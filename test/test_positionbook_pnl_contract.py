from types import SimpleNamespace

from broker.deltaexchange.mapping import order_data as delta
from broker.firstock.mapping import order_data as firstock
from services.positionbook_service import format_position_data


def test_firstock_returns_numeric_realized_and_total_pnl(monkeypatch):
    monkeypatch.setattr(firstock, "get_symbol", lambda *_: "TEST")
    rows = firstock.map_position_data(
        {"status": "success", "data": [{"exchange": "NSE", "RealizedPNL": "10.00"}]}
    )
    [position] = format_position_data(firstock.transform_positions_data(rows))

    assert position["realized_pnl"] == position["pnl"] == 10.0


def test_delta_preserves_both_multiplier_fields_without_rounding(monkeypatch):
    monkeypatch.setattr(delta, "get_symbol", lambda *_: "BTCUSD.P")
    monkeypatch.setattr(delta, "get_symbol_info", lambda *_: SimpleNamespace(contract_value=0.001))
    rows = delta.map_position_data(
        [{"product_id": 1, "size": 2, "realized_pnl": "10.00", "unrealized_pnl": "25.00"}]
    )
    [position] = format_position_data(delta.transform_positions_data(rows))

    assert position["contract_multiplier"] == position["lot_size"] == 0.001
    assert position["realized_pnl"] == 10.0
    assert position["pnl"] == 35.0
