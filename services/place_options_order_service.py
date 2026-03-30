"""
Place Options Order Service

This service places option orders by:
1. Resolving the option symbol using offset from ATM
2. Placing the order in either live or analyze mode
3. Optionally splitting large orders into multiple smaller orders (if splitsize is specified)

Supports both live trading and sandbox (analyze) mode, just like place_order_service.
"""

import copy
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from database.analyzer_db import async_log_analyzer
from database.apilog_db import async_log_order
from database.apilog_db import executor as log_executor
from database.auth_db import get_auth_token_broker
from database.settings_db import get_analyze_mode, get_smart_trade_rules
from extensions import socketio
from services.option_symbol_service import (
    find_atm_strike_from_actual,
    find_option_symbols_by_strikes_batch,
    get_available_strikes,
    get_option_exchange,
    get_option_symbol,
    parse_underlying_symbol,
)
from services.place_order_service import place_order
from services.quotes_service import get_multiquotes, get_quotes
from services.telegram_alert_service import telegram_alert_service
from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)

# Maximum number of split orders allowed
MAX_SPLIT_ORDERS = 100

# Maximum adjustment limits for price discovery
MAX_ADJUSTMENT_PERCENT = 10.0
MAX_ADJUSTMENT_ABSOLUTE = 10.0


# Get rate limit from environment (default: 10 per second)
def get_order_rate_limit():
    """Parse ORDER_RATE_LIMIT and return delay in seconds between orders"""
    rate_limit_str = os.getenv("ORDER_RATE_LIMIT", "10 per second")
    try:
        rate = int(rate_limit_str.split()[0])
        return 1.0 / rate if rate > 0 else 0.1
    except (ValueError, IndexError):
        return 0.1  # Default 100ms delay


def place_single_split_order(
    order_data: dict[str, Any],
    api_key: str,
    order_num: int,
    total_orders: int,
    auth_token: str | None = None,
    broker: str | None = None,
) -> dict[str, Any]:
    """
    Place a single split order and return result.

    Args:
        order_data: Order data with symbol, exchange, action, quantity, etc.
        api_key: OpenAlgo API key
        order_num: Order number in the sequence
        total_orders: Total number of orders
        auth_token: Direct broker auth token (optional)
        broker: Broker name (optional)

    Returns:
        Result dictionary with order status
    """
    try:
        # Pass emit_event=False to suppress per-order socket events
        # A summary event is emitted at the end of all split orders
        success, order_response, status_code = place_order(
            order_data=order_data,
            api_key=api_key,
            auth_token=auth_token,
            broker=broker,
            emit_event=False,
        )

        if success:
            return {
                "order_num": order_num,
                "quantity": int(order_data["quantity"]),
                "status": "success",
                "orderid": order_response.get("orderid"),
            }
        else:
            return {
                "order_num": order_num,
                "quantity": int(order_data["quantity"]),
                "status": "error",
                "message": order_response.get("message", "Failed to place order"),
            }
    except Exception as e:
        logger.exception(f"Error placing split order {order_num}: {e}")
        return {
            "order_num": order_num,
            "quantity": int(order_data["quantity"]),
            "status": "error",
            "message": "Failed to place order due to internal error",
        }


def select_best_liquid_strike(
    underlying: str,
    exchange: str,
    expiry_date: str,
    option_type: str,
    api_key: str,
    underlying_ltp: float | None = None,
    base_symbol: str | None = None,
    options_exchange: str | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """
    Select the strike with best liquidity from ATM and 3 ITM strikes.

    Evaluates 4 strikes (ATM + ITM1-ITM3), fetches quotes via multiquotes,
    and returns the symbol with highest liquidity score among valid (bid>0 and ask>0) strikes.

    Score = (oi * 0.7) + (volume * 0.3)
    """
    if base_symbol is None or options_exchange is None:
        parsed_base, embedded_expiry = parse_underlying_symbol(underlying)
        base_symbol = base_symbol or parsed_base
        options_exchange = options_exchange or get_option_exchange(exchange)
    else:
        _, embedded_expiry = parse_underlying_symbol(underlying)
    final_expiry = embedded_expiry or expiry_date

    available_strikes = get_available_strikes(
        base_symbol, final_expiry, option_type, options_exchange
    )
    if not available_strikes:
        return False, {"status": "error", "message": "No strikes available for liquidity selection"}, 404

    # Get underlying LTP
    if underlying_ltp is not None:
        ltp = underlying_ltp
    else:
        success, symbol_resp, _ = get_option_symbol(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date,
            strike_int=None, offset="ATM", option_type=option_type, api_key=api_key,
        )
        if not success:
            return False, {"status": "error", "message": "Failed to fetch underlying LTP"}, 500
        ltp = symbol_resp.get("underlying_ltp")
        if not ltp:
            return False, {"status": "error", "message": "Could not determine underlying LTP"}, 500

    atm_strike = find_atm_strike_from_actual(ltp, available_strikes)
    if atm_strike is None:
        return False, {"status": "error", "message": "Failed to determine ATM strike"}, 500

    atm_index = available_strikes.index(atm_strike)
    option_type_upper = option_type.upper()

    # Build candidate indices: ATM + 3 ITM
    if option_type_upper == "CE":
        indices = [atm_index - i for i in range(4) if atm_index - i >= 0]
    else:  # PE
        indices = [atm_index + i for i in range(4) if atm_index + i < len(available_strikes)]

    candidate_strikes = [available_strikes[i] for i in indices]
    if not candidate_strikes:
        return False, {"status": "error", "message": "No candidate strikes found"}, 404

    # Build symbols via batch lookup
    batch_results = find_option_symbols_by_strikes_batch(
        base_symbol, final_expiry, candidate_strikes, options_exchange
    )

    # Build symbol -> (strike, batch_info) mapping for later lookup
    symbol_to_strike: dict[str, tuple[float, dict[str, Any]]] = {}
    symbols_to_fetch = []
    for strike in candidate_strikes:
        info = batch_results.get((strike, option_type_upper), {})
        sym = info.get("symbol")
        if sym:
            symbol_to_strike[sym] = (strike, info)
            symbols_to_fetch.append({"symbol": sym, "exchange": options_exchange})

    if not symbols_to_fetch:
        return False, {"status": "error", "message": "No valid option symbols found for candidate strikes"}, 404

    # Fetch all quotes in one call
    success, quotes_response, _ = get_multiquotes(symbols=symbols_to_fetch, api_key=api_key)
    if not success:
        return False, {"status": "error", "message": "Failed to fetch quotes for liquidity evaluation"}, 500

    # Score and select
    best_score = -1
    best_result = None
    evaluated = []

    for result in quotes_response.get("results", []):
        sym = result.get("symbol", "")

        # Skip error entries from multiquotes
        if "error" in result and "data" not in result:
            evaluated.append({"symbol": sym, "oi": 0, "volume": 0, "bid": 0, "ask": 0, "score": 0, "error": result["error"]})
            continue

        data = result.get("data", result)
        bid = data.get("bid", 0) or 0
        ask = data.get("ask", 0) or 0
        oi = data.get("oi", 0) or 0
        volume = data.get("volume", 0) or 0
        score = (oi * 0.7) + (volume * 0.3)

        evaluated.append({"symbol": sym, "oi": int(oi), "volume": int(volume), "bid": bid, "ask": ask, "score": score})

        if bid > 0 and ask > 0 and score > best_score:
            best_score = score
            _, batch_info = symbol_to_strike.get(sym, (0, {}))
            best_result = {
                "symbol": sym,
                "exchange": options_exchange,
                "lotsize": batch_info.get("lotsize", 0),
                "tick_size": batch_info.get("tick_size", 0.05),
            }

    if best_result is None:
        logger.warning(f"Liquidity selection: no valid strikes for {underlying} {option_type_upper} - evaluated: {evaluated}")
        return False, {"status": "error", "message": "No strikes with valid bid/ask prices found"}, 400

    logger.info(f"Liquidity selection: best={best_result['symbol']} score={best_score}, evaluated={evaluated}")
    return True, {"status": "success", **best_result, "evaluated_strikes": evaluated}, 200


def place_options_order(
    options_data: dict[str, Any],
    api_key: str | None = None,
    auth_token: str | None = None,
    broker: str | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """
    Place an options order by first resolving the symbol, then placing the order.
    Works in both live and analyze mode.

    Args:
        options_data: Options order data containing:
            - underlying: Underlying symbol
            - exchange: Exchange
            - expiry_date: Expiry date (optional if embedded in underlying)
            - strike_int: Strike interval (OPTIONAL - if not provided, uses actual strikes from database)
            - offset: Strike offset (ATM, ITM1-ITM50, OTM1-OTM50)
            - option_type: CE or PE
            - action: BUY or SELL
            - quantity: Order quantity
            - pricetype: MARKET, LIMIT, SL, SL-M
            - product: MIS or NRML
            - price: Limit price (if applicable)
            - trigger_price: Trigger price (if applicable)
            - disclosed_quantity: Disclosed quantity
            - strategy: Strategy name
            - apikey: API key
        api_key: OpenAlgo API key (for API-based calls)
        auth_token: Direct broker authentication token (for internal calls)
        broker: Direct broker name (for internal calls)

    Returns:
        Tuple containing:
        - Success status (bool)
        - Response data (dict)
        - HTTP status code (int)
    """
    try:
        # Store original data for potential queuing
        original_data = copy.deepcopy(options_data)
        if api_key:
            original_data["apikey"] = api_key

        # Add API key to options data if provided (needed for validation and symbol resolution)
        if api_key:
            options_data["apikey"] = api_key

        # Check if order should be routed to Action Center (semi-auto mode)
        if api_key and not (auth_token and broker):
            from services.order_router_service import queue_order, should_route_to_pending

            if should_route_to_pending(api_key, "optionsorder"):
                return queue_order(api_key, original_data, "optionsorder")

        # Extract option-specific parameters
        underlying = options_data.get("underlying")
        exchange = options_data.get("exchange")
        expiry_date = options_data.get("expiry_date")
        strike_int = options_data.get(
            "strike_int"
        )  # Optional - if not provided, actual strikes from database will be used
        offset = options_data.get("offset")
        option_type = options_data.get("option_type")

        # Validate required option parameters (strike_int is now optional)
        if not all([underlying, exchange, offset, option_type]):
            return (
                False,
                {
                    "status": "error",
                    "message": "Missing required option parameters: underlying, exchange, offset, option_type",
                },
                400,
            )

        # Log the option order request
        logger.info(
            f"Options order request: underlying={underlying}, exchange={exchange}, "
            f"expiry={expiry_date}, strike_int={strike_int}, offset={offset}, type={option_type}"
        )

        # Step 1: Get the option symbol using option_symbol_service
        # Pass api_key or use the one from options_data
        symbol_api_key = api_key or options_data.get("apikey")
        if not symbol_api_key:
            return (
                False,
                {"status": "error", "message": "API key required for option symbol resolution"},
                400,
            )

        success, symbol_response, status_code = get_option_symbol(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            strike_int=strike_int,
            offset=offset,
            option_type=option_type,
            api_key=symbol_api_key,
        )

        if not success:
            # Option symbol not found or error occurred
            logger.error(f"Failed to get option symbol: {symbol_response.get('message')}")
            return False, symbol_response, status_code

        # Extract the resolved symbol and exchange
        resolved_symbol = symbol_response.get("symbol")
        resolved_exchange = symbol_response.get("exchange")
        underlying_ltp = symbol_response.get("underlying_ltp")
        tick_size = symbol_response.get("tick_size", 0.05)  # Get tick_size with fallback

        if not resolved_symbol or not resolved_exchange:
            return (
                False,
                {
                    "status": "error",
                    "message": "Failed to extract symbol from option_symbol response",
                },
                500,
            )

        logger.info(
            f"Resolved option symbol: {resolved_symbol} on {resolved_exchange}, "
            f"Underlying LTP: {underlying_ltp}, Tick Size: {tick_size}"
        )

        # Price Discovery: If pricetype is LIMIT and price is 0.0, fetch option LTP
        pricetype = options_data.get("pricetype", "MARKET")
        price = options_data.get("price", 0.0)
        action = options_data.get("action", "BUY").upper()
        liquidity_fallback_applied = False
        original_symbol_for_fallback = None
        fallback_reason = None

        if pricetype == "LIMIT" and price == 0.0:
            logger.info(f"Price discovery triggered for {resolved_symbol}")

            # Fetch option quotes (includes LTP, bid, ask)
            success, quote_response, status_code = get_quotes(
                symbol=resolved_symbol, exchange=resolved_exchange, api_key=symbol_api_key
            )

            if not success:
                error_msg = quote_response.get("message", "Unknown error")
                logger.error(f"Price discovery failed for {resolved_symbol}: {error_msg}")
                return (
                    False,
                    {
                        "status": "error",
                        "message": f"Failed to fetch option price for {resolved_symbol}. {error_msg}",
                    },
                    status_code,
                )

            # Extract quote data
            option_ltp = quote_response.get("data", {}).get("ltp")
            option_bid = quote_response.get("data", {}).get("bid", 0)
            option_ask = quote_response.get("data", {}).get("ask", 0)

            # Log quote data for audit trail
            logger.info(
                f"PRICE_DISCOVERY_QUOTES: symbol={resolved_symbol}, "
                f"ltp={option_ltp}, bid={option_bid}, ask={option_ask}, action={action}"
            )

            # Liquidity fallback: auto-select best liquid strike if configured
            smart_rules = get_smart_trade_rules()
            liquidity_fallback_enabled = smart_rules.get("liquidity_fallback", True)

            if liquidity_fallback_enabled:
                should_fallback = (offset.upper() == "ATM") or (not option_bid or option_bid <= 0) or (not option_ask or option_ask <= 0)

                if should_fallback:
                    logger.info(
                        f"Liquidity fallback triggered for {resolved_symbol} "
                        f"(offset={offset}, bid={option_bid}, ask={option_ask})"
                    )
                    fb_success, fb_response, fb_status = select_best_liquid_strike(
                        underlying=underlying,
                        exchange=exchange,
                        expiry_date=expiry_date,
                        option_type=option_type,
                        api_key=symbol_api_key,
                        underlying_ltp=underlying_ltp,
                        options_exchange=resolved_exchange,
                    )

                    if fb_success:
                        original_symbol_for_fallback = resolved_symbol
                        resolved_symbol = fb_response["symbol"]
                        resolved_exchange = fb_response.get("exchange", resolved_exchange)
                        tick_size = fb_response.get("tick_size", tick_size)
                        liquidity_fallback_applied = True
                        if offset.upper() == "ATM":
                            fallback_reason = "ATM: auto-selected best liquid strike"
                        elif not option_bid or option_bid <= 0:
                            fallback_reason = "Original strike had bid=0"
                        else:
                            fallback_reason = "Original strike had ask=0"

                        logger.info(
                            f"Liquidity fallback: selected {resolved_symbol} (was {original_symbol_for_fallback})"
                        )

                        # Re-fetch quotes for the selected symbol
                        success, quote_response, status_code = get_quotes(
                            symbol=resolved_symbol, exchange=resolved_exchange, api_key=symbol_api_key
                        )
                        if not success:
                            return (
                                False,
                                {
                                    "status": "error",
                                    "message": f"Liquidity fallback selected {resolved_symbol} but failed to fetch its quotes",
                                },
                                status_code,
                            )
                        option_ltp = quote_response.get("data", {}).get("ltp")
                        option_bid = quote_response.get("data", {}).get("bid", 0)
                        option_ask = quote_response.get("data", {}).get("ask", 0)
                    else:
                        # Fallback failed
                        if (not option_bid or option_bid <= 0) or (not option_ask or option_ask <= 0):
                            return (
                                False,
                                {
                                    "status": "error",
                                    "message": f"Invalid base price: no liquidity for {resolved_symbol} and no better strike found. {fb_response.get('message', '')}",
                                },
                                fb_status if fb_status != 200 else 400,
                            )

            # Determine base price based on action
            # BUY: Use ask price (what sellers are asking)
            # SELL: Use bid price (what buyers are bidding)
            if action == "BUY":
                if option_ask and option_ask > 0:
                    base_price = option_ask
                    price_source = "ask"
                else:
                    # Fallback to LTP if ask not available
                    base_price = option_ltp
                    price_source = "ltp_fallback"
            else:  # SELL
                if option_bid and option_bid > 0:
                    base_price = option_bid
                    price_source = "bid"
                else:
                    # Fallback to LTP if bid not available
                    base_price = option_ltp
                    price_source = "ltp_fallback"

            if not base_price or base_price <= 0:
                logger.error(f"Invalid base price for {resolved_symbol}: {base_price}")
                return (
                    False,
                    {"status": "error", "message": f"Invalid option price received: {base_price}"},
                    400,
                )

            # Get adjustment parameters
            adjustment_type = options_data.get("price_adjustment_type")
            adjustment_value = options_data.get("price_adjustment_value", 0.0)

            # Validate adjustment limits
            if adjustment_type == "percentage":
                if adjustment_value > MAX_ADJUSTMENT_PERCENT:
                    return (
                        False,
                        {
                            "status": "error",
                            "message": f"Adjustment value {adjustment_value}% exceeds maximum allowed {MAX_ADJUSTMENT_PERCENT}%",
                        },
                        400,
                    )
            elif adjustment_type == "absolute":
                if adjustment_value > MAX_ADJUSTMENT_ABSOLUTE:
                    return (
                        False,
                        {
                            "status": "error",
                            "message": f"Absolute adjustment value {adjustment_value} exceeds maximum allowed {MAX_ADJUSTMENT_ABSOLUTE}",
                        },
                        400,
                    )

            # Log adjustment parameters for audit trail
            logger.info(
                f"PRICE_DISCOVERY_ADJUSTMENT: symbol={resolved_symbol}, "
                f"adjustment_type={adjustment_type}, adjustment_value={adjustment_value}, "
                f"base_price={base_price}, price_source={price_source}"
            )

            # Apply adjustment to base price
            if adjustment_type == "percentage":
                # BUY: Add premium (pay more), SELL: Reduce price (receive less)
                if action == "BUY":
                    discovered_price = base_price * (1 + adjustment_value / 100)
                else:  # SELL
                    discovered_price = base_price * (1 - adjustment_value / 100)
            elif adjustment_type == "absolute":
                # BUY: Add amount, SELL: Subtract amount
                if action == "BUY":
                    discovered_price = base_price + adjustment_value
                else:  # SELL
                    discovered_price = base_price - adjustment_value
            else:
                # No adjustment
                discovered_price = base_price

            # Round to tick size from database
            if tick_size and tick_size > 0:
                discovered_price = round(discovered_price / tick_size) * tick_size
            else:
                # Fallback to 2 decimal places if tick_size not available
                discovered_price = round(discovered_price, 2)

            # Validate final price
            if discovered_price <= 0:
                logger.error(
                    f"Invalid discovered price for {resolved_symbol}: {discovered_price} "
                    f"(Base: {base_price}, Action: {action}, Adjustment: {adjustment_type}:{adjustment_value})"
                )
                return (
                    False,
                    {
                        "status": "error",
                        "message": f"Invalid discovered price: {discovered_price}. "
                        f"Adjustment too large for {action} order.",
                    },
                    400,
                )

            # Override price parameter with discovered price
            options_data["price"] = discovered_price

            # Log final result for audit trail
            logger.info(
                f"PRICE_DISCOVERY_COMPLETE: symbol={resolved_symbol}, action={action}, "
                f"base_price={base_price}, price_source={price_source}, "
                f"adjustment_type={adjustment_type}, adjustment_value={adjustment_value}, "
                f"tick_size={tick_size}, final_price={discovered_price}"
            )
        else:
            logger.debug(
                f"Price discovery not needed: pricetype={pricetype}, price={price} "
                f"(discovery only for LIMIT orders with price=0.0)"
            )

        # Check if split order is requested
        splitsize = options_data.get("splitsize", 0) or 0
        total_quantity = int(options_data.get("quantity", 0))

        # Step 2: Handle split orders if splitsize > 0
        if splitsize > 0:
            # Validate split parameters
            num_full_orders = total_quantity // splitsize
            remaining_qty = total_quantity % splitsize
            total_orders = num_full_orders + (1 if remaining_qty > 0 else 0)

            if total_orders > MAX_SPLIT_ORDERS:
                return (
                    False,
                    {
                        "status": "error",
                        "message": f"Total number of orders would exceed maximum limit of {MAX_SPLIT_ORDERS}",
                    },
                    400,
                )

            logger.info(
                f"Split order requested: total_qty={total_quantity}, splitsize={splitsize}, "
                f"orders={total_orders}"
            )

            # Base order data template - include underlying_ltp for execution reference
            base_order_data = {
                "apikey": options_data.get("apikey"),
                "strategy": options_data.get("strategy"),
                "exchange": resolved_exchange,
                "symbol": resolved_symbol,
                "action": options_data.get("action"),
                "pricetype": options_data.get("pricetype", "MARKET"),
                "product": options_data.get("product", "MIS"),
                "price": options_data.get("price", 0.0),
                "trigger_price": options_data.get("trigger_price", 0.0),
                "disclosed_quantity": options_data.get("disclosed_quantity", 0),
                "underlying_ltp": underlying_ltp,  # Pass LTP for execution reference
            }

            # Process split orders sequentially with rate limiting
            results = []
            order_delay = get_order_rate_limit()

            # Place full-size orders
            for i in range(num_full_orders):
                if i > 0:
                    time.sleep(order_delay)  # Rate limit delay between orders
                order_data = copy.deepcopy(base_order_data)
                order_data["quantity"] = splitsize
                result = place_single_split_order(
                    order_data, api_key, i + 1, total_orders, auth_token, broker
                )
                results.append(result)

            # Place remaining quantity order if any
            if remaining_qty > 0:
                if num_full_orders > 0:
                    time.sleep(order_delay)  # Rate limit delay
                order_data = copy.deepcopy(base_order_data)
                order_data["quantity"] = remaining_qty
                result = place_single_split_order(
                    order_data, api_key, total_orders, total_orders, auth_token, broker
                )
                results.append(result)

            # Build split order response
            response_data = {
                "status": "success",
                "symbol": resolved_symbol,
                "exchange": resolved_exchange,
                "underlying": underlying,
                "underlying_ltp": underlying_ltp,
                "offset": offset,
                "option_type": option_type.upper(),
                "total_quantity": total_quantity,
                "split_size": splitsize,
                "results": results,
            }

            # Add mode if in analyze mode
            if get_analyze_mode():
                response_data["mode"] = "analyze"

            # Add liquidity fallback info if applied
            if liquidity_fallback_applied:
                response_data["original_symbol"] = original_symbol_for_fallback
                response_data["liquidity_fallback"] = True
                response_data["fallback_reason"] = fallback_reason

            # Emit toast notification for split orders
            mode = "analyze" if get_analyze_mode() else "live"
            successful_orders = sum(1 for r in results if r.get("status") == "success")
            socketio.start_background_task(
                socketio.emit,
                "order_event",
                {
                    "symbol": resolved_symbol,
                    "action": options_data.get("action"),
                    "orderid": f"{successful_orders}/{len(results)} orders",
                    "exchange": resolved_exchange,
                    "price_type": options_data.get("pricetype", "MARKET"),
                    "product_type": options_data.get("product", "MIS"),
                    "mode": mode,
                    "batch_order": True,
                    "is_last_order": True,
                },
            )

            # Log the split order
            request_log = original_data.copy()
            if "apikey" in request_log:
                del request_log["apikey"]

            if get_analyze_mode():
                request_log["api_type"] = "optionsorder"
                log_executor.submit(async_log_analyzer, request_log, response_data, "optionsorder")
                socketio.start_background_task(
                    socketio.emit,
                    "analyzer_update",
                    {"request": request_log, "response": response_data},
                )
            else:
                log_executor.submit(async_log_order, "optionsorder", request_log, response_data)

            # Send Telegram alert in background task (non-blocking)
            socketio.start_background_task(
                telegram_alert_service.send_order_alert,
                "optionsorder",
                options_data,
                response_data,
                api_key,
            )

            logger.info(
                f"Split options order completed: {successful_orders}/{len(results)} successful"
            )
            return True, response_data, 200

        # Step 2 (non-split): Construct regular order data with the resolved symbol
        # Include underlying_ltp for execution reference
        order_data = {
            "apikey": options_data.get("apikey"),
            "strategy": options_data.get("strategy"),
            "exchange": resolved_exchange,  # Use resolved exchange (NFO/BFO)
            "symbol": resolved_symbol,  # Use resolved option symbol
            "action": options_data.get("action"),
            "quantity": options_data.get("quantity"),
            "pricetype": options_data.get("pricetype", "MARKET"),
            "product": options_data.get("product", "MIS"),
            "price": options_data.get("price", 0.0),
            "trigger_price": options_data.get("trigger_price", 0.0),
            "disclosed_quantity": options_data.get("disclosed_quantity", 0),
            "underlying_ltp": underlying_ltp,  # Pass LTP for execution reference
        }

        # Step 3: Place the order using the standard place_order service
        # This automatically handles live vs analyze mode
        success, order_response, status_code = place_order(
            order_data=order_data, api_key=api_key, auth_token=auth_token, broker=broker
        )

        if success:
            # Enhance response with option details
            enhanced_response = {
                "status": "success",
                "orderid": order_response.get("orderid"),
                "symbol": resolved_symbol,
                "exchange": resolved_exchange,
                "underlying": underlying,
                "underlying_ltp": underlying_ltp,
                "offset": offset,
                "option_type": option_type.upper(),
            }

            # Add mode if present (analyze or live)
            if "mode" in order_response:
                enhanced_response["mode"] = order_response["mode"]

            # Add liquidity fallback info if applied
            if liquidity_fallback_applied:
                enhanced_response["original_symbol"] = original_symbol_for_fallback
                enhanced_response["liquidity_fallback"] = True
                enhanced_response["fallback_reason"] = fallback_reason

            logger.info(f"Options order placed successfully: {enhanced_response.get('orderid')}")
            return True, enhanced_response, status_code
        else:
            # Order placement failed, return the error
            logger.error(f"Failed to place options order: {order_response.get('message')}")
            return False, order_response, status_code

    except Exception as e:
        logger.exception(f"Error in place_options_order: {e}")
        return (
            False,
            {
                "status": "error",
                "message": f"An error occurred while processing options order: {str(e)}",
            },
            500,
        )
