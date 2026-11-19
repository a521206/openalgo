# SyntheticFuture

Calculate a synthetic futures price using ATM options. The `enter` and `exit` sections below describe a proposed paired-order API contract; those actions are not implemented yet.

## Endpoint URL

```http
Local Host   :  POST http://127.0.0.1:5000/api/v1/syntheticfuture
Ngrok Domain :  POST https://<your-ngrok-domain>.ngrok-free.app/api/v1/syntheticfuture
Custom Domain:  POST https://<your-custom-domain>/api/v1/syntheticfuture
```

## Actions

Send `action` as `calculate`, `enter`, or `exit`. Calculate does not place orders.

## Calculate

```json
{
  "apikey": "<your_app_apikey>",
  "action": "calculate",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "expiry_date": "25NOV25"
}
```

The response includes the underlying LTP, ATM strike, and synthetic futures price:

```json
{
  "status": "success",
  "action": "calculate",
  "underlying": "NIFTY",
  "underlying_ltp": 25910.05,
  "expiry": "25NOV25",
  "atm_strike": 25900.0,
  "synthetic_future_price": 25980.05
}
```

Formula: `synthetic future = strike + call premium - put premium`.

## Enter

```json
{
  "apikey": "<your_app_apikey>",
  "action": "enter",
  "strategy": "Synthetic Future",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "expiry_date": "25NOV25",
  "direction": "LONG",
  "quantity": 75,
  "pricetype": "MARKET",
  "product": "MIS"
}
```

Use `direction: "LONG"` to buy the ATM call and sell the ATM put. Use `direction: "SHORT"` to sell the ATM call and buy the ATM put. Both legs use the same ATM strike and expiry.

The response uses the same `results` array pattern as `optionsmultiorder`:

```json
{
  "status": "success",
  "underlying": "NIFTY",
  "underlying_ltp": 25910.05,
  "results": [
    {"leg": 1, "symbol": "NIFTY25NOV2525900CE", "exchange": "NFO", "offset": "ATM", "option_type": "CE", "action": "BUY", "status": "success", "orderid": "<order-id>"},
    {"leg": 2, "symbol": "NIFTY25NOV2525900PE", "exchange": "NFO", "offset": "ATM", "option_type": "PE", "action": "SELL", "status": "success", "orderid": "<order-id>"}
  ]
}
```

If either leg fails, OpenAlgo attempts to square off the successful leg, returns `status: "error"` with the per-leg results, and sends an alert.

## Exit

Send `action: "exit"` with the two symbols and quantities returned by entry. OpenAlgo places the opposite orders to close the pair.

```json
{
  "apikey": "<your_app_apikey>",
  "strategy": "Synthetic Future",
  "action": "exit",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "legs": [
    {"symbol": "NIFTY25NOV2525900CE", "exchange": "NFO", "action": "SELL", "quantity": 75, "pricetype": "MARKET", "product": "MIS"},
    {"symbol": "NIFTY25NOV2525900PE", "exchange": "NFO", "action": "BUY", "quantity": 75, "pricetype": "MARKET", "product": "MIS"}
  ]
}
```

Exit legs use explicit symbols, like `basketorder`, because the original entry strike must be closed. The response reports both orders in `results`. If an exit leg fails, OpenAlgo returns the per-leg results and sends an alert.

## Request Fields

| Field | Description |
|-------|-------------|
| `apikey` | OpenAlgo API key |
| `action` | `calculate`, `enter`, or `exit` |
| `strategy` | Strategy identifier, as used by options order APIs |
| `underlying` | Underlying symbol, for example `NIFTY`; required for calculate and entry |
| `exchange` | Underlying exchange, for example `NSE_INDEX`; required for calculate and entry |
| `expiry_date` | Expiry in `DDMMMYY` format |
| `direction` | `LONG` or `SHORT`, for entry |
| `quantity` | Quantity per leg, for entry |
| `pricetype` | Price type, such as `MARKET` or `LIMIT`, for entry |
| `product` | Product type, such as `MIS` or `NRML` |
| `legs` | Explicit option symbols and order details, for exit |

Order placement is not atomic. OpenAlgo attempts to close a successfully placed entry leg if its pair fails, but broker execution can prevent a square-off. Check the per-leg results and alert if the endpoint reports failure.

---

**Back to**: [API Documentation](../README.md)
