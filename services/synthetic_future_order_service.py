"""Order workflows for synthetic futures built from ATM options."""

from utils.logging import get_logger

logger = get_logger(__name__)


def enter_synthetic_future(data: dict, api_key: str):
    """Place the BUY then SELL leg, squaring off the first if the second fails."""
    from services.order_router_service import should_route_to_pending
    from services.place_options_order_service import place_options_order

    long_call = data["direction"] == "LONG"
    call_offset = data["offset"].upper()
    if call_offset.startswith("ITM"):
        put_offset = "OTM" + call_offset[3:]
    elif call_offset.startswith("OTM"):
        put_offset = "ITM" + call_offset[3:]
    else:
        put_offset = call_offset
    legs = [
        ("CE" if long_call else "PE", "BUY", call_offset if long_call else put_offset),
        ("PE" if long_call else "CE", "SELL", put_offset if long_call else call_offset),
    ]
    common = {
        "apikey": api_key,
        "strategy": data["strategy"],
        "underlying": data["underlying"],
        "exchange": data["exchange"],
        "expiry_date": data["expiry_date"],
        "quantity": data["quantity"],
        "pricetype": data["pricetype"],
        "product": data["product"],
        "price": data["price"],
        "trigger_price": data["trigger_price"],
        "disclosed_quantity": data["disclosed_quantity"],
    }

    # Queue the pair together; queueing the first optionsorder alone would leave
    # the second leg unsubmitted until after approval.
    if should_route_to_pending(api_key, "optionsorder"):
        from services.basket_order_service import place_basket_order
        from services.option_symbol_service import get_option_symbol

        resolved = []
        underlying_ltp = None
        for option_type, action, offset in legs:
            ok, symbol_data, status_code = get_option_symbol(
                underlying=data["underlying"],
                exchange=data["exchange"],
                expiry_date=data["expiry_date"],
                strike_int=None,
                offset=offset,
                option_type=option_type,
                api_key=api_key,
                underlying_ltp=underlying_ltp,
            )
            if not ok:
                return False, symbol_data, status_code
            underlying_ltp = symbol_data.get("underlying_ltp")
            resolved.append(
                {
                    "symbol": symbol_data["symbol"],
                    "exchange": symbol_data["exchange"],
                    "action": action,
                    **{key: common[key] for key in (
                        "quantity", "pricetype", "product", "price", "trigger_price",
                        "disclosed_quantity",
                    )},
                }
            )
        return place_basket_order(
            {"apikey": api_key, "strategy": data["strategy"], "orders": resolved},
            api_key=api_key,
        )

    results = []
    underlying_ltp = None
    first_result = None
    status_code = 200
    for index, (option_type, action, offset) in enumerate(legs, start=1):
        ok, response, status_code = place_options_order(
            {
                **common,
                "offset": offset,
                "option_type": option_type,
                "action": action,
                "underlying_ltp": underlying_ltp,
            },
            api_key=api_key,
        )
        result = {
            "leg": index,
            "symbol": response.get("symbol"),
            "exchange": response.get("exchange"),
            "offset": offset,
            "option_type": option_type,
            "action": action,
            "status": "success" if ok else "error",
        }
        if ok:
            result["orderid"] = response.get("orderid")
            underlying_ltp = response.get("underlying_ltp", underlying_ltp)
            if index == 1:
                first_result = result
        else:
            result["message"] = response.get("message", "Order placement failed")
        results.append(result)

        if not ok:
            if index == 1:
                next_type, next_action, next_offset = legs[1]
                results.append(
                    {
                        "leg": 2,
                        "offset": next_offset,
                        "option_type": next_type,
                        "action": next_action,
                        "status": "skipped",
                        "message": "Not placed because the first leg failed",
                    }
                )
            break

    response_data = {
        "status": "success" if len(results) == 2 and all(
            item["status"] == "success" for item in results
        ) else "error",
        "underlying": data["underlying"],
        "underlying_ltp": underlying_ltp,
        "results": results,
    }
    if response_data["status"] == "success":
        return True, response_data, 200

    if first_result is not None:
        try:
            from services.basket_order_service import place_basket_order

            success, square_off_response, _ = place_basket_order(
                {
                    "apikey": api_key,
                    "strategy": data["strategy"],
                    "orders": [
                        {
                            "symbol": first_result["symbol"],
                            "exchange": first_result["exchange"],
                            "action": "SELL" if first_result["action"] == "BUY" else "BUY",
                            "quantity": data["quantity"],
                            "pricetype": "MARKET",
                            "product": data["product"],
                        }
                    ],
                },
                api_key=api_key,
            )
            response_data["square_off_results"] = square_off_response.get("results", [])
            response_data["square_off_status"] = (
                "success"
                if success and all(
                    item.get("status") == "success"
                    for item in response_data["square_off_results"]
                )
                else "error"
            )
        except Exception as error:
            logger.exception("Failed to square off a synthetic future entry leg")
            response_data["square_off_status"] = "error"
            response_data["square_off_results"] = [{"status": "error", "message": str(error)}]
    else:
        response_data["square_off_status"] = "not_required"
        response_data["square_off_results"] = []

    return False, response_data, status_code


def exit_synthetic_future(data: dict, api_key: str):
    """Close explicit option symbols through the existing basket-order service."""
    from services.basket_order_service import place_basket_order

    return place_basket_order(
        {"apikey": api_key, "strategy": data["strategy"], "orders": data["legs"]},
        api_key=api_key,
    )
