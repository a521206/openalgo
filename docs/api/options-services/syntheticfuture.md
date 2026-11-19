# SyntheticFuture

Calculate a synthetic futures price using ATM options, or submit the corresponding option legs.

## Endpoint URL

```http
Local Host   :  POST http://127.0.0.1:5000/api/v1/syntheticfuture
Ngrok Domain :  POST https://<your-ngrok-domain>.ngrok-free.app/api/v1/syntheticfuture
Custom Domain:  POST https://<your-custom-domain>/api/v1/syntheticfuture
```

## Actions

Send `action` as `calculate`, `enter`, or `exit`. If omitted, it defaults to `calculate` for compatibility. Entry places its two option legs sequentially through the existing `optionsorder` service. Exit submits the explicit legs in one `basketorder` request.

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
  "offset": "ITM1",
  "quantity": 75,
  "pricetype": "MARKET",
  "product": "MIS"
}
```

Use `direction: "LONG"` to buy the call and sell the put. Use `direction: "SHORT"` to buy the put and sell the call. `offset` selects the strike relative to ATM and defaults to `ATM`; accepted values are `ATM`, `ITM1`-`ITM50`, and `OTM1`-`OTM50`. Both legs always use the same strike: the put uses the inverse moneyness offset (for example, call `ITM1` pairs with put `OTM1`).

The response reports each entry order in `results`:

```json
{
  "status": "success",
  "underlying": "NIFTY",
  "underlying_ltp": 25910.05,
  "results": [
    {"leg": 1, "symbol": "NIFTY25NOV2525850CE", "exchange": "NFO", "offset": "ITM1", "option_type": "CE", "action": "BUY", "status": "success", "orderid": "<order-id>"},
    {"leg": 2, "symbol": "NIFTY25NOV2525850PE", "exchange": "NFO", "offset": "OTM1", "option_type": "PE", "action": "SELL", "status": "success", "orderid": "<order-id>"}
  ]
}
```

In automatic mode, entry places the BUY leg first and uses its underlying LTP when resolving the second leg, ensuring both legs use the same strike selected by `offset`. If the first leg fails, the second is not sent. If the second leg fails, OpenAlgo attempts to close the first leg with an opposite MARKET order. The response includes both entry results and `square_off_status` / `square_off_results` for that recovery attempt. A failed square-off leaves exposure that must be managed manually. In semi-automatic mode, both symbols are resolved and queued together for approval; after approval, basket execution may partially succeed and does not use the sequential rollback flow. Analyze mode simulates the automatic flow. Order placement is not atomic, and broker-side execution can differ from the returned result.

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

Exit legs use explicit symbols and are submitted via the existing `basketorder` service. The response follows that service's contract (`status` and per-order `results`, each including `symbol`, `status`, and either `orderid` or `message`). Orders may partially succeed; the service does not guarantee atomic execution or rollback.

## Request Fields

| Field | Description |
|-------|-------------|
| `apikey` | OpenAlgo API key |
| `action` | `calculate`, `enter`, or `exit` |
| `strategy` | Strategy identifier, as used by options order APIs |
| `underlying` | Underlying symbol, for example `NIFTY`; required for all actions |
| `exchange` | Underlying exchange, for example `NSE_INDEX`; required for all actions |
| `expiry_date` | Expiry in `DDMMMYY` format; required for calculate and entry |
| `direction` | `LONG` or `SHORT`, required for entry |
| `offset` | Strike offset from ATM; optional for entry, defaults to `ATM`; supports `ITM1`-`ITM50` and `OTM1`-`OTM50` |
| `quantity` | Positive quantity per leg, required for entry |
| `pricetype` | `MARKET`, `LIMIT`, `SL`, or `SL-M`; optional for entry, defaults to `MARKET` |
| `product` | `MIS` or `NRML`; optional for entry, defaults to `MIS` |
| `price` | Non-negative order price; optional for entry, defaults to `0` |
| `trigger_price` | Non-negative trigger price; optional for entry, defaults to `0` |
| `disclosed_quantity` | Non-negative disclosed quantity; optional for entry, defaults to `0` |
| `legs` | Exactly two explicit basket-order objects, required for exit |

Order placement is not atomic. Entry uses two `optionsorder` calls and attempts a MARKET square-off if the second leg fails; exit uses `basketorder` and may partially succeed. Check every result before retrying or taking corrective action.

---

**Back to**: [API Documentation](../README.md)
