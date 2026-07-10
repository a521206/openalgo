"""
Unit tests for Liquidity Fallback Service.

Exercises the public/protected methods of the real LiquidityFallbackService.
Heavy dependencies (DB, quotes, option-symbol) are mocked via root conftest.py.
"""

import pytest

from services.liquidity_fallback_service import (
    MAX_DEEPER_SCAN,
    LiquidityFallbackService,
    LiquidStrike,
)

S = LiquidityFallbackService()


# ---------------------------------------------------------------------------
# _parse_offset_number
# ---------------------------------------------------------------------------
class TestParseOffsetNumber:
    def test_atm_returns_none(self):
        assert S._parse_offset_number("ATM") is None
        assert S._parse_offset_number("atm") is None

    def test_itm_offsets_parsed(self):
        assert S._parse_offset_number("ITM1") == 1
        assert S._parse_offset_number("ITM2") == 2
        assert S._parse_offset_number("ITM50") == 50
        assert S._parse_offset_number("itm5") == 5

    def test_otm_offsets_parsed(self):
        assert S._parse_offset_number("OTM1") == 1
        assert S._parse_offset_number("OTM5") == 5
        assert S._parse_offset_number("otm50") == 50

    def test_invalid_offsets(self):
        for bad in ["INVALID", "ITM", "OTM", "ITMax", "", "   "]:
            assert S._parse_offset_number(bad) is None


# ---------------------------------------------------------------------------
# should_fallback
# ---------------------------------------------------------------------------
class TestShouldFallback:
    def test_atm_always_triggers(self):
        triggered, reason = S.should_fallback("ATM", 100, 100)
        assert triggered is True
        assert reason == "atm_selected"

    def test_no_liquidity_triggers(self):
        triggered, reason = S.should_fallback("ITM2", 0, 0)
        assert triggered is True
        assert reason == "no_liquidity"

    def test_liquid_no_fallback(self):
        triggered, reason = S.should_fallback("ITM2", 50, 55)
        assert triggered is False
        assert reason == ""


# ---------------------------------------------------------------------------
# _get_candidate_strikes
# ---------------------------------------------------------------------------
STRIKES = [23000, 23100, 23200, 23300, 23400, 23500, 23600, 23700, 23800]


class TestGetCandidateStrikes:

    def _candidates(self, atm, strikes, option_type, offset):
        cands, degraded, reason = S._get_candidate_strikes(atm, strikes, option_type, offset)
        return cands

    def test_max_deeper_scan_constant(self):
        assert MAX_DEEPER_SCAN == 3

    def test_atm_anchor_window_ce(self):
        result = self._candidates(23500, STRIKES, "CE", "ATM")
        assert result == [23500, 23400]

    def test_atm_anchor_window_pe(self):
        result = self._candidates(23500, STRIKES, "PE", "ATM")
        assert result == [23500, 23600]

    def test_invalid_offset_uses_anchor_window(self):
        result, degraded, _ = S._get_candidate_strikes(23500, STRIKES, "CE", "INVALID")
        assert degraded is False
        assert result == [23500, 23400]

    def test_itm1_ce_four_candidates(self):
        result = self._candidates(23500, STRIKES, "CE", "ITM1")
        assert result == [23400, 23300, 23200, 23100]

    def test_itm2_ce_four_candidates(self):
        result = self._candidates(23500, STRIKES, "CE", "ITM2")
        assert result == [23300, 23200, 23100, 23000]

    def test_itm3_ce_three_candidates_boundary(self):
        result = self._candidates(23500, STRIKES, "CE", "ITM3")
        assert result == [23200, 23100, 23000]

    def test_itm5_ce_single_candidate_at_boundary(self):
        result = self._candidates(23500, STRIKES, "CE", "ITM5")
        assert result == [23000]

    def test_itm2_pe_two_candidates_at_upper_bounds(self):
        result = self._candidates(23500, STRIKES, "PE", "ITM2")
        assert result == [23700, 23800]

    def test_otm2_ce_two_candidates_at_upper_bound(self):
        result = self._candidates(23500, STRIKES, "CE", "OTM2")
        assert result == [23700, 23800]

    def test_otm2_pe_four_candidates(self):
        result = self._candidates(23500, STRIKES, "PE", "OTM2")
        assert result == [23300, 23200, 23100, 23000]

    def test_out_of_range_degrades(self):
        short_strikes = [23000, 23100, 23200]
        result, degraded, reason = S._get_candidate_strikes(23100, short_strikes, "CE", "ITM5")
        assert degraded is True
        assert reason == "offset_out_of_bounds"
        assert result == [23100, 23000]


# ---------------------------------------------------------------------------
# _select_best_strike
# ---------------------------------------------------------------------------
class TestSelectBestStrike:
    def _strike_to_symbol(self):
        return {
            23200: ("NIFTY28OCT2523200CE", {"lotsize": 25, "tick_size": 0.05}),
            23300: ("NIFTY28OCT2523300CE", {"lotsize": 25, "tick_size": 0.05}),
            23400: ("NIFTY28OCT2523400CE", {"lotsize": 25, "tick_size": 0.05}),
        }

    def test_picks_highest_score(self):
        quotes_response = {
            "results": [
                {"symbol": "NIFTY28OCT2523200CE", "data": {"bid": 10, "ask": 12, "volume": 5000, "oi": 20000, "ltp": 11}},
                {"symbol": "NIFTY28OCT2523300CE", "data": {"bid": 20, "ask": 22, "volume": 2000, "oi": 15000, "ltp": 21}},
                {"symbol": "NIFTY28OCT2523400CE", "data": {"bid": 5, "ask": 7, "volume": 10000, "oi": 5000, "ltp": 6}},
            ]
        }
        best, evaluated = S._select_best_strike(quotes_response, self._strike_to_symbol(), "NFO")
        assert isinstance(best, LiquidStrike)
        assert best.symbol == "NIFTY28OCT2523200CE"
        assert best.score == 5000 * 0.6 + 20000 * 0.4
        assert len(evaluated) == 3

    def test_unqualified_excluded_from_result(self):
        quotes_response = {
            "results": [
                {"symbol": "NIFTY28OCT2523200CE", "data": {"bid": 0, "ask": 12, "volume": 5000, "oi": 20000}},
                {"symbol": "NIFTY28OCT2523300CE", "data": {"bid": 20, "ask": 22, "volume": 2000, "oi": 15000}},
            ]
        }
        strike_to_symbol = {
            23200: ("NIFTY28OCT2523200CE", {"lotsize": 25, "tick_size": 0.05}),
            23300: ("NIFTY28OCT2523300CE", {"lotsize": 25, "tick_size": 0.05}),
        }
        best, evaluated = S._select_best_strike(quotes_response, strike_to_symbol, "NFO")
        assert best.symbol == "NIFTY28OCT2523300CE"
        assert len(evaluated) == 1
        assert evaluated[0]["symbol"] == "NIFTY28OCT2523300CE"

    def test_no_qualified_strikes(self):
        quotes_response = {
            "results": [
                {"symbol": "NIFTY28OCT2523200CE", "data": {"bid": 0, "ask": 0, "volume": 0, "oi": 0}},
            ]
        }
        strike_to_symbol = {
            23200: ("NIFTY28OCT2523200CE", {"lotsize": 25, "tick_size": 0.05}),
        }
        best, evaluated = S._select_best_strike(quotes_response, strike_to_symbol, "NFO")
        assert best is None
        assert evaluated == []

    def test_evaluated_metadata(self):
        quotes_response = {
            "results": [
                {"symbol": "NIFTY28OCT2523200CE", "data": {"bid": 10, "ask": 12, "volume": 1000, "oi": 5000, "ltp": 11}},
            ]
        }
        strike_to_symbol = {
            23200: ("NIFTY28OCT2523200CE", {"lotsize": 25, "tick_size": 0.05}),
        }
        best, evaluated = S._select_best_strike(quotes_response, strike_to_symbol, "NFO")
        e = evaluated[0]
        assert e["strike"] == 23200
        assert e["symbol"] == "NIFTY28OCT2523200CE"
        assert e["bid"] == 10
        assert e["ask"] == 12
        assert e["volume"] == 1000
        assert e["oi"] == 5000
        assert e["score"] == 1000 * 0.6 + 5000 * 0.4
