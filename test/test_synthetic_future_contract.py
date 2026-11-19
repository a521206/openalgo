import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
from marshmallow import ValidationError

from services import synthetic_future_order_service as order_service

schema_path = Path(__file__).parents[1] / "restx_api" / "schemas.py"
schema_spec = importlib.util.spec_from_file_location("openalgo_test_schemas", schema_path)
if schema_spec is None or schema_spec.loader is None:
    raise RuntimeError(f"Could not load API schemas from {schema_path}")
schemas = importlib.util.module_from_spec(schema_spec)
schema_spec.loader.exec_module(schemas)
SyntheticFutureSchema = schemas.SyntheticFutureSchema
SyntheticFutureOrderSchema = schemas.SyntheticFutureOrderSchema


def test_calculate_request_without_action_remains_valid():
    data = SyntheticFutureSchema().load(
        {
            "apikey": "key",
            "underlying": "NIFTY",
            "exchange": "NSE_INDEX",
            "expiry_date": "25NOV25",
        }
    )

    assert data["underlying"] == "NIFTY"


def test_order_schema_rejects_calculate_action():
    with pytest.raises(ValidationError):
        SyntheticFutureOrderSchema().load(
            {
                "apikey": "key",
                "action": "calculate",
                "underlying": "NIFTY",
                "exchange": "NSE_INDEX",
                "expiry_date": "25NOV25",
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "enter", "strategy": "Synthetic", "direction": "LONG"},
        {"action": "enter", "strategy": "Synthetic", "direction": "OTHER", "quantity": 1},
        {
            "action": "enter", "strategy": "Synthetic", "direction": "LONG",
            "quantity": 1, "offset": "ITM51",
        },
        {"action": "exit", "strategy": "Synthetic", "legs": []},
    ],
)
def test_action_specific_required_fields_are_validated(payload):
    with pytest.raises(ValidationError):
        SyntheticFutureOrderSchema().load(
            {
                "apikey": "key",
                "underlying": "NIFTY",
                "exchange": "NSE_INDEX",
                "expiry_date": "25NOV25",
                **payload,
            }
        )


def test_entry_places_inverse_offsets_at_same_strike(monkeypatch):
    calls = []

    def place_options_order(data, api_key):
        calls.append(data.copy())
        return True, {
            "symbol": f"NIFTY25NOV2525900{data['option_type']}",
            "exchange": "NFO",
            "orderid": f"order-{len(calls)}",
            "underlying_ltp": 25910.05,
        }, 200

    monkeypatch.setitem(
        sys.modules,
        "services.place_options_order_service",
        SimpleNamespace(place_options_order=place_options_order),
    )
    monkeypatch.setitem(
        sys.modules,
        "services.order_router_service",
        SimpleNamespace(should_route_to_pending=lambda *_: False),
    )
    request = {
        "underlying": "NIFTY",
        "exchange": "NSE_INDEX",
        "expiry_date": "25NOV25",
        "strategy": "Synthetic",
        "direction": "LONG",
        "offset": "ITM1",
        "quantity": 75,
        "pricetype": "MARKET",
        "product": "MIS",
        "price": 0,
        "trigger_price": 0,
        "disclosed_quantity": 0,
    }

    success, response, _ = order_service.enter_synthetic_future(request, "key")

    assert success is True
    assert [(leg["option_type"], leg["action"]) for leg in calls] == [
        ("CE", "BUY"),
        ("PE", "SELL"),
    ]
    assert calls[1]["underlying_ltp"] == 25910.05
    assert [leg["offset"] for leg in calls] == ["ITM1", "OTM1"]
    assert response["status"] == "success"


def test_first_leg_failure_skips_second_leg(monkeypatch):
    calls = []

    def place_options_order(data, api_key):
        calls.append(data.copy())
        return False, {"message": "first leg rejected"}, 500

    monkeypatch.setitem(
        sys.modules,
        "services.place_options_order_service",
        SimpleNamespace(place_options_order=place_options_order),
    )
    monkeypatch.setitem(
        sys.modules,
        "services.order_router_service",
        SimpleNamespace(should_route_to_pending=lambda *_: False),
    )
    request = {
        "underlying": "NIFTY", "exchange": "NSE_INDEX", "expiry_date": "25NOV25",
        "strategy": "Synthetic", "direction": "LONG", "offset": "ATM", "quantity": 75,
        "pricetype": "MARKET", "product": "MIS", "price": 0,
        "trigger_price": 0, "disclosed_quantity": 0,
    }

    success, response, status_code = order_service.enter_synthetic_future(request, "key")

    assert success is False
    assert status_code == 500
    assert len(calls) == 1
    assert [result["status"] for result in response["results"]] == ["error", "skipped"]
    assert response["square_off_status"] == "not_required"


def test_second_leg_failure_attempts_to_square_off_first(monkeypatch):
    calls = []
    square_off = {}

    def place_options_order(data, api_key):
        calls.append(data.copy())
        if len(calls) == 1:
            return True, {
                "symbol": "NIFTY25NOV2525900CE",
                "exchange": "NFO",
                "orderid": "entry-order",
                "underlying_ltp": 25910.05,
            }, 200
        return False, {"message": "second leg rejected"}, 500

    def place_basket_order(data, api_key):
        square_off.update(data)
        return True, {
            "results": [{"symbol": "NIFTY25NOV2525900CE", "status": "success"}]
        }, 200

    monkeypatch.setitem(
        sys.modules,
        "services.place_options_order_service",
        SimpleNamespace(place_options_order=place_options_order),
    )
    monkeypatch.setitem(
        sys.modules,
        "services.order_router_service",
        SimpleNamespace(should_route_to_pending=lambda *_: False),
    )
    monkeypatch.setitem(
        sys.modules,
        "services.basket_order_service",
        SimpleNamespace(place_basket_order=place_basket_order),
    )
    request = {
        "underlying": "NIFTY", "exchange": "NSE_INDEX", "expiry_date": "25NOV25",
        "strategy": "Synthetic", "direction": "LONG", "offset": "ATM", "quantity": 75,
        "pricetype": "MARKET", "product": "MIS", "price": 0,
        "trigger_price": 0, "disclosed_quantity": 0,
    }

    success, response, _ = order_service.enter_synthetic_future(request, "key")

    assert success is False
    assert response["results"][1]["message"] == "second leg rejected"
    assert response["square_off_status"] == "success"
    assert square_off["orders"] == [
        {
            "symbol": "NIFTY25NOV2525900CE",
            "exchange": "NFO",
            "action": "SELL",
            "quantity": 75,
            "pricetype": "MARKET",
            "product": "MIS",
        }
    ]


def test_short_entry_buys_put_before_selling_call(monkeypatch):
    calls = []

    def place_options_order(data, api_key):
        calls.append(data.copy())
        return True, {"symbol": "SYM", "exchange": "NFO", "underlying_ltp": 25910.05}, 200

    monkeypatch.setitem(
        sys.modules,
        "services.place_options_order_service",
        SimpleNamespace(place_options_order=place_options_order),
    )
    monkeypatch.setitem(
        sys.modules,
        "services.order_router_service",
        SimpleNamespace(should_route_to_pending=lambda *_: False),
    )
    request = {
        "underlying": "NIFTY",
        "exchange": "NSE_INDEX",
        "expiry_date": "25NOV25",
        "strategy": "Synthetic",
        "direction": "SHORT",
        "offset": "ATM",
        "quantity": 75,
        "pricetype": "MARKET",
        "product": "MIS",
        "price": 0,
        "trigger_price": 0,
        "disclosed_quantity": 0,
    }

    order_service.enter_synthetic_future(request, "key")

    assert [(leg["option_type"], leg["action"]) for leg in calls] == [
        ("PE", "BUY"),
        ("CE", "SELL"),
    ]


def test_exit_maps_explicit_symbols_to_basket_order(monkeypatch):
    captured = {}

    def place_basket_order(data, api_key):
        captured.update(data)
        return True, {"status": "success", "results": []}, 200

    monkeypatch.setitem(
        sys.modules,
        "services.basket_order_service",
        SimpleNamespace(place_basket_order=place_basket_order),
    )
    request = {
        "strategy": "Synthetic",
        "legs": [
            {"symbol": "NIFTY25NOV2525900CE", "exchange": "NFO", "action": "SELL", "quantity": 75},
            {"symbol": "NIFTY25NOV2525900PE", "exchange": "NFO", "action": "BUY", "quantity": 75},
        ],
    }

    order_service.exit_synthetic_future(request, "key")

    assert captured["orders"] == request["legs"]
