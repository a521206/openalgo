"""Synthetic future paired-leg order endpoint.

POST /api/v1/syntheticfutureorder
"""

import os

from flask import jsonify, make_response, request
from flask_restx import Namespace, Resource
from marshmallow import ValidationError

from limiter import limiter
from restx_api.schemas import SyntheticFutureOrderSchema
from services.synthetic_future_order_service import enter_synthetic_future, exit_synthetic_future
from utils.logging import get_logger

logger = get_logger(__name__)
api = Namespace("syntheticfutureorder", description="Enter or exit synthetic future positions")
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10 per second")


@api.route("/", strict_slashes=False)
class SyntheticFutureOrder(Resource):
    @limiter.limit(API_RATE_LIMIT)
    def post(self):
        """Enter or exit a synthetic future position using option legs."""
        try:
            data = SyntheticFutureOrderSchema().load(request.json)
            api_key = data["apikey"]

            if data["action"] == "enter":
                _, response_data, status_code = enter_synthetic_future(data, api_key)
            else:
                _, response_data, status_code = exit_synthetic_future(data, api_key)

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
