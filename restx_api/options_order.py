"""
Options Order API Endpoint

POST /api/v1/optionsorder

Places option orders by resolving option symbol based on underlying and offset,
then placing the order. Works in both live and analyze (sandbox) mode.
Supports order splitting via optional splitsize parameter.

PRICE DISCOVERY FEATURE:
For LIMIT orders, set price=0.0 to automatically fetch the option's current market data
and use bid/ask prices for better fill rates. Optionally apply adjustments.

Price Discovery Behavior:
- BUY orders: Uses ask price (what sellers are asking) + adjustment
- SELL orders: Uses bid price (what buyers are bidding) - adjustment
- Falls back to LTP if bid/ask not available

Request Body:
{
    "apikey": "your_api_key",
    "strategy": "strategy_name",
    "underlying": "NIFTY",  // or "NIFTY28NOV24FUT"
    "exchange": "NSE_INDEX",  // or "NSE", "NFO", "BSE_INDEX", "BSE", "BFO"
    "expiry_date": "28NOV24",  // Optional if underlying includes expiry
    "strike_int": 50,  // Optional: Strike interval. If omitted, actual strikes from database are used (RECOMMENDED)
    "offset": "ITM2",  // ATM, ITM1-ITM50, OTM1-OTM50
    "option_type": "CE",  // CE or PE
    "action": "BUY",  // or "SELL"
    "quantity": 75,
    "splitsize": 0,  // Optional: If > 0, splits order into multiple orders of this size
    "pricetype": "MARKET",  // or "LIMIT", "SL", "SL-M"
    "product": "MIS",  // or "NRML"
    "price": 0.0,  // For LIMIT orders. Set to 0.0 to trigger automatic price discovery
    "trigger_price": 0.0,  // For SL/SL-M orders
    "disclosed_quantity": 0,

    // PRICE DISCOVERY ADJUSTMENT (Optional - only used when price=0.0 and pricetype=LIMIT)
    "price_adjustment_type": "percentage",  // "percentage" or "absolute" or null (default: "percentage")
    "price_adjustment_value": 2.0           // Adjustment amount (0-10, default: 2.0)
                                            // BUY: adds to base price, SELL: subtracts from base price
}

Price Discovery Examples:
1. BUY with defaults: price=0.0
   → Uses ask price + 2% adjustment
   → If ask=102, final price = 102 + 2% = 104.04

2. SELL with defaults: price=0.0
   → Uses bid price - 2% adjustment
   → If bid=98, final price = 98 - 2% = 96.04

3. No adjustment: price=0.0, price_adjustment_type=null, price_adjustment_value=0.0
   → BUY: Uses ask price directly, SELL: Uses bid price directly

4. BUY with ₹5 premium: price=0.0, price_adjustment_type="absolute", price_adjustment_value=5.0
   → If ask=100, final price = 100 + 5 = 105

5. SELL with ₹5 discount: price=0.0, price_adjustment_type="absolute", price_adjustment_value=5.0
   → If bid=100, final price = 100 - 5 = 95

Note: Adjustment value is capped at 10 (10% for percentage, ₹10 for absolute).

Response (Success - Live Mode - Regular Order):
{
    "status": "success",
    "orderid": "240123000001234",
    "symbol": "NIFTY28NOV2423500CE",
    "exchange": "NFO",
    "underlying": "NIFTY",
    "underlying_ltp": 23587.50,
    "offset": "ITM2",
    "option_type": "CE"
}

Response (Success - Split Order):
{
    "status": "success",
    "symbol": "NIFTY28NOV2423500CE",
    "exchange": "NFO",
    "underlying": "NIFTY",
    "underlying_ltp": 23587.50,
    "offset": "ITM2",
    "option_type": "CE",
    "total_quantity": 150,
    "split_size": 50,
    "results": [
        {"order_num": 1, "quantity": 50, "status": "success", "orderid": "240123000001234"},
        {"order_num": 2, "quantity": 50, "status": "success", "orderid": "240123000001235"},
        {"order_num": 3, "quantity": 50, "status": "success", "orderid": "240123000001236"}
    ]
}

Response (Success - Analyze Mode):
{
    "status": "success",
    "orderid": "SB-1234567890",
    "symbol": "NIFTY28NOV2423500CE",
    "exchange": "NFO",
    "underlying": "NIFTY",
    "underlying_ltp": 23587.50,
    "offset": "ITM2",
    "option_type": "CE",
    "mode": "analyze"
}

Response (Error):
{
    "status": "error",
    "message": "Option symbol NIFTY28NOV2425500CE not found in NFO. Symbol may not exist or master contract needs update."
}
"""

import os

from flask import jsonify, make_response, request
from flask_restx import Namespace, Resource
from marshmallow import ValidationError

from limiter import limiter
from restx_api.schemas import OptionsOrderSchema
from services.place_options_order_service import place_options_order
from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)

# Create namespace
api = Namespace("optionsorder", description="Place Options Order API")

# Get rate limit from environment
ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10 per second")


@api.route("/", strict_slashes=False)
class OptionsOrder(Resource):
    @limiter.limit(ORDER_RATE_LIMIT)
    def post(self):
        """
        Place an options order by resolving the symbol based on underlying and offset.
        Works in both live and analyze (sandbox) mode.
        """
        try:
            # Validate request data
            schema = OptionsOrderSchema()
            data = schema.load(request.json)

            # Extract API key
            api_key = data.get("apikey")

            logger.info(
                f"Options order API request: underlying={data.get('underlying')}, "
                f"offset={data.get('offset')}, action={data.get('action')}"
            )

            # Call the service function to place the options order
            success, response_data, status_code = place_options_order(
                options_data=data, api_key=api_key
            )

            return make_response(jsonify(response_data), status_code)

        except ValidationError as err:
            logger.warning(f"Validation error in options order request: {err.messages}")
            return make_response(
                jsonify({"status": "error", "message": "Validation error", "errors": err.messages}),
                400,
            )
        except Exception:
            logger.exception("An unexpected error occurred in OptionsOrder endpoint.")
            error_response = {
                "status": "error",
                "message": "An unexpected error occurred in the API endpoint",
            }
            return make_response(jsonify(error_response), 500)
