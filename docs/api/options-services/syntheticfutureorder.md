# SyntheticFutureOrder

Place synthetic-futures BUY or SELL trades by submitting paired option legs.

## Endpoint URL

```http
POST http://127.0.0.1:5000/api/v1/syntheticfutureorder
```

Send `action` as `BUY` or `SELL`. `BUY` buys the call and sells the put; `SELL` buys the put and sells the call. Entry places the BUY leg first. If the second leg fails, OpenAlgo attempts to square off the first. For exits, include the two explicit closing legs in `legs`; these are submitted through `basketorder` so the exact symbols can be closed. Neither operation guarantees atomic execution.

## BUY or SELL

```json
{
  "apikey": "<your_app_apikey>",
  "action": "BUY",
  "strategy": "Synthetic Future",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "expiry_date": "25NOV25",
  "offset": "ATM",
  "quantity": 75,
  "pricetype": "MARKET",
  "product": "MIS"
}
```

Use `action: "BUY"` for a synthetic long (buy call, sell put) or `action: "SELL"` for a synthetic short (buy put, sell call). `offset` defaults to `ATM` and accepts `ATM`, `ITM1`-`ITM50`, or `OTM1`-`OTM50`. The paired option legs use inverse offsets to resolve to the same strike.

## Exit

Send the two symbols and quantities from the entry response. OpenAlgo submits the opposite orders to close the pair.

```json
{
  "apikey": "<your_app_apikey>",
  "action": "SELL",
  "strategy": "Synthetic Future",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "legs": [
    {"symbol": "NIFTY25NOV2525900CE", "exchange": "NFO", "action": "SELL", "quantity": 75, "pricetype": "MARKET", "product": "MIS"},
    {"symbol": "NIFTY25NOV2525900PE", "exchange": "NFO", "action": "BUY", "quantity": 75, "pricetype": "MARKET", "product": "MIS"}
  ]
}
```

Use `action: "SELL"` to close a previously BUY synthetic position, or `action: "BUY"` to close a previously SELL synthetic position. Entry can partially execute. If its second leg fails, inspect `square_off_status` and `square_off_results`; a failed square-off can leave an open position. Exit may also partially succeed. Check every result before retrying or taking corrective action.

See [`SyntheticFuture`](./syntheticfuture.md) for synthetic-futures price calculation.
