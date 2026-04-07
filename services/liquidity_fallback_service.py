"""
Liquidity Fallback Service

Handles automatic selection of liquid option strikes when the requested strike lacks liquidity.
Provides simplified, maintainable logic for liquidity fallback operations.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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


@dataclass
class LiquidityResult:
    """Result of liquidity fallback operation"""
    applied: bool = False
    original_symbol: str = ""
    selected_symbol: str = ""
    reason: str = ""
    evaluated_strikes: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LiquidStrike:
    """Represents a liquid strike option"""
    symbol: str
    exchange: str
    lotsize: int = 0
    tick_size: float = 0.05
    bid: float = 0.0
    ask: float = 0.0
    ltp: float = 0.0
    score: float = 0.0


class LiquidityFallbackService:
    """
    Service for handling liquidity fallback in options trading.

    Simplifies the complex logic of selecting alternative strikes when
    the requested option lacks sufficient liquidity.
    """

    def should_fallback(self, offset: str, bid: float, ask: float) -> Tuple[bool, str]:
        """
        Determine if liquidity fallback should be applied.

        Args:
            offset: Strike offset (ATM, ITM1, etc.)
            bid: Current bid price
            ask: Current ask price

        Returns:
            Tuple of (should_fallback, reason)
        """
        if offset.upper() == "ATM":
            return True, "atm_selected"

        if bid <= 0 or ask <= 0:
            return True, "no_liquidity"

        return False, ""

    def find_liquid_strike(
        self,
        underlying: str,
        exchange: str,
        expiry_date: str,
        option_type: str,
        api_key: str,
        underlying_ltp: Optional[float] = None,
        options_exchange: Optional[str] = None,
    ) -> Optional[LiquidStrike]:
        """
        Find the most liquid strike from available options.

        Uses simplified logic: try ATM first, then 1 ITM if needed.

        Args:
            underlying: Underlying symbol
            exchange: Exchange
            expiry_date: Expiry date
            option_type: CE or PE
            api_key: API key for quotes
            underlying_ltp: Underlying LTP (optional)
            options_exchange: Options exchange (optional)

        Returns:
            LiquidStrike if found, None otherwise
        """
        try:
            # Parse symbol and determine exchanges
            parsed_base, embedded_expiry = parse_underlying_symbol(underlying)
            base_symbol = parsed_base
            final_expiry = embedded_expiry or expiry_date
            target_exchange = options_exchange or get_option_exchange(exchange)

            # Get available strikes
            available_strikes = get_available_strikes(
                base_symbol, final_expiry, option_type, target_exchange
            )
            if not available_strikes:
                logger.warning(f"No strikes available for {underlying} {option_type}")
                return None

            # Resolve underlying LTP if missing or invalid
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
                    return None
                underlying_ltp = symbol_resp.get("underlying_ltp")

            if underlying_ltp is None or underlying_ltp <= 0:
                logger.warning("Underlying LTP unavailable for liquidity fallback")
                return None

            # Find ATM strike
            atm_strike = find_atm_strike_from_actual(underlying_ltp, available_strikes)
            if not atm_strike:
                logger.warning(f"Could not determine ATM strike for {underlying}")
                return None

            # Try ATM first, then 1 ITM
            candidate_strikes = self._get_candidate_strikes(atm_strike, available_strikes, option_type)

            if not candidate_strikes:
                logger.warning(f"No candidate strikes found for {underlying}")
                return None

            # Get symbols for candidates
            batch_results = find_option_symbols_by_strikes_batch(
                base_symbol, final_expiry, candidate_strikes, target_exchange
            )

            # Build symbols to fetch
            symbols_to_fetch = []
            strike_to_symbol = {}

            for strike in candidate_strikes:
                info = batch_results.get((strike, option_type.upper()), {})
                symbol = info.get("symbol")
                if symbol:
                    symbols_to_fetch.append({"symbol": symbol, "exchange": target_exchange})
                    strike_to_symbol[strike] = (symbol, info)

            if not symbols_to_fetch:
                logger.warning(f"No valid symbols found for candidate strikes")
                return None

            # Fetch quotes for all candidates
            success, quotes_response, _ = get_multiquotes(symbols=symbols_to_fetch, api_key=api_key)
            if not success:
                logger.error(f"Failed to fetch quotes for liquidity evaluation")
                return None

            # Find best liquid strike
            return self._select_best_strike(quotes_response, strike_to_symbol, target_exchange)

        except Exception as e:
            logger.exception(f"Error in find_liquid_strike: {e}")
            return None

    def _get_candidate_strikes(self, atm_strike: float, available_strikes: List[float], option_type: str) -> List[float]:
        """Get candidate strikes to evaluate (ATM + 1 ITM)"""
        atm_index = available_strikes.index(atm_strike)
        option_type_upper = option_type.upper()

        candidates = [atm_strike]  # Always include ATM

        # Add 1 ITM strike
        if option_type_upper == "CE" and atm_index > 0:
            candidates.append(available_strikes[atm_index - 1])
        elif option_type_upper == "PE" and atm_index < len(available_strikes) - 1:
            candidates.append(available_strikes[atm_index + 1])

        return candidates

    def _select_best_strike(
        self,
        quotes_response: Dict[str, Any],
        strike_to_symbol: Dict[float, Tuple[str, Dict[str, Any]]],
        exchange: str
    ) -> Optional[LiquidStrike]:
        """Select the best liquid strike from quote results"""
        best_strike = None
        best_score = -1

        for result in quotes_response.get("results", []):
            symbol = result.get("symbol", "")

            # Skip errors
            if "error" in result and "data" not in result:
                continue

            data = result.get("data", result)
            bid = data.get("bid", 0) or 0
            ask = data.get("ask", 0) or 0

            # Must have valid bid and ask
            if bid <= 0 or ask <= 0:
                continue

            # Simple scoring: prefer higher volume, then higher OI
            volume = data.get("volume", 0) or 0
            oi = data.get("oi", 0) or 0
            score = volume * 0.6 + oi * 0.4  # Simplified scoring

            if score > best_score:
                best_score = score

                # Find strike for this symbol
                strike = None
                batch_info = {}
                for s, (sym, info) in strike_to_symbol.items():
                    if sym == symbol:
                        strike = s
                        batch_info = info
                        break

                if strike is not None:
                    ltp = data.get("ltp") or ((bid + ask) / 2 if bid > 0 and ask > 0 else 0.0)
                    best_strike = LiquidStrike(
                        symbol=symbol,
                        exchange=exchange,
                        lotsize=batch_info.get("lotsize", 0),
                        tick_size=batch_info.get("tick_size", 0.05),
                        bid=bid,
                        ask=ask,
                        ltp=ltp,
                        score=score,
                    )

        return best_strike


# Global service instance
_liquidity_service = None


def get_liquidity_fallback_service() -> LiquidityFallbackService:
    """Get the global liquidity fallback service instance"""
    global _liquidity_service
    if _liquidity_service is None:
        _liquidity_service = LiquidityFallbackService()
    return _liquidity_service


def is_liquidity_fallback_enabled() -> bool:
    """Check if liquidity fallback is enabled in smart trade rules"""
    smart_rules = get_smart_trade_rules()
    return smart_rules.get("liquidity_fallback", True)