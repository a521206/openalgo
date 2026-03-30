"""
Unit tests for Smart Trade Rules Service - Maximum Position Lots Functionality

Tests cover:
- Position change analysis (OPENING, INCREASING, REDUCING, REVERSING)
- Position size validation with short positions
- F&O position size validation with lot sizes
- Lot size fetch for different exchanges
- Edge cases and error handling
"""

import pytest
from unittest.mock import patch, MagicMock

from services.smart_trade_rules_service import (
    PositionChangeType,
    PositionChange,
    PositionFetchStatus,
    PositionFetchResult,
    LotSizeFetchStatus,
    LotSizeResult,
    analyze_position_change,
    validate_against_smart_trade_rules,
    get_lot_size_with_status,
)


class TestPositionChangeTypeEnum:
    """Tests for PositionChangeType enum."""
    
    def test_enum_values(self):
        """Test that all expected enum values exist."""
        assert PositionChangeType.REDUCING.value == "reducing"
        assert PositionChangeType.INCREASING.value == "increasing"
        assert PositionChangeType.REVERSING.value == "reversing"
        assert PositionChangeType.OPENING.value == "opening"


class TestPositionChangeDataclass:
    """Tests for PositionChange dataclass."""
    
    def test_position_change_creation(self):
        """Test creating a PositionChange instance."""
        change = PositionChange(
            change_type=PositionChangeType.OPENING,
            current_qty=0,
            new_qty=100,
            increment=100,
            direction="LONG"
        )
        assert change.change_type == PositionChangeType.OPENING
        assert change.current_qty == 0
        assert change.new_qty == 100
        assert change.increment == 100
        assert change.direction == "LONG"


class TestAnalyzePositionChange:
    """Tests for analyze_position_change function."""
    
    # --- OPENING tests ---
    
    def test_open_long_from_flat(self):
        """Opening a long position from flat."""
        result = analyze_position_change(0, "BUY", 100)
        assert result.change_type == PositionChangeType.OPENING
        assert result.current_qty == 0
        assert result.new_qty == 100
        assert result.increment == 100
        assert result.direction == "LONG"
    
    def test_open_short_from_flat(self):
        """Opening a short position from flat."""
        result = analyze_position_change(0, "SELL", 100)
        assert result.change_type == PositionChangeType.OPENING
        assert result.current_qty == 0
        assert result.new_qty == -100
        assert result.increment == 100
        assert result.direction == "SHORT"
    
    def test_open_long_lowercase_action(self):
        """Opening with lowercase action should work."""
        result = analyze_position_change(0, "buy", 50)
        assert result.change_type == PositionChangeType.OPENING
        assert result.new_qty == 50
        assert result.direction == "LONG"
    
    # --- INCREASING tests ---
    
    def test_increase_long(self):
        """Increasing a long position."""
        result = analyze_position_change(50, "BUY", 50)
        assert result.change_type == PositionChangeType.INCREASING
        assert result.current_qty == 50
        assert result.new_qty == 100
        assert result.increment == 50
        assert result.direction == "LONG"
    
    def test_increase_short(self):
        """Increasing a short position (more short)."""
        result = analyze_position_change(-50, "SELL", 50)
        assert result.change_type == PositionChangeType.INCREASING
        assert result.current_qty == -50
        assert result.new_qty == -100
        assert result.increment == 50
        assert result.direction == "SHORT"
    
    # --- REDUCING tests ---
    
    def test_reduce_long(self):
        """Reducing a long position."""
        result = analyze_position_change(100, "SELL", 50)
        assert result.change_type == PositionChangeType.REDUCING
        assert result.current_qty == 100
        assert result.new_qty == 50
        assert result.increment == 0  # No increase
        assert result.direction == "LONG"
    
    def test_reduce_short(self):
        """Reducing a short position (buying back)."""
        result = analyze_position_change(-100, "BUY", 50)
        assert result.change_type == PositionChangeType.REDUCING
        assert result.current_qty == -100
        assert result.new_qty == -50
        assert result.increment == 0  # No increase
        assert result.direction == "SHORT"
    
    def test_close_long_completely(self):
        """Closing a long position completely."""
        result = analyze_position_change(100, "SELL", 100)
        assert result.change_type == PositionChangeType.REDUCING
        assert result.new_qty == 0
        assert result.direction == "FLAT"
    
    def test_close_short_completely(self):
        """Closing a short position completely."""
        result = analyze_position_change(-100, "BUY", 100)
        assert result.change_type == PositionChangeType.REDUCING
        assert result.new_qty == 0
        assert result.direction == "FLAT"
    
    # --- REVERSING tests ---
    
    def test_reverse_long_to_short(self):
        """Reversing from long to short (sell more than current long)."""
        result = analyze_position_change(50, "SELL", 150)
        assert result.change_type == PositionChangeType.REVERSING
        assert result.current_qty == 50
        assert result.new_qty == -100
        assert result.increment == 100  # New short position size
        assert result.direction == "SHORT"
    
    def test_reverse_short_to_long(self):
        """Reversing from short to long (buy more than current short)."""
        result = analyze_position_change(-50, "BUY", 150)
        assert result.change_type == PositionChangeType.REVERSING
        assert result.current_qty == -50
        assert result.new_qty == 100
        assert result.increment == 100  # New long position size
        assert result.direction == "LONG"
    
    def test_reverse_long_to_smaller_short(self):
        """Reversing from large long to smaller short."""
        result = analyze_position_change(100, "SELL", 150)
        assert result.change_type == PositionChangeType.REVERSING
        assert result.new_qty == -50
        assert result.increment == 50
        assert result.direction == "SHORT"
    
    # --- Edge cases ---
    
    def test_zero_quantity_buy(self):
        """BUY with zero quantity should result in no change."""
        result = analyze_position_change(100, "BUY", 0)
        assert result.change_type == PositionChangeType.REDUCING
        assert result.new_qty == 100
    
    def test_zero_quantity_sell(self):
        """SELL with zero quantity should result in no change."""
        result = analyze_position_change(100, "SELL", 0)
        assert result.change_type == PositionChangeType.REDUCING
        assert result.new_qty == 100


class TestPositionSizeValidationWithShortPositions:
    """Tests for position size validation that accounts for short positions."""
    
    def _create_position_result(self, qty: int, status: PositionFetchStatus = PositionFetchStatus.SUCCESS):
        """Helper to create a PositionFetchResult."""
        return PositionFetchResult(quantity=qty, status=status)
    
    def _create_order_data(self, symbol: str = "RELIANCE", exchange: str = "NSE", 
                           action: str = "BUY", quantity: int = 100, price: float = 100.0,
                           product_type: str = "MIS"):
        """Helper to create order data."""
        return {
            "symbol": symbol,
            "exchange": exchange,
            "action": action,
            "quantity": quantity,
            "price": price,
            "product_type": product_type
        }
    
    # --- Tests for REDUCING positions (should skip limit check) ---
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_reduce_long_skips_limit_check(self, mock_rules):
        """Reducing a long position should skip limit check."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 50,  # Limit is 50
        }
        
        # Current position is 100 (above limit), selling 50 to reduce to 50
        order_data = self._create_order_data(action="SELL", quantity=50)
        position_result = self._create_position_result(100)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        # Should pass because we're reducing, even though current > limit
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_reduce_short_skips_limit_check(self, mock_rules):
        """Reducing a short position should skip limit check."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 50,
        }
        
        # Current short position is -100, buying 50 to reduce to -50
        order_data = self._create_order_data(action="BUY", quantity=50)
        position_result = self._create_position_result(-100)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_close_long_position_allowed(self, mock_rules):
        """Closing a long position should always be allowed."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 50,
        }
        
        # Close a position of 100
        order_data = self._create_order_data(action="SELL", quantity=100)
        position_result = self._create_position_result(100)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    # --- Tests for OPENING positions (should check limit) ---
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_open_long_within_limit(self, mock_rules):
        """Opening a long position within limit should pass."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        order_data = self._create_order_data(action="BUY", quantity=50)
        position_result = self._create_position_result(0)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_open_long_exceeds_limit(self, mock_rules):
        """Opening a long position exceeding limit should fail."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 50,
        }
        
        order_data = self._create_order_data(action="BUY", quantity=100)
        position_result = self._create_position_result(0)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is False
        assert "Maximum position size exceeded" in error
        assert "LONG" in error
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_open_short_within_limit(self, mock_rules):
        """Opening a short position within limit should pass."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        order_data = self._create_order_data(action="SELL", quantity=50)
        position_result = self._create_position_result(0)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_open_short_exceeds_limit(self, mock_rules):
        """Opening a short position exceeding limit should fail."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 50,
        }
        
        order_data = self._create_order_data(action="SELL", quantity=100)
        position_result = self._create_position_result(0)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is False
        assert "Maximum position size exceeded" in error
        assert "SHORT" in error
    
    # --- Tests for INCREASING positions (should check limit) ---
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_increase_long_within_limit(self, mock_rules):
        """Increasing a long position within limit should pass."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Current 50, buying 50 more = 100 total
        order_data = self._create_order_data(action="BUY", quantity=50)
        position_result = self._create_position_result(50)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_increase_long_exceeds_limit(self, mock_rules):
        """Increasing a long position exceeding limit should fail."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Current 75, buying 50 more = 125 total (exceeds 100)
        order_data = self._create_order_data(action="BUY", quantity=50)
        position_result = self._create_position_result(75)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is False
        assert "Maximum position size exceeded" in error
        assert "125" in error
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_increase_short_within_limit(self, mock_rules):
        """Increasing a short position within limit should pass."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Current -50, selling 50 more = -100 total
        order_data = self._create_order_data(action="SELL", quantity=50)
        position_result = self._create_position_result(-50)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_increase_short_exceeds_limit(self, mock_rules):
        """Increasing a short position exceeding limit should fail."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Current -75, selling 50 more = -125 total (exceeds 100)
        order_data = self._create_order_data(action="SELL", quantity=50)
        position_result = self._create_position_result(-75)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is False
        assert "Maximum position size exceeded" in error
        assert "125" in error
    
    # --- Tests for REVERSING positions (should check new position limit) ---
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_reverse_long_to_short_within_limit(self, mock_rules):
        """Reversing from long to short within limit should pass."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Current +50, selling 100 = -50 short (within limit)
        order_data = self._create_order_data(action="SELL", quantity=100)
        position_result = self._create_position_result(50)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_reverse_long_to_short_exceeds_limit(self, mock_rules):
        """Reversing from long to short exceeding limit should fail."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 50,
        }
        
        # Current +50, selling 150 = -100 short (exceeds 50 limit)
        order_data = self._create_order_data(action="SELL", quantity=150)
        position_result = self._create_position_result(50)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is False
        assert "Maximum position size exceeded" in error
        assert "SHORT" in error
        assert "100" in error
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_reverse_short_to_long_within_limit(self, mock_rules):
        """Reversing from short to long within limit should pass."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Current -50, buying 100 = +50 long (within limit)
        order_data = self._create_order_data(action="BUY", quantity=100)
        position_result = self._create_position_result(-50)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_reverse_short_to_long_exceeds_limit(self, mock_rules):
        """Reversing from short to long exceeding limit should fail."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 50,
        }
        
        # Current -50, buying 150 = +100 long (exceeds 50 limit)
        order_data = self._create_order_data(action="BUY", quantity=150)
        position_result = self._create_position_result(-50)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is False
        assert "Maximum position size exceeded" in error
        assert "LONG" in error
        assert "100" in error


class TestPositionSizeValidationForFO:
    """Tests for F&O position size validation with lot sizes."""
    
    def _create_position_result(self, qty: int, status: PositionFetchStatus = PositionFetchStatus.SUCCESS):
        """Helper to create a PositionFetchResult."""
        return PositionFetchResult(quantity=qty, status=status)
    
    def _create_order_data(self, symbol: str = "NIFTY24FEB18000CE", exchange: str = "NFO",
                           action: str = "BUY", quantity: int = 50, price: float = 100.0,
                           product_type: str = "NRML"):
        """Helper to create order data."""
        return {
            "symbol": symbol,
            "exchange": exchange,
            "action": action,
            "quantity": quantity,
            "price": price,
            "product_type": product_type
        }
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    @patch("services.smart_trade_rules_service.get_lot_size_with_status")
    def test_fo_reduce_position_skips_limit(self, mock_lot_size, mock_rules):
        """F&O: Reducing position should skip limit check."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 2,  # 2 lots max
        }
        mock_lot_size.return_value = LotSizeResult(
            lot_size=50,
            status=LotSizeFetchStatus.SUCCESS,
            exchange="NFO"
        )
        
        # Current 3 lots (150 qty), selling 1 lot (50 qty) to reduce to 2 lots
        order_data = self._create_order_data(action="SELL", quantity=50)
        position_result = self._create_position_result(150)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    @patch("services.smart_trade_rules_service.get_lot_size_with_status")
    def test_fo_increase_position_within_limit(self, mock_lot_size, mock_rules):
        """F&O: Increasing position within limit should pass."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 5,  # 5 lots max
        }
        mock_lot_size.return_value = LotSizeResult(
            lot_size=50,
            status=LotSizeFetchStatus.SUCCESS,
            exchange="NFO"
        )
        
        # Current 2 lots (100 qty), buying 2 lots (100 qty) = 4 lots total
        order_data = self._create_order_data(action="BUY", quantity=100)
        position_result = self._create_position_result(100)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    @patch("services.smart_trade_rules_service.get_lot_size_with_status")
    def test_fo_increase_position_exceeds_limit(self, mock_lot_size, mock_rules):
        """F&O: Increasing position exceeding limit should fail."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 3,  # 3 lots max
        }
        mock_lot_size.return_value = LotSizeResult(
            lot_size=50,
            status=LotSizeFetchStatus.SUCCESS,
            exchange="NFO"
        )
        
        # Current 2 lots (100 qty), buying 2 lots (100 qty) = 4 lots total (exceeds 3)
        order_data = self._create_order_data(action="BUY", quantity=100)
        position_result = self._create_position_result(100)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is False
        assert "Maximum position size exceeded" in error
        assert "4.00 lots" in error


class TestLotSizeFetch:
    """Tests for lot size fetch functionality."""
    
    @patch("services.smart_trade_rules_service.get_symbol_info")
    def test_nfo_lot_size_success(self, mock_get_symbol_info):
        """NFO lot size should be fetched from master contract."""
        mock_symbol_info = MagicMock()
        mock_symbol_info.lotsize = 50
        mock_get_symbol_info.return_value = mock_symbol_info
        
        result = get_lot_size_with_status("NIFTY24FEB18000CE", "NFO")
        
        assert result.lot_size == 50
        assert result.status == LotSizeFetchStatus.SUCCESS
        assert result.exchange == "NFO"
    
    @patch("services.smart_trade_rules_service.get_symbol_info")
    def test_nfo_lot_size_not_found(self, mock_get_symbol_info):
        """NFO lot size not found should return NOT_FOUND status."""
        mock_get_symbol_info.return_value = None
        
        result = get_lot_size_with_status("NIFTY24FEB18000CE", "NFO")
        
        assert result.lot_size == 1
        assert result.status == LotSizeFetchStatus.NOT_FOUND
        assert result.exchange == "NFO"
        assert "not found" in result.error_message.lower()
    
    @patch("services.smart_trade_rules_service.get_symbol_info")
    def test_nfo_lot_size_fetch_error(self, mock_get_symbol_info):
        """NFO lot size fetch error should return FAILED status."""
        mock_get_symbol_info.side_effect = Exception("Database error")
        
        result = get_lot_size_with_status("NIFTY24FEB18000CE", "NFO")
        
        assert result.lot_size == 1
        assert result.status == LotSizeFetchStatus.FAILED
        assert result.exchange == "NFO"
        assert "Database error" in result.error_message
    
    def test_nse_lot_size_equity(self):
        """NSE lot size should always be 1 (equity)."""
        result = get_lot_size_with_status("RELIANCE", "NSE")
        
        assert result.lot_size == 1
        assert result.status == LotSizeFetchStatus.EQUITY_DEFAULT
        assert result.exchange == "NSE"
    
    def test_bse_lot_size_equity(self):
        """BSE lot size should always be 1 (equity)."""
        result = get_lot_size_with_status("TCS", "BSE")
        
        assert result.lot_size == 1
        assert result.status == LotSizeFetchStatus.EQUITY_DEFAULT
        assert result.exchange == "BSE"
    
    @patch("services.smart_trade_rules_service.get_symbol_info")
    def test_mcx_lot_size_success(self, mock_get_symbol_info):
        """MCX lot size should be fetched from master contract."""
        mock_symbol_info = MagicMock()
        mock_symbol_info.lotsize = 100
        mock_get_symbol_info.return_value = mock_symbol_info
        
        result = get_lot_size_with_status("CRUDEOIL24FEB6000CE", "MCX")
        
        assert result.lot_size == 100
        assert result.status == LotSizeFetchStatus.SUCCESS
        assert result.exchange == "MCX"
    
    @patch("services.smart_trade_rules_service.get_symbol_info")
    def test_cds_lot_size_success(self, mock_get_symbol_info):
        """CDS lot size should be fetched from master contract."""
        mock_symbol_info = MagicMock()
        mock_symbol_info.lotsize = 1000
        mock_get_symbol_info.return_value = mock_symbol_info
        
        result = get_lot_size_with_status("USDINR24FEB8200CE", "CDS")
        
        assert result.lot_size == 1000
        assert result.status == LotSizeFetchStatus.SUCCESS
        assert result.exchange == "CDS"


class TestIntegrationScenarios:
    """Integration tests for realistic trading scenarios."""
    
    def _create_position_result(self, qty: int):
        return PositionFetchResult(quantity=qty, status=PositionFetchStatus.SUCCESS)
    
    def _create_order_data(self, **kwargs):
        defaults = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS"
        }
        defaults.update(kwargs)
        return defaults
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_scenario_reduce_large_position_in_steps(self, mock_rules):
        """Scenario: Reducing a large position in multiple steps should all pass."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Start with 500 qty (above limit), reduce in steps
        for sell_qty, remaining in [(100, 400), (100, 300), (100, 200), (100, 100)]:
            order_data = self._create_order_data(action="SELL", quantity=sell_qty)
            position_result = self._create_position_result(remaining + sell_qty)
            
            is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
            assert is_valid is True, f"Failed at remaining={remaining}: {error}"
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_scenario_build_position_up_to_limit(self, mock_rules):
        """Scenario: Building a position up to the limit."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Build from 0 to 100 in steps
        for buy_qty, current in [(25, 0), (25, 25), (25, 50), (25, 75)]:
            order_data = self._create_order_data(action="BUY", quantity=buy_qty)
            position_result = self._create_position_result(current)
            
            is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
            assert is_valid is True, f"Failed at current={current}: {error}"
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_scenario_reverse_position(self, mock_rules):
        """Scenario: Reversing from long to short."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Start with 50 long, sell 100 to become 50 short
        order_data = self._create_order_data(action="SELL", quantity=100)
        position_result = self._create_position_result(50)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        assert is_valid is True  # 50 short is within 100 limit
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_scenario_reverse_exceeds_limit(self, mock_rules):
        """Scenario: Reversing from long to short that exceeds limit."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 50,
        }
        
        # Start with 50 long, sell 150 to become 100 short (exceeds 50 limit)
        order_data = self._create_order_data(action="SELL", quantity=150)
        position_result = self._create_position_result(50)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        assert is_valid is False
        assert "SHORT" in error


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def _create_position_result(self, qty: int):
        return PositionFetchResult(quantity=qty, status=PositionFetchStatus.SUCCESS)
    
    def _create_order_data(self, **kwargs):
        defaults = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS"
        }
        defaults.update(kwargs)
        return defaults
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_position_at_exact_limit(self, mock_rules):
        """Position at exact limit should pass."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Current 100, selling 50 to reduce to 50 (within limit)
        order_data = self._create_order_data(action="SELL", quantity=50)
        position_result = self._create_position_result(100)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_position_just_over_limit(self, mock_rules):
        """Position just over limit should fail."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": 100,
        }
        
        # Current 100, buying 1 to increase to 101 (exceeds limit)
        order_data = self._create_order_data(action="BUY", quantity=1)
        position_result = self._create_position_result(100)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is False
        assert "Maximum position size exceeded" in error
        assert "101" in error
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_smart_trade_disabled(self, mock_rules):
        """Smart trade disabled should allow all orders."""
        mock_rules.return_value = {
            "smart_trade_enabled": False,
            "max_position_size": 50,
        }
        
        # Current 0, buying 1000 (would exceed limit if enabled)
        order_data = self._create_order_data(action="BUY", quantity=1000)
        position_result = self._create_position_result(0)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None
    
    @patch("services.smart_trade_rules_service.get_smart_trade_rules")
    def test_no_max_position_size_set(self, mock_rules):
        """No max position size set should allow all orders."""
        mock_rules.return_value = {
            "smart_trade_enabled": True,
            "max_position_size": None,
        }
        
        # Current 0, buying 1000 (no limit)
        order_data = self._create_order_data(action="BUY", quantity=1000)
        position_result = self._create_position_result(0)
        
        is_valid, error = validate_against_smart_trade_rules(order_data, position_result)
        
        assert is_valid is True
        assert error is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
