"""Synthetic future paired-leg order endpoint.

POST /api/v1/syntheticfutureorder
"""

import os
from typing import Any, cast

from flask import jsonify, make_response, request
from flask_restx import Namespace, Resource
from marshmallow import ValidationError

from limiter import limiter
from restx_api.schemas import SyntheticFutureOrderSchema
from services.synthetic_future_order_service import enter_synthetic_future, exit_synthetic_future
from utils.logging import get_logger

logger = get_logger(__name__)
api = Namespace("syntheticfutureorder", description="Place synthetic future BUY and SELL orders")
ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10 per second")


@api.route("/", strict_slashes=False)
class SyntheticFutureOrder(Resource):
    @limiter.limit(ORDER_RATE_LIMIT)
    def post(self):
        """Place a synthetic future BUY or SELL using paired option legs."""
        try:
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return make_response(
                    jsonify({"status": "error", "message": "Request body must be a JSON object"}),
                    400,
                )

            data = cast(dict[str, Any], SyntheticFutureOrderSchema().load(payload))
            api_key = data["apikey"]
            leg_actions = (
                [leg["action"] for leg in data["legs"]]
                if "legs" in data
                else ["BUY", "SELL"]
            )

            logger.info(
                "Synthetic future order request: underlying=%s, action=%s, leg_actions=%s",
                data.get("underlying"),
                data.get("action"),
                ",".join(leg_actions),
            )

            if "legs" in data:
                _, response_data, status_code = exit_synthetic_future(data, api_key)
            else:
                data["direction"] = "LONG" if data["action"] == "BUY" else "SHORT"
                _, response_data, status_code = enter_synthetic_future(data, api_key)

            return make_response(jsonify(response_data), status_code)
        except ValidationError as err:
            logger.warning("Validation error in synthetic future order request: %s", err.messages)
            return make_response(
                jsonify({"status": "error", "message": "Validation error", "errors": err.messages}),
                400,
            )
        except Exception:
            logger.exception("An unexpected error occurred in SyntheticFutureOrder endpoint.")
            return make_response(
                jsonify({"status": "error", "message": "An unexpected error occurred in the API endpoint"}),
                500,
            )
