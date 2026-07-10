"""
Liquidity Fallback Service

Handles automatic selection of liquid option strikes when the requested strike lacks liquidity.
"""

from dataclasses import dataclass, field
from typing import Any

from database.settings_db import get_smart_trade_rules
from services.option_symbol_service import (
    find_atm_strike_from_actual,
    find_option_symbols_by_strikes_batch,
    get_available_strikes,
    get_option_exchange,
    get_option_symbol,
    parse_underlying_symbol,
)
from services.quotes_service import get_multiquotes
from utils.logging import get_logger

logger = get_logger(__name__)

MAX_DEEPER_SCAN = 3
DEFAULT_TICK_SIZE = 0.05


@dataclass
class LiquidStrike:
    symbol: str
    exchange: str
    lotsize: int = 0
    tick_size: float = DEFAULT_TICK_SIZE
    bid: float = 0.0
    ask: float = 0.0
    ltp: float = 0.0
    score: float = 0.0


@dataclass
class LiquidityEvaluationResult:
    selected: LiquidStrike | None = None
    evaluated: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False
    degradation_reason: str = ""


@dataclass
class LiquidityResult:
    applied: bool = False
    original_symbol: str = ""
    selected_symbol: str = ""
    reason: str = ""
    evaluated_strikes: list[dict[str, Any]] = field(default_factory=list)


class LiquidityFallbackService:

    def should_fallback(self, offset: str, bid: float, ask: float) -> tuple[bool, str]:
        if offset.upper() == "ATM":
            return True, "atm_selected"
        if bid <= 0 or ask <= 0:
            return True, "no_liquidity"
        return False, ""

    @staticmethod
    def _parse_offset_number(offset: str) -> int | None:
        upper = offset.strip().upper()
        if upper == "ATM":
            return None
        for prefix in ("ITM", "OTM"):
            if upper.startswith(prefix) and upper[len(prefix):].isdigit():
                return int(upper[len(prefix):])
        return None

    @staticmethod
    def _direction(option_type: str, offset: str) -> int:
        ot_upper = option_type.upper()
        is_itm = offset.strip().upper().startswith("ITM")
        if (ot_upper == "CE" and is_itm) or (ot_upper == "PE" and not is_itm):
            return -1
        return 1

    def _window_from_anchor(
        self,
        anchor_index: int,
        available_strikes: list[float],
        direction: int,
        depth: int,
    ) -> list[float]:
        result = []
        for i in range(depth + 1):
            idx = anchor_index + direction * i
            if 0 <= idx < len(available_strikes):
                result.append(available_strikes[idx])
        return result

    def _get_candidate_strikes(
        self,
        atm_strike: float,
        available_strikes: list[float],
        option_type: str,
        offset: str,
    ) -> tuple[list[float], bool, str]:
        atm_index = available_strikes.index(atm_strike)
        ot_upper = option_type.upper()
        anchor_direction = -1 if ot_upper == "CE" else 1
        offset_number = self._parse_offset_number(offset)

        if offset_number is None:
            return self._window_from_anchor(atm_index, available_strikes, anchor_direction, 1), False, ""

        direction = self._direction(option_type, offset)
        target_index = atm_index + direction * offset_number

        if target_index < 0 or target_index >= len(available_strikes):
            logger.warning(
                f"Offset {offset} target_out_of_bounds for {ot_upper} "
                f"(atm_index={atm_index}, target={target_index}, len={len(available_strikes)}); "
                f"degrading to anchor window"
            )
            return self._window_from_anchor(atm_index, available_strikes, anchor_direction, 1), True, "offset_out_of_bounds"

        candidates = self._window_from_anchor(target_index, available_strikes, direction, MAX_DEEPER_SCAN)
        return candidates, False, ""

    def evaluate(
        self,
        underlying: str,
        exchange: str,
        expiry_date: str,
        option_type: str,
        api_key: str,
        offset: str = "ATM",
        underlying_ltp: float | None = None,
        options_exchange: str | None = None,
    ) -> LiquidityEvaluationResult:
        normalized_offset = (offset or "ATM").strip().upper()

        try:
            parsed_base, embedded_expiry = parse_underlying_symbol(underlying)
            base_symbol = parsed_base
            final_expiry = embedded_expiry or expiry_date
            target_exchange = options_exchange or get_option_exchange(exchange)

            available_strikes = get_available_strikes(
                base_symbol, final_expiry, option_type, target_exchange
            )
            if not available_strikes:
                logger.warning(f"No strikes available for {underlying} {option_type}")
                return LiquidityEvaluationResult()

            if underlying_ltp is None or underlying_ltp <= 0:
                success, symbol_resp, _ = get_option_symbol(
                    underlying=underlying,
                    exchange=exchange,
                    expiry_date=expiry_date,
                    strike_int=None,
                    offset="ATM",
                    option_type=option_type,
                    api_key=api_key,
                )
                if not success:
                    logger.warning("Unable to resolve underlying LTP for liquidity fallback")
                    return LiquidityEvaluationResult()
                underlying_ltp = symbol_resp.get("underlying_ltp")

            if underlying_ltp is None or underlying_ltp <= 0:
                logger.warning("Underlying LTP unavailable for liquidity fallback")
                return LiquidityEvaluationResult()

            atm_strike = find_atm_strike_from_actual(underlying_ltp, available_strikes)
            if atm_strike is None:
                logger.warning(f"Could not determine ATM strike for {underlying}")
                return LiquidityEvaluationResult()

            candidates, degraded, degradation_reason = self._get_candidate_strikes(
                atm_strike, available_strikes, option_type, normalized_offset
            )

            if not candidates:
                return LiquidityEvaluationResult(degraded=degraded, degradation_reason=degradation_reason or "no_candidates")

            batch_results = find_option_symbols_by_strikes_batch(
                base_symbol, final_expiry, candidates, target_exchange
            )

            symbols_to_fetch = []
            strike_to_symbol = {}
            for strike in candidates:
                info = batch_results.get((strike, option_type.upper()), {})
                symbol = info.get("symbol")
                if symbol:
                    symbols_to_fetch.append({"symbol": symbol, "exchange": target_exchange})
                    strike_to_symbol[strike] = (symbol, info)

            if not symbols_to_fetch:
                logger.warning("No valid symbols found for candidate strikes")
                return LiquidityEvaluationResult(degraded=degraded, degradation_reason=degradation_reason or "no_symbols")

            success, quotes_response, _ = get_multiquotes(symbols=symbols_to_fetch, api_key=api_key)
            if not success:
                logger.error("Failed to fetch quotes for liquidity evaluation")
                return LiquidityEvaluationResult(degraded=degraded, degradation_reason=degradation_reason or "quotes_failed")

            selected = self._select_best_strike(quotes_response, strike_to_symbol, target_exchange)
            best_strike, evaluated = selected

            return LiquidityEvaluationResult(
                selected=best_strike,
                evaluated=evaluated,
                degraded=degraded,
                degradation_reason=degradation_reason,
            )

        except Exception as e:
            logger.exception(f"Error in evaluate: {e}")
            return LiquidityEvaluationResult(degraded=True, degradation_reason="exception")

    @staticmethod
    def _select_best_strike(
        quotes_response: dict[str, Any],
        strike_to_symbol: dict[float, tuple[str, dict[str, Any]]],
        exchange: str,
    ) -> tuple[LiquidStrike | None, list[dict[str, Any]]]:
        best_strike = None
        best_score = -1
        evaluated: list[dict[str, Any]] = []

        symbol_to_strike = {sym: (s, info) for s, (sym, info) in strike_to_symbol.items()}

        for result in quotes_response.get("results", []):
            symbol = result.get("symbol", "")
            if "error" in result and "data" not in result:
                continue

            data = result.get("data", result)
            bid = data.get("bid", 0) or 0
            ask = data.get("ask", 0) or 0

            if bid <= 0 or ask <= 0:
                continue

            volume = data.get("volume", 0) or 0
            oi = data.get("oi", 0) or 0
            score = volume * 0.6 + oi * 0.4

            strike, batch_info = symbol_to_strike.get(symbol, (None, {}))
            evaluated.append(
                {
                    "strike": strike,
                    "symbol": symbol,
                    "bid": bid,
                    "ask": ask,
                    "volume": volume,
                    "oi": oi,
                    "score": score,
                }
            )

            if score > best_score and strike is not None:
                best_score = score
                ltp = data.get("ltp") or ((bid + ask) / 2 if bid > 0 and ask > 0 else 0.0)
                best_strike = LiquidStrike(
                    symbol=symbol,
                    exchange=exchange,
                    lotsize=batch_info.get("lotsize", 0),
                    tick_size=batch_info.get("tick_size", DEFAULT_TICK_SIZE),
                    bid=bid,
                    ask=ask,
                    ltp=ltp,
                    score=score,
                )

        return best_strike, evaluated


_liquidity_service = None


def get_liquidity_fallback_service() -> LiquidityFallbackService:
    global _liquidity_service
    if _liquidity_service is None:
        _liquidity_service = LiquidityFallbackService()
    return _liquidity_service


def is_liquidity_fallback_enabled() -> bool:
    smart_rules = get_smart_trade_rules()
    return smart_rules.get("liquidity_fallback", True)
