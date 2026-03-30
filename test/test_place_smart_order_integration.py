"""
Integration tests for Place Smart Order Service with Smart Trade Rules

Tests cover:
- Position fetch with retry logic
- Smart trade rules integration
- Order validation
- Price discovery
- Zerodha API mocking
"""

import pytest
from unittest.mock import patch, MagicMock, call
import time

from services.place_smart_order_service import (
    _fetch_position_for_validation,
    validate_smart_order,
    place_smart_order_with_auth,
    place_smart_order,
)
from services.smart_trade_rules_service import (
    PositionFetchStatus,
    PositionFetchResult,
)


class TestPositionFetchForValidation:
    """Tests for _fetch_position_for_validation function."""
    
    @patch("services.place_smart_order_service.import_broker_module")
    def test_position_fetch_success(self, mock_import_broker):
        """Successful position fetch should return quantity."""
        mock_broker_module = MagicMock()
        mock_broker_module.get_open_position.return_value = "100"
        mock_import_broker.return_value = mock_broker_module
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product_type": "MIS"
        }
        
        result = _fetch_position_for_validation("zerodha", order_data, "test_token")
        
        assert result.quantity == 100
        assert result.status == PositionFetchStatus.SUCCESS
        assert result.error_message is None
        mock_broker_module.get_open_position.assert_called_once_with(
            "RELIANCE", "NSE", "MIS", "test_token"
        )
    
    @patch("services.place_smart_order_service.import_broker_module")
    def test_position_fetch_zero(self, mock_import_broker):
        """Position fetch returning zero should work."""
        mock_broker_module = MagicMock()
        mock_broker_module.get_open_position.return_value = "0"
        mock_import_broker.return_value = mock_broker_module
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product_type": "MIS"
        }
        
        result = _fetch_position_for_validation("zerodha", order_data, "test_token")
        
        assert result.quantity == 0
        assert result.status == PositionFetchStatus.SUCCESS
        assert result.error_message is None
    
    @patch("services.place_smart_order_service.import_broker_module")
    def test_position_fetch_negative(self, mock_import_broker):
        """Position fetch returning negative (short position) should work."""
        mock_broker_module = MagicMock()
        mock_broker_module.get_open_position.return_value = "-50"
        mock_import_broker.return_value = mock_broker_module
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product_type": "MIS"
        }
        
        result = _fetch_position_for_validation("zerodha", order_data, "test_token")
        
        assert result.quantity == -50
        assert result.status == PositionFetchStatus.SUCCESS
        assert result.error_message is None
    
    @patch("services.place_smart_order_service.import_broker_module")
    def test_position_fetch_empty_string(self, mock_import_broker):
        """Position fetch returning empty string should return 0."""
        mock_broker_module = MagicMock()
        mock_broker_module.get_open_position.return_value = ""
        mock_import_broker.return_value = mock_broker_module
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product_type": "MIS"
        }
        
        result = _fetch_position_for_validation("zerodha", order_data, "test_token")
        
        assert result.quantity == 0
        assert result.status == PositionFetchStatus.SUCCESS
        assert result.error_message is None
    
    @patch("services.place_smart_order_service.import_broker_module")
    def test_position_fetch_none(self, mock_import_broker):
        """Position fetch returning None should return 0."""
        mock_broker_module = MagicMock()
        mock_broker_module.get_open_position.return_value = None
        mock_import_broker.return_value = mock_broker_module
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product_type": "MIS"
        }
        
        result = _fetch_position_for_validation("zerodha", order_data, "test_token")
        
        assert result.quantity == 0
        assert result.status == PositionFetchStatus.SUCCESS
        assert result.error_message is None
    
    @patch("services.place_smart_order_service.import_broker_module")
    def test_position_fetch_not_supported(self, mock_import_broker):
        """Broker not supporting position fetch should return NOT_SUPPORTED."""
        mock_broker_module = MagicMock()
        del mock_broker_module.get_open_position  # Remove the attribute
        mock_import_broker.return_value = mock_broker_module
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product_type": "MIS"
        }
        
        result = _fetch_position_for_validation("zerodha", order_data, "test_token")
        
        assert result.quantity == 0
        assert result.status == PositionFetchStatus.NOT_SUPPORTED
        assert "not supported" in result.error_message.lower()
    
    @patch("services.place_smart_order_service.import_broker_module")
    def test_position_fetch_failure(self, mock_import_broker):
        """Position fetch failure should return FAILED status."""
        mock_broker_module = MagicMock()
        mock_broker_module.get_open_position.side_effect = Exception("API error")
        mock_import_broker.return_value = mock_broker_module
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product_type": "MIS"
        }
        
        result = _fetch_position_for_validation("zerodha", order_data, "test_token")
        
        assert result.quantity == 0
        assert result.status == PositionFetchStatus.FAILED
        assert "API error" in result.error_message
    
    @patch("services.place_smart_order_service.time.sleep")
    @patch("services.place_smart_order_service.import_broker_module")
    def test_position_fetch_retry_success(self, mock_import_broker, mock_sleep):
        """Position fetch should retry on failure and succeed."""
        mock_broker_module = MagicMock()
        # First call fails, second call succeeds
        mock_broker_module.get_open_position.side_effect = [
            Exception("Temporary error"),
            "100"
        ]
        mock_import_broker.return_value = mock_broker_module
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product_type": "MIS"
        }
        
        result = _fetch_position_for_validation("zerodha", order_data, "test_token")
        
        assert result.quantity == 100
        assert result.status == PositionFetchStatus.SUCCESS
        assert result.error_message is None
        assert mock_broker_module.get_open_position.call_count == 2
        mock_sleep.assert_called_once()
    
    @patch("services.place_smart_order_service.time.sleep")
    @patch("services.place_smart_order_service.import_broker_module")
    def test_position_fetch_max_retries(self, mock_import_broker, mock_sleep):
        """Position fetch should fail after max retries."""
        mock_broker_module = MagicMock()
        mock_broker_module.get_open_position.side_effect = Exception("Persistent error")
        mock_import_broker.return_value = mock_broker_module
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product_type": "MIS"
        }
        
        result = _fetch_position_for_validation("zerodha", order_data, "test_token")
        
        assert result.quantity == 0
        assert result.status == PositionFetchStatus.FAILED
        assert "Persistent error" in result.error_message
        # Max retries = 2, so total calls = 3 (initial + 2 retries)
        assert mock_broker_module.get_open_position.call_count == 3
        assert mock_sleep.call_count == 2


class TestValidateSmartOrder:
    """Tests for validate_smart_order function."""
    
    def test_valid_order(self):
        """Valid order should pass validation."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 100
        }
        
        is_valid, error = validate_smart_order(order_data)
        
        assert is_valid is True
        assert error is None
    
    def test_missing_symbol(self):
        """Missing symbol should fail validation."""
        order_data = {
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 100
        }
        
        is_valid, error = validate_smart_order(order_data)
        
        assert is_valid is False
        assert "symbol" in error.lower()
    
    def test_missing_exchange(self):
        """Missing exchange should fail validation."""
        order_data = {
            "symbol": "RELIANCE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 100
        }
        
        is_valid, error = validate_smart_order(order_data)
        
        assert is_valid is False
        assert "exchange" in error.lower()
    
    def test_invalid_exchange(self):
        """Invalid exchange should fail validation."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "INVALID",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 100
        }
        
        is_valid, error = validate_smart_order(order_data)
        
        assert is_valid is False
        assert "exchange" in error.lower()
    
    def test_invalid_action(self):
        """Invalid action should fail validation."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "INVALID",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 100
        }
        
        is_valid, error = validate_smart_order(order_data)
        
        assert is_valid is False
        assert "action" in error.lower()
    
    def test_lowercase_action(self):
        """Lowercase action should be converted to uppercase."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "buy",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 100
        }
        
        is_valid, error = validate_smart_order(order_data)
        
        assert is_valid is True
        assert error is None
        assert order_data["action"] == "BUY"
    
    def test_invalid_product_type(self):
        """Invalid product type should fail validation."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "INVALID",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 100
        }
        
        is_valid, error = validate_smart_order(order_data)
        
        assert is_valid is False
        assert "product" in error.lower()


class TestPlaceSmartOrderWithAuth:
    """Tests for place_smart_order_with_auth function."""
    
    @patch("services.place_smart_order_service.socketio")
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_smart_trade_rules_pass(self, mock_analyze_mode, mock_validate_smart_order, 
                                     mock_fetch_position, mock_validate_rules, mock_socketio):
        """Order passing smart trade rules should proceed."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_fetch_position.return_value = PositionFetchResult(
            quantity=0, status=PositionFetchStatus.SUCCESS
        )
        mock_validate_rules.return_value = (True, None)
        mock_socketio.start_background_task = MagicMock()
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 100
        }
        
        # Mock broker module
        with patch("services.place_smart_order_service.import_broker_module") as mock_import_broker:
            mock_broker_module = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 200
            mock_broker_module.place_smartorder_api.return_value = (
                mock_response, {"status": "success"}, "ORDER123"
            )
            mock_import_broker.return_value = mock_broker_module
            
            success, response, status_code = place_smart_order_with_auth(
                order_data, "test_token", "zerodha", order_data
            )
            
            assert success is True
            assert status_code == 200
            mock_validate_rules.assert_called_once()
    
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_smart_trade_rules_fail(self, mock_analyze_mode, mock_validate_smart_order,
                                     mock_fetch_position, mock_validate_rules):
        """Order failing smart trade rules should be blocked."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_fetch_position.return_value = PositionFetchResult(
            quantity=100, status=PositionFetchStatus.SUCCESS
        )
        mock_validate_rules.return_value = (False, "Smart Trade Rule: Duplicate BUY blocked")
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 50,
            "price": 100.0,
            "product_type": "MIS"
        }
        
        success, response, status_code = place_smart_order_with_auth(
            order_data, "test_token", "zerodha", order_data
        )
        
        assert success is False
        assert status_code == 400
        assert "Duplicate BUY blocked" in response["message"]
        mock_validate_rules.assert_called_once()
    
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_position_fetch_failed_with_rules_enabled(self, mock_analyze_mode, mock_validate_smart_order,
                                                       mock_fetch_position, mock_validate_rules):
        """Position fetch failed with rules enabled should block order."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_fetch_position.return_value = PositionFetchResult(
            quantity=0, status=PositionFetchStatus.FAILED, error_message="API error"
        )
        mock_validate_rules.return_value = (False, "Smart Trade Rule: Cannot validate order - position fetch failed")
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS"
        }
        
        success, response, status_code = place_smart_order_with_auth(
            order_data, "test_token", "zerodha", order_data
        )
        
        assert success is False
        assert status_code == 400
        assert "position fetch failed" in response["message"].lower()
        mock_validate_rules.assert_called_once()
    
    @patch("services.place_smart_order_service.socketio")
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_smart_trade_rules_disabled(self, mock_analyze_mode, mock_validate_smart_order,
                                        mock_fetch_position, mock_validate_rules, mock_socketio):
        """Smart trade rules disabled should allow all orders."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_fetch_position.return_value = PositionFetchResult(
            quantity=0, status=PositionFetchStatus.SUCCESS
        )
        mock_validate_rules.return_value = (True, None)  # Rules disabled
        mock_socketio.start_background_task = MagicMock()
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 1000,  # Large quantity
            "price": 100.0,
            "product_type": "MIS",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 1000
        }
        
        # Mock broker module
        with patch("services.place_smart_order_service.import_broker_module") as mock_import_broker:
            mock_broker_module = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 200
            mock_broker_module.place_smartorder_api.return_value = (
                mock_response, {"status": "success"}, "ORDER123"
            )
            mock_import_broker.return_value = mock_broker_module
            
            success, response, status_code = place_smart_order_with_auth(
                order_data, "test_token", "zerodha", order_data
            )
            
            assert success is True
            assert status_code == 200
            mock_validate_rules.assert_called_once()


class TestPlaceSmartOrder:
    """Tests for place_smart_order function."""
    
    @patch("services.place_smart_order_service.get_auth_token_broker")
    @patch("services.place_smart_order_service.place_smart_order_with_auth")
    def test_api_key_authentication(self, mock_place_with_auth, mock_get_auth):
        """API key authentication should work."""
        mock_get_auth.return_value = ("test_token", "zerodha")
        mock_place_with_auth.return_value = (True, {"status": "success"}, 200)
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS"
        }
        
        success, response, status_code = place_smart_order(
            order_data, api_key="test_api_key"
        )
        
        assert success is True
        assert status_code == 200
        mock_get_auth.assert_called_once_with("test_api_key")
        mock_place_with_auth.assert_called_once()
    
    @patch("services.place_smart_order_service.get_auth_token_broker")
    def test_invalid_api_key(self, mock_get_auth):
        """Invalid API key should return 403."""
        mock_get_auth.return_value = (None, None)
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS"
        }
        
        success, response, status_code = place_smart_order(
            order_data, api_key="invalid_api_key"
        )
        
        assert success is False
        assert status_code == 403
        assert "Invalid openalgo apikey" in response["message"]
    
    @patch("services.place_smart_order_service.place_smart_order_with_auth")
    def test_direct_authentication(self, mock_place_with_auth):
        """Direct authentication with auth_token and broker should work."""
        mock_place_with_auth.return_value = (True, {"status": "success"}, 200)
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS"
        }
        
        success, response, status_code = place_smart_order(
            order_data, auth_token="test_token", broker="zerodha"
        )
        
        assert success is True
        assert status_code == 200
        mock_place_with_auth.assert_called_once()
    
    def test_missing_authentication(self):
        """Missing authentication should return 400."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 100,
            "price": 100.0,
            "product_type": "MIS"
        }
        
        success, response, status_code = place_smart_order(order_data)
        
        assert success is False
        assert status_code == 400
        assert "Either api_key or both auth_token and broker must be provided" in response["message"]


class TestZerodhaAPIMocking:
    """Tests for Zerodha API mocking scenarios."""
    
    @patch("services.place_smart_order_service.socketio")
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_zerodha_order_placement_success(self, mock_analyze_mode, mock_validate_smart_order,
                                              mock_fetch_position, mock_validate_rules, mock_socketio):
        """Zerodha order placement success scenario."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_fetch_position.return_value = PositionFetchResult(
            quantity=0, status=PositionFetchStatus.SUCCESS
        )
        mock_validate_rules.return_value = (True, None)
        mock_socketio.start_background_task = MagicMock()
        
        order_data = {
            "symbol": "NIFTY24FEB18000CE",
            "exchange": "NFO",
            "action": "BUY",
            "quantity": 50,
            "price": 100.0,
            "product_type": "NRML",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 50
        }
        
        # Mock Zerodha broker module
        with patch("services.place_smart_order_service.import_broker_module") as mock_import_broker:
            mock_broker_module = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 200
            mock_broker_module.place_smartorder_api.return_value = (
                mock_response, {"status": "success"}, "ORDER123"
            )
            mock_import_broker.return_value = mock_broker_module
            
            success, response, status_code = place_smart_order_with_auth(
                order_data, "test_token", "zerodha", order_data
            )
            
            assert success is True
            assert status_code == 200
            assert response["orderid"] == "ORDER123"
            mock_broker_module.place_smartorder_api.assert_called_once()
    
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_zerodha_duplicate_buy_blocked(self, mock_analyze_mode, mock_validate_smart_order,
                                           mock_fetch_position, mock_validate_rules):
        """Zerodha duplicate BUY should be blocked by smart trade rules."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_fetch_position.return_value = PositionFetchResult(
            quantity=100, status=PositionFetchStatus.SUCCESS  # Existing long position
        )
        mock_validate_rules.return_value = (False, "Smart Trade Rule: Duplicate BUY blocked. You already have a long position of 100 in RELIANCE")
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 50,
            "price": 100.0,
            "product_type": "MIS"
        }
        
        success, response, status_code = place_smart_order_with_auth(
            order_data, "test_token", "zerodha", order_data
        )
        
        assert success is False
        assert status_code == 400
        assert "Duplicate BUY blocked" in response["message"]
        mock_validate_rules.assert_called_once()
    
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_zerodha_max_position_exceeded(self, mock_analyze_mode, mock_validate_smart_order,
                                           mock_fetch_position, mock_validate_rules):
        """Zerodha max position exceeded should be blocked."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_fetch_position.return_value = PositionFetchResult(
            quantity=0, status=PositionFetchStatus.SUCCESS
        )
        mock_validate_rules.return_value = (False, "Smart Trade Rule: Maximum position size exceeded. Limit: 100 qty, New LONG position would be: 150 qty")
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 150,
            "price": 100.0,
            "product_type": "MIS"
        }
        
        success, response, status_code = place_smart_order_with_auth(
            order_data, "test_token", "zerodha", order_data
        )
        
        assert success is False
        assert status_code == 400
        assert "Maximum position size exceeded" in response["message"]
        mock_validate_rules.assert_called_once()
    
    @patch("services.place_smart_order_service.socketio")
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_zerodha_reduce_position_allowed(self, mock_analyze_mode, mock_validate_smart_order,
                                             mock_fetch_position, mock_validate_rules, mock_socketio):
        """Zerodha reduce position should be allowed even if over limit."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_fetch_position.return_value = PositionFetchResult(
            quantity=150, status=PositionFetchStatus.SUCCESS  # Over limit
        )
        mock_validate_rules.return_value = (True, None)  # Reducing skips limit check
        mock_socketio.start_background_task = MagicMock()
        
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "SELL",
            "quantity": 50,
            "price": 100.0,
            "product_type": "MIS",
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "position_size": 100
        }
        
        # Mock Zerodha broker module
        with patch("services.place_smart_order_service.import_broker_module") as mock_import_broker:
            mock_broker_module = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 200
            mock_broker_module.place_smartorder_api.return_value = (
                mock_response, {"status": "success"}, "ORDER123"
            )
            mock_import_broker.return_value = mock_broker_module
            
            success, response, status_code = place_smart_order_with_auth(
                order_data, "test_token", "zerodha", order_data
            )
            
            assert success is True
            assert status_code == 200
            mock_validate_rules.assert_called_once()


class TestSequentialOrderLimitEnforcement:
    """Tests for sequential buy orders with max position limit enforcement."""
    
    @patch("services.place_smart_order_service.socketio")
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_sequential_buy_orders_equity_within_limit(self, mock_analyze_mode, mock_validate_smart_order,
                                                        mock_fetch_position, mock_validate_rules, mock_socketio):
        """Sequential buy orders within limit should all succeed."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_socketio.start_background_task = MagicMock()
        
        # Track cumulative position
        cumulative_position = 0
        max_position_limit = 500
        
        # Mock broker module
        with patch("services.place_smart_order_service.import_broker_module") as mock_import_broker:
            mock_broker_module = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 200
            mock_broker_module.place_smartorder_api.return_value = (
                mock_response, {"status": "success"}, "ORDER123"
            )
            mock_import_broker.return_value = mock_broker_module
            
            # Send 5 buy orders of 100 each (total 500, within limit)
            for i in range(5):
                # Mock position fetch to return current cumulative position
                mock_fetch_position.return_value = PositionFetchResult(
                    quantity=cumulative_position, status=PositionFetchStatus.SUCCESS
                )
                
                # Mock validation to check against limit
                def validate_side_effect(order_data, position_result, broker=None):
                    new_position = position_result.quantity + order_data["quantity"]
                    if new_position > max_position_limit:
                        return False, f"Smart Trade Rule: Maximum position size exceeded. Limit: {max_position_limit} qty, New LONG position would be: {new_position} qty"
                    return True, None
                
                mock_validate_rules.side_effect = validate_side_effect
                
                order_data = {
                    "symbol": "RELIANCE",
                    "exchange": "NSE",
                    "action": "BUY",
                    "quantity": 100,
                    "price": 100.0,
                    "product_type": "MIS",
                    "apikey": "test_api_key",
                    "strategy": "test_strategy",
                    "position_size": cumulative_position + 100
                }
                
                success, response, status_code = place_smart_order_with_auth(
                    order_data, "test_token", "zerodha", order_data
                )
                
                assert success is True, f"Order {i+1} should succeed"
                assert status_code == 200
                
                # Update cumulative position
                cumulative_position += 100
    
    @patch("services.place_smart_order_service.socketio")
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_sequential_buy_orders_equity_exceeds_limit(self, mock_analyze_mode, mock_validate_smart_order,
                                                         mock_fetch_position, mock_validate_rules, mock_socketio):
        """Sequential buy orders exceeding limit should be blocked."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_socketio.start_background_task = MagicMock()
        
        # Track cumulative position
        cumulative_position = 0
        max_position_limit = 350
        
        # Mock broker module
        with patch("services.place_smart_order_service.import_broker_module") as mock_import_broker:
            mock_broker_module = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 200
            mock_broker_module.place_smartorder_api.return_value = (
                mock_response, {"status": "success"}, "ORDER123"
            )
            mock_import_broker.return_value = mock_broker_module
            
            # Send 4 buy orders of 100 each (total 400, exceeds limit of 350)
            for i in range(4):
                # Mock position fetch to return current cumulative position
                mock_fetch_position.return_value = PositionFetchResult(
                    quantity=cumulative_position, status=PositionFetchStatus.SUCCESS
                )
                
                # Mock validation to check against limit
                def validate_side_effect(order_data, position_result, broker=None):
                    new_position = position_result.quantity + order_data["quantity"]
                    if new_position > max_position_limit:
                        return False, f"Smart Trade Rule: Maximum position size exceeded. Limit: {max_position_limit} qty, New LONG position would be: {new_position} qty"
                    return True, None
                
                mock_validate_rules.side_effect = validate_side_effect
                
                order_data = {
                    "symbol": "RELIANCE",
                    "exchange": "NSE",
                    "action": "BUY",
                    "quantity": 100,
                    "price": 100.0,
                    "product_type": "MIS",
                    "apikey": "test_api_key",
                    "strategy": "test_strategy",
                    "position_size": cumulative_position + 100
                }
                
                success, response, status_code = place_smart_order_with_auth(
                    order_data, "test_token", "zerodha", order_data
                )
                
                if i < 3:  # First 3 orders should succeed (0, 100, 200, 300)
                    assert success is True, f"Order {i+1} should succeed"
                    assert status_code == 200
                    cumulative_position += 100
                else:  # 4th order should fail (400 > 350)
                    assert success is False, f"Order {i+1} should be blocked"
                    assert status_code == 400
                    assert "Maximum position size exceeded" in response["message"]
    
    @patch("services.place_smart_order_service.socketio")
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_sequential_buy_orders_fo_within_limit(self, mock_analyze_mode, mock_validate_smart_order,
                                                    mock_fetch_position, mock_validate_rules, mock_socketio):
        """Sequential buy orders for F&O within lot limit should all succeed."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_socketio.start_background_task = MagicMock()
        
        # Track cumulative position (in quantity)
        cumulative_position = 0
        lot_size = 50
        max_lots_limit = 3
        max_quantity_limit = max_lots_limit * lot_size  # 150
        
        # Mock broker module
        with patch("services.place_smart_order_service.import_broker_module") as mock_import_broker:
            mock_broker_module = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 200
            mock_broker_module.place_smartorder_api.return_value = (
                mock_response, {"status": "success"}, "ORDER123"
            )
            mock_import_broker.return_value = mock_broker_module
            
            # Send 3 buy orders of 50 each (1 lot each, total 3 lots, within limit)
            for i in range(3):
                # Mock position fetch to return current cumulative position
                mock_fetch_position.return_value = PositionFetchResult(
                    quantity=cumulative_position, status=PositionFetchStatus.SUCCESS
                )
                
                # Mock validation to check against limit in lots
                def validate_side_effect(order_data, position_result, broker=None):
                    new_position = position_result.quantity + order_data["quantity"]
                    new_lots = new_position / lot_size
                    if new_lots > max_lots_limit:
                        return False, f"Smart Trade Rule: Maximum position size exceeded. Limit: {max_lots_limit} lots ({max_quantity_limit} qty), New LONG position would be: {new_lots:.2f} lots ({new_position} qty)"
                    return True, None
                
                mock_validate_rules.side_effect = validate_side_effect
                
                order_data = {
                    "symbol": "NIFTY24JAN22000CE",
                    "exchange": "NFO",
                    "action": "BUY",
                    "quantity": 50,
                    "price": 100.0,
                    "product_type": "NRML",
                    "apikey": "test_api_key",
                    "strategy": "test_strategy",
                    "position_size": cumulative_position + 50
                }
                
                success, response, status_code = place_smart_order_with_auth(
                    order_data, "test_token", "zerodha", order_data
                )
                
                assert success is True, f"Order {i+1} should succeed"
                assert status_code == 200
                
                # Update cumulative position
                cumulative_position += 50
    
    @patch("services.place_smart_order_service.socketio")
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_sequential_buy_orders_fo_exceeds_limit(self, mock_analyze_mode, mock_validate_smart_order,
                                                     mock_fetch_position, mock_validate_rules, mock_socketio):
        """Sequential buy orders for F&O exceeding lot limit should be blocked."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_socketio.start_background_task = MagicMock()
        
        # Track cumulative position (in quantity)
        cumulative_position = 0
        lot_size = 50
        max_lots_limit = 2
        max_quantity_limit = max_lots_limit * lot_size  # 100
        
        # Mock broker module
        with patch("services.place_smart_order_service.import_broker_module") as mock_import_broker:
            mock_broker_module = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 200
            mock_broker_module.place_smartorder_api.return_value = (
                mock_response, {"status": "success"}, "ORDER123"
            )
            mock_import_broker.return_value = mock_broker_module
            
            # Send 3 buy orders of 50 each (1 lot each, total 3 lots, exceeds limit of 2)
            for i in range(3):
                # Mock position fetch to return current cumulative position
                mock_fetch_position.return_value = PositionFetchResult(
                    quantity=cumulative_position, status=PositionFetchStatus.SUCCESS
                )
                
                # Mock validation to check against limit in lots
                def validate_side_effect(order_data, position_result, broker=None):
                    new_position = position_result.quantity + order_data["quantity"]
                    new_lots = new_position / lot_size
                    if new_lots > max_lots_limit:
                        return False, f"Smart Trade Rule: Maximum position size exceeded. Limit: {max_lots_limit} lots ({max_quantity_limit} qty), New LONG position would be: {new_lots:.2f} lots ({new_position} qty)"
                    return True, None
                
                mock_validate_rules.side_effect = validate_side_effect
                
                order_data = {
                    "symbol": "NIFTY24JAN22000CE",
                    "exchange": "NFO",
                    "action": "BUY",
                    "quantity": 50,
                    "price": 100.0,
                    "product_type": "NRML",
                    "apikey": "test_api_key",
                    "strategy": "test_strategy",
                    "position_size": cumulative_position + 50
                }
                
                success, response, status_code = place_smart_order_with_auth(
                    order_data, "test_token", "zerodha", order_data
                )
                
                if i < 2:  # First 2 orders should succeed (0, 50, 100)
                    assert success is True, f"Order {i+1} should succeed"
                    assert status_code == 200
                    cumulative_position += 50
                else:  # 3rd order should fail (150 > 100)
                    assert success is False, f"Order {i+1} should be blocked"
                    assert status_code == 400
                    assert "Maximum position size exceeded" in response["message"]
    
    @patch("services.place_smart_order_service.socketio")
    @patch("services.place_smart_order_service.validate_against_smart_trade_rules")
    @patch("services.place_smart_order_service._fetch_position_for_validation")
    @patch("services.place_smart_order_service.validate_smart_order")
    @patch("services.place_smart_order_service.get_analyze_mode")
    def test_sequential_buy_orders_with_reduce_allowed(self, mock_analyze_mode, mock_validate_smart_order,
                                                        mock_fetch_position, mock_validate_rules, mock_socketio):
        """Sequential orders: buy to limit, then reduce should be allowed."""
        mock_analyze_mode.return_value = False
        mock_validate_smart_order.return_value = (True, None)
        mock_socketio.start_background_task = MagicMock()
        
        # Track cumulative position
        cumulative_position = 0
        max_position_limit = 300
        
        # Mock broker module
        with patch("services.place_smart_order_service.import_broker_module") as mock_import_broker:
            mock_broker_module = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 200
            mock_broker_module.place_smartorder_api.return_value = (
                mock_response, {"status": "success"}, "ORDER123"
            )
            mock_import_broker.return_value = mock_broker_module
            
            # Step 1: Buy 300 (reach limit)
            mock_fetch_position.return_value = PositionFetchResult(
                quantity=cumulative_position, status=PositionFetchStatus.SUCCESS
            )
            
            def validate_side_effect(order_data, position_result, broker=None):
                action = order_data["action"]
                quantity = order_data["quantity"]
                current = position_result.quantity
                
                if action == "BUY":
                    new_position = current + quantity
                else:  # SELL
                    new_position = current - quantity
                
                # Check if reducing (SELL when long)
                if action == "SELL" and current > 0:
                    # Reducing position - always allowed
                    return True, None
                
                # Check limit for increasing/opening positions
                if abs(new_position) > max_position_limit:
                    return False, f"Smart Trade Rule: Maximum position size exceeded. Limit: {max_position_limit} qty, New LONG position would be: {new_position} qty"
                return True, None
            
            mock_validate_rules.side_effect = validate_side_effect
            
            order_data = {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": 300,
                "price": 100.0,
                "product_type": "MIS",
                "apikey": "test_api_key",
                "strategy": "test_strategy",
                "position_size": 300
            }
            
            success, response, status_code = place_smart_order_with_auth(
                order_data, "test_token", "zerodha", order_data
            )
            
            assert success is True, "Initial buy to limit should succeed"
            assert status_code == 200
            cumulative_position = 300
            
            # Step 2: Try to buy 100 more (should fail - exceeds limit)
            mock_fetch_position.return_value = PositionFetchResult(
                quantity=cumulative_position, status=PositionFetchStatus.SUCCESS
            )
            
            order_data = {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": 100,
                "price": 100.0,
                "product_type": "MIS",
                "apikey": "test_api_key",
                "strategy": "test_strategy",
                "position_size": 400
            }
            
            success, response, status_code = place_smart_order_with_auth(
                order_data, "test_token", "zerodha", order_data
            )
            
            assert success is False, "Buy exceeding limit should be blocked"
            assert status_code == 400
            assert "Maximum position size exceeded" in response["message"]
            
            # Step 3: Sell 100 (reduce position - should succeed)
            mock_fetch_position.return_value = PositionFetchResult(
                quantity=cumulative_position, status=PositionFetchStatus.SUCCESS
            )
            
            order_data = {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "action": "SELL",
                "quantity": 100,
                "price": 100.0,
                "product_type": "MIS",
                "apikey": "test_api_key",
                "strategy": "test_strategy",
                "position_size": 200
            }
            
            success, response, status_code = place_smart_order_with_auth(
                order_data, "test_token", "zerodha", order_data
            )
            
            assert success is True, "Reduce position should be allowed"
            assert status_code == 200
            cumulative_position = 200
            
            # Step 4: Buy 100 again (should succeed - back to limit)
            mock_fetch_position.return_value = PositionFetchResult(
                quantity=cumulative_position, status=PositionFetchStatus.SUCCESS
            )
            
            order_data = {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": 100,
                "price": 100.0,
                "product_type": "MIS",
                "apikey": "test_api_key",
                "strategy": "test_strategy",
                "position_size": 300
            }
            
            success, response, status_code = place_smart_order_with_auth(
                order_data, "test_token", "zerodha", order_data
            )
            
            assert success is True, "Buy back to limit should succeed"
            assert status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
