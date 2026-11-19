# SyntheticFutureOrder

Enter or exit a synthetic-futures position by submitting its paired option legs.

## Endpoint URL

```http
POST http://127.0.0.1:5000/api/v1/syntheticfutureorder
```

Send `action` as `enter` or `exit`. Entry places a BUY leg followed by a SELL leg. If the second entry leg fails, OpenAlgo attempts to square off the first. Exit submits the explicit option legs through `basketorder`; neither operation guarantees atomic execution.

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
  "offset": "ATM",
  "quantity": 75,
  "pricetype": "MARKET",
  "product": "MIS"
}
```

`LONG` buys the call and sells the put; `SHORT` buys the put and sells the call. `offset` defaults to `ATM` and accepts `ATM`, `ITM1`-`ITM50`, or `OTM1`-`OTM50`. The paired option legs use inverse offsets to resolve to the same strike.

## Exit

Send the two symbols and quantities from the entry response. OpenAlgo submits the opposite orders to close the pair.

```json
{
  "apikey": "<your_app_apikey>",
  "action": "exit",
  "strategy": "Synthetic Future",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "legs": [
    {"symbol": "NIFTY25NOV2525900CE", "exchange": "NFO", "action": "SELL", "quantity": 75, "pricetype": "MARKET", "product": "MIS"},
    {"symbol": "NIFTY25NOV2525900PE", "exchange": "NFO", "action": "BUY", "quantity": 75, "pricetype": "MARKET", "product": "MIS"}
  ]
}
```

Entry can partially execute. If its second leg fails, inspect `square_off_status` and `square_off_results`; a failed square-off can leave an open position. Exit may also partially succeed. Check every result before retrying or taking corrective action.

See [`SyntheticFuture`](./syntheticfuture.md) for synthetic-futures price calculation.
