import copy
import importlib
import time
import traceback
from typing import Any, Dict, Optional, Tuple

from database.analyzer_db import async_log_analyzer
from database.apilog_db import async_log_order, executor
from database.auth_db import get_auth_token_broker
from database.settings_db import get_analyze_mode
from extensions import socketio
from services.quotes_service import get_quotes
from services.smart_trade_rules_service import (
    PositionFetchResult,
    PositionFetchStatus,
    validate_against_smart_trade_rules,
)
from services.symbol_service import get_symbol_info_with_auth
from services.telegram_alert_service import telegram_alert_service
from utils.api_analyzer import analyze_request, generate_order_id
from utils.config import get_execution_buffer
from utils.constants import (
    REQUIRED_SMART_ORDER_FIELDS,
    VALID_ACTIONS,
    VALID_EXCHANGES,
    VALID_PRICE_TYPES,
    VALID_PRODUCT_TYPES,
)
from utils.logging import get_logger
from utils.price_utils import round_price_to_tick_size

# Initialize logger
logger = get_logger(__name__)

# Smart order delay
SMART_ORDER_DELAY = "0.5"  # Default value, can be overridden by environment variable

# Position fetch configuration
POSITION_FETCH_MAX_RETRIES = 2
POSITION_FETCH_RETRY_DELAY = 0.5


def emit_analyzer_error(request_data: dict[str, Any], error_message: str) -> dict[str, Any]:
    """
    Helper function to emit analyzer error events

    Args:
        request_data: Original request data
        error_message: Error message to emit

    Returns:
        Error response dictionary
    """
    error_response = {"mode": "analyze", "status": "error", "message": error_message}

    # Store complete request data without apikey
    analyzer_request = request_data.copy()
    if "apikey" in analyzer_request:
        del analyzer_request["apikey"]
    analyzer_request["api_type"] = "placesmartorder"

    # Log to analyzer database
    executor.submit(async_log_analyzer, analyzer_request, error_response, "placesmartorder")

    # Emit socket event asynchronously (non-blocking)
    socketio.start_background_task(
        socketio.emit, "analyzer_update", {"request": analyzer_request, "response": error_response}
    )

    return error_response


def import_broker_module(broker_name: str) -> Any | None:
    """
    Dynamically import the broker-specific order API module.

    Args:
        broker_name: Name of the broker

    Returns:
        The imported module or None if import fails
    """
    try:
        module_path = f"broker.{broker_name}.api.order_api"
        broker_module = importlib.import_module(module_path)
        return broker_module
    except ImportError as error:
        logger.error(f"Error importing broker module '{module_path}': {error}")
        return None


def _fetch_position_for_validation(
    broker: str,
    order_data: dict[str, Any],
    auth_token: str,
) -> PositionFetchResult:
    """
    Fetch current position with retry logic and proper error handling.

    Args:
        broker: Broker name
        order_data: Order data containing symbol, exchange, product_type
        auth_token: Broker authentication token

    Returns:
        PositionFetchResult with quantity, status, and error message
    """
    broker_module = import_broker_module(broker)

    if not broker_module or not hasattr(broker_module, "get_open_position"):
        logger.info(f"Broker {broker} does not support position fetching")
        return PositionFetchResult(
            quantity=0,
            status=PositionFetchStatus.NOT_SUPPORTED,
            error_message="Position fetch not supported for this broker",
        )

    last_error = None
    for attempt in range(POSITION_FETCH_MAX_RETRIES + 1):
        try:
            position_qty_str = broker_module.get_open_position(
                order_data.get("symbol"),
                order_data.get("exchange"),
                order_data.get("product_type"),
                auth_token,
            )
            quantity = int(position_qty_str) if position_qty_str else 0
            logger.debug(f"Position fetch successful: {quantity} for {order_data.get('symbol')}")
            return PositionFetchResult(quantity=quantity, status=PositionFetchStatus.SUCCESS)
        except Exception as e:
            last_error = e
            logger.warning(
                f"Position fetch attempt {attempt + 1} failed for {order_data.get('symbol')}: {e}"
            )
            if attempt < POSITION_FETCH_MAX_RETRIES:
                time.sleep(POSITION_FETCH_RETRY_DELAY)

    # All retries failed
    logger.error(
        f"Position fetch failed after {POSITION_FETCH_MAX_RETRIES + 1} attempts: {last_error}"
    )
    return PositionFetchResult(
        quantity=0, status=PositionFetchStatus.FAILED, error_message=str(last_error)
    )


def validate_smart_order(order_data: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate smart order data

    Args:
        order_data: Order data to validate

    Returns:
        Tuple containing:
        - Success status (bool)
        - Error message (str) or None if validation succeeded
    """
    # Check for missing mandatory fields
    missing_fields = [field for field in REQUIRED_SMART_ORDER_FIELDS if field not in order_data]
    if missing_fields:
        return False, f"Missing mandatory field(s): {', '.join(missing_fields)}"

    # Validate exchange
    if "exchange" in order_data and order_data["exchange"] not in VALID_EXCHANGES:
        return False, f"Invalid exchange. Must be one of: {', '.join(VALID_EXCHANGES)}"

    # Convert action to uppercase and validate
    if "action" in order_data:
        order_data["action"] = order_data["action"].upper()
        if order_data["action"] not in VALID_ACTIONS:
            return (
                False,
                f"Invalid action. Must be one of: {', '.join(VALID_ACTIONS)} (case insensitive)",
            )

    # Validate price type if provided
    if "price_type" in order_data and order_data["price_type"] not in VALID_PRICE_TYPES:
        return False, f"Invalid price type. Must be one of: {', '.join(VALID_PRICE_TYPES)}"

    # Validate product type if provided
    if "product_type" in order_data and order_data["product_type"] not in VALID_PRODUCT_TYPES:
        return False, f"Invalid product type. Must be one of: {', '.join(VALID_PRODUCT_TYPES)}"

    return True, None


def place_smart_order_with_auth(
    order_data: dict[str, Any],
    auth_token: str,
    broker: str,
    original_data: dict[str, Any],
    smart_order_delay: str = SMART_ORDER_DELAY,
) -> tuple[bool, dict[str, Any], int]:
    """
    Place a smart order using provided auth token.

    Args:
        order_data: Smart order data
        auth_token: Authentication token for the broker API
        broker: Name of the broker
        original_data: Original request data for logging
        smart_order_delay: Delay in seconds between order placement and response

    Returns:
        Tuple containing:
        - Success status (bool)
        - Response data (dict)
        - HTTP status code (int)
    """
    order_request_data = copy.deepcopy(original_data)
    if "apikey" in order_request_data:
        order_request_data.pop("apikey", None)

    # Validate order data
    is_valid, error_message = validate_smart_order(order_data)
    if not is_valid:
        # Provide fallback for error_message if None
        error_msg = error_message or "Validation failed"
        if get_analyze_mode():
            return False, emit_analyzer_error(original_data, error_msg), 400
        error_response = {"status": "error", "message": error_msg}
        executor.submit(async_log_order, "placesmartorder", original_data, error_response)
        return False, error_response, 400

    # Get current position with fail-safe handling
    position_result = _fetch_position_for_validation(broker, order_data, auth_token)

    # Validate against smart trade rules
    is_valid, error_message = validate_against_smart_trade_rules(
        order_data, position_result, broker
    )

    if not is_valid:
        # Provide fallback for error_message if None
        error_msg = error_message or "Validation failed"
        if get_analyze_mode():
            return False, emit_analyzer_error(original_data, error_msg), 400
        error_response = {"status": "error", "message": error_msg}
        executor.submit(async_log_order, "placesmartorder", original_data, error_response)
        return False, error_response, 400

    # If in analyze mode, route to sandbox for virtual trading
    if get_analyze_mode():
        from services.sandbox_service import sandbox_place_smart_order

        api_key = original_data.get("apikey")
        if not api_key:
            return (
                False,
                emit_analyzer_error(original_data, "API key required for sandbox mode"),
                400,
            )

        # Route to sandbox smart order
        success, response_data, status_code = sandbox_place_smart_order(
            order_data, api_key, original_data
        )

        # Store complete request data without apikey
        analyzer_request = order_request_data.copy()
        analyzer_request["api_type"] = "placesmartorder"

        # Log to analyzer database with complete request and response
        executor.submit(async_log_analyzer, analyzer_request, response_data, "placesmartorder")

        # Emit socket event for toast notification asynchronously (non-blocking)
        socketio.start_background_task(
            socketio.emit,
            "analyzer_update",
            {"request": analyzer_request, "response": response_data},
        )

        # Send Telegram alert in background task (non-blocking)
        socketio.start_background_task(
            telegram_alert_service.send_order_alert,
            "placesmartorder",
            order_data,
            response_data,
            order_data.get("apikey"),
        )
        return success, response_data, status_code

    # Live Mode - Proceed with actual order placement
    broker_module = import_broker_module(broker)
    if broker_module is None:
        error_response = {"status": "error", "message": "Broker-specific module not found"}
        executor.submit(async_log_order, "placesmartorder", original_data, error_response)
        return False, error_response, 404

    # Price Discovery: If pricetype is LIMIT and price is 0, fetch latest quote
    pricetype = order_data.get("pricetype", "MARKET")
    price = order_data.get("price", 0)
    if pricetype == "LIMIT" and price == 0:
        action = order_data.get("action", "BUY").upper()
        logger.info(
            f"Price discovery triggered for {order_data.get('symbol')} "
            f"on {order_data.get('exchange')}"
        )

        symbol = order_data.get("symbol")
        exchange = order_data.get("exchange")
        symbol_success, symbol_response, _ = get_symbol_info_with_auth(
            symbol, exchange, auth_token, broker
        )

        tick_size = 0.05
        if symbol_success:
            symbol_data = symbol_response.get("data", {})
            tick_size = symbol_data.get("tick_size", 0.05)

        api_key = original_data.get("apikey")
        success, quote_response, _ = get_quotes(
            symbol=order_data.get("symbol"),
            exchange=order_data.get("exchange"),
            api_key=api_key,
        )

        if success:
            quote_data = quote_response.get("data", {})
            quote_ltp = quote_data.get("ltp", 0)
            quote_bid = quote_data.get("bid", 0)
            quote_ask = quote_data.get("ask", 0)

            # BUY: Use ask + buffer%, SELL: Use bid - buffer%, fallback to LTP
            execution_buffer = get_execution_buffer()
            if action == "BUY" and quote_ask > 0:
                discovered_price = quote_ask * (1 + execution_buffer)
            elif action == "SELL" and quote_bid > 0:
                discovered_price = quote_bid * (1 - execution_buffer)
            else:
                discovered_price = quote_ltp

            if discovered_price and discovered_price > 0:
                order_data["price"] = round_price_to_tick_size(discovered_price, tick_size)
                buffer_pct = round(execution_buffer * 100, 1)
                logger.info(
                    f"Price discovered for {order_data.get('symbol')}: "
                    f"{order_data['price']} ({action}, buffer={buffer_pct}%)"
                )
            else:
                logger.warning(
                    f"Invalid price from quote for {order_data.get('symbol')}: {discovered_price}"
                )
        else:
            logger.warning(
                f"Price discovery failed for {order_data.get('symbol')}: "
                f"{quote_response.get('message', 'Unknown error')}"
            )

    try:
        res, response_data, order_id = broker_module.place_smartorder_api(order_data, auth_token)

        # Handle case where position size matches current position
        if (
            res is None
            and response_data.get("status") == "success"
            and "No action needed" in response_data.get("message", "")
        ):
            # Log the no-action-needed case
            order_response_data = {
                "status": "success",
                "message": "Positions Already Matched. No Action needed.",
            }
            executor.submit(
                async_log_order, "placesmartorder", order_request_data, order_response_data
            )

            # Emit notification for matched positions asynchronously (non-blocking)
            socketio.start_background_task(
                socketio.emit,
                "order_notification",
                {
                    "symbol": order_data.get("symbol"),
                    "status": "info",
                    "message": " Positions Already Matched. No Action needed.",
                },
            )
            # Send Telegram alert in background task (non-blocking)
            socketio.start_background_task(
                telegram_alert_service.send_order_alert,
                "placesmartorder",
                order_data,
                order_response_data,
                original_data.get("apikey"),
            )
            return True, order_response_data, 200

        # Log successful order immediately after placement
        if res and res.status == 200:
            order_response_data = {"status": "success", "orderid": order_id}
            executor.submit(
                async_log_order, "placesmartorder", order_request_data, order_response_data
            )
            # Send Telegram alert in background task (non-blocking)
            socketio.start_background_task(
                telegram_alert_service.send_order_alert,
                "placesmartorder",
                order_data,
                order_response_data,
                original_data.get("apikey"),
            )
            # Emit SocketIO event asynchronously (non-blocking)
            socketio.start_background_task(
                socketio.emit,
                "order_event",
                {
                    "symbol": order_data.get("symbol"),
                    "action": order_data.get("action"),
                    "orderid": order_id,
                    "mode": "live",
                },
            )

    except Exception as e:
        logger.error(f"Error in broker_module.place_smartorder_api: {e}")
        traceback.print_exc()
        error_response = {
            "status": "error",
            "message": "Failed to place smart order due to internal error",
        }
        executor.submit(async_log_order, "placesmartorder", original_data, error_response)
        return False, error_response, 500

    # Add delay if needed
    try:
        time.sleep(float(smart_order_delay))
    except Exception:
        logger.error(f"Invalid SMART_ORDER_DELAY value: {smart_order_delay}")
        traceback.print_exc()

    if res and res.status == 200:
        return True, order_response_data, 200
    else:
        message = (
            response_data.get("message", "Failed to place smart order")
            if isinstance(response_data, dict)
            else "Failed to place smart order"
        )
        error_response = {"status": "error", "message": message}
        executor.submit(async_log_order, "placesmartorder", original_data, error_response)
        status_code = res.status if res and hasattr(res, "status") else 500
        return False, error_response, status_code


def place_smart_order(
    order_data: dict[str, Any],
    api_key: str | None = None,
    auth_token: str | None = None,
    broker: str | None = None,
    smart_order_delay: str | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """
    Place a smart order.
    Supports both API-based authentication and direct internal calls.

    Args:
        order_data: Smart order data
        api_key: OpenAlgo API key (for API-based calls)
        auth_token: Direct broker authentication token (for internal calls)
        broker: Direct broker name (for internal calls)
        smart_order_delay: Delay in seconds between order placement and response

    Returns:
        Tuple containing:
        - Success status (bool)
        - Response data (dict)
        - HTTP status code (int)
    """
    original_data = copy.deepcopy(order_data)
    if api_key:
        original_data["apikey"] = api_key

    # Use default delay if not provided
    if smart_order_delay is None:
        smart_order_delay = SMART_ORDER_DELAY

    # Add API key to order data if provided (needed for validation)
    if api_key:
        order_data["apikey"] = api_key

    # Case 1: API-based authentication
    if api_key and not (auth_token and broker):
        # Check if order should be routed to Action Center (semi-auto mode)
        from services.order_router_service import queue_order, should_route_to_pending

        if should_route_to_pending(api_key, "smartorder"):
            return queue_order(api_key, original_data, "smartorder")

        AUTH_TOKEN, broker_name = get_auth_token_broker(api_key)
        if AUTH_TOKEN is None:
            error_response = {"status": "error", "message": "Invalid openalgo apikey"}
            # Skip logging for invalid API keys to prevent database flooding
            return False, error_response, 403

        return place_smart_order_with_auth(
            order_data, AUTH_TOKEN, broker_name, original_data, smart_order_delay
        )

    # Case 2: Direct internal call with auth_token and broker
    elif auth_token and broker:
        return place_smart_order_with_auth(
            order_data, auth_token, broker, original_data, smart_order_delay
        )

    # Case 3: Invalid parameters
    else:
        error_response = {
            "status": "error",
            "message": "Either api_key or both auth_token and broker must be provided",
        }
        return False, error_response, 400
