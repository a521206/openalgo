# blueprints/tv_json.py

import logging
from collections import OrderedDict

from flask import Blueprint, jsonify, request, session

from database.auth_db import get_api_key_for_tradingview
from database.symbol import enhanced_search_symbols
from utils.session import check_session_validity

logger = logging.getLogger(__name__)

tv_json_bp = Blueprint("tv_json_bp", __name__, url_prefix="/tradingview")


@tv_json_bp.route("/", methods=["POST"])
@check_session_validity
def tradingview_json():
    try:
        symbol_input = request.json.get("symbol")
        exchange = request.json.get("exchange")
        product = request.json.get("product")
        mode = request.json.get("mode", "strategy")  # 'strategy' or 'line'

        # Get actual API key for TradingView
        api_key = get_api_key_for_tradingview(session.get("user"))
        if not api_key:
            logger.error(f"API key not found for user: {session.get('user')}")
            return jsonify({"error": "API key not found"}), 404

        # Use enhanced search function
        symbols = enhanced_search_symbols(symbol_input, exchange)
        if not symbols:
            logger.warning(f"Symbol not found: {symbol_input}")
            return jsonify({"error": "Symbol not found"}), 404

        symbol_data = symbols[0]  # Take the first match
        logger.info(f"Found matching symbol: {symbol_data.symbol}")

        if mode == "line":
            # Line Alert Mode - similar to GoCharting (uses placeorder)
            action = request.json.get("action")
            quantity = request.json.get("quantity")

            if not all([symbol_input, exchange, product, action, quantity]):
                logger.error("Missing required fields in TradingView Line Alert request")
                return jsonify({"error": "Missing required fields"}), 400

            logger.info(
                f"Processing TradingView Line Alert - Symbol: {symbol_input}, Action: {action}, Quantity: {quantity}"
            )

            json_data = OrderedDict(
                [
                    ("apikey", api_key),
                    ("strategy", "TradingView Line Alert"),
                    ("symbol", symbol_data.symbol),
                    ("action", action.upper()),
                    ("exchange", symbol_data.exchange),
                    ("pricetype", "MARKET"),
                    ("product", product),
                    ("quantity", str(quantity)),
                ]
            )
        else:
            # Strategy Alert Mode - original behavior (uses placesmartorder)
            if not all([symbol_input, exchange, product]):
                logger.error("Missing required fields in TradingView Strategy request")
                return jsonify({"error": "Missing required fields"}), 400

            logger.info(
                f"Processing TradingView Strategy Alert - Symbol: {symbol_input}, Exchange: {exchange}, Product: {product}"
            )

            json_data = OrderedDict(
                [
                    ("apikey", api_key),
                    ("strategy", "TradingView Strategy"),
                    ("symbol", symbol_data.symbol),
                    ("action", "{{strategy.order.action}}"),
                    ("exchange", symbol_data.exchange),
                    ("pricetype", "MARKET"),
                    ("product", product),
                    ("quantity", "{{strategy.order.contracts}}"),
                    ("position_size", "{{strategy.position_size}}"),
                ]
            )

        logger.info("Successfully generated TradingView webhook data")
        return jsonify(json_data)

    except Exception as e:
        logger.exception(f"Error processing TradingView request: {str(e)}")
        return jsonify({"error": str(e)}), 500
