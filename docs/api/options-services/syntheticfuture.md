# SyntheticFuture

Calculate a synthetic futures price using ATM options.

## Endpoint URL

```http
Local Host   :  POST http://127.0.0.1:5000/api/v1/syntheticfuture
Ngrok Domain :  POST https://<your-ngrok-domain>.ngrok-free.app/api/v1/syntheticfuture
Custom Domain:  POST https://<your-custom-domain>/api/v1/syntheticfuture
```

## Request

```json
{
  "apikey": "<your_app_apikey>",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "expiry_date": "25NOV25"
}
```

```json
{
  "status": "success",
  "underlying": "NIFTY",
  "underlying_ltp": 25910.05,
  "expiry": "25NOV25",
  "atm_strike": 25900.0,
  "synthetic_future_price": 25980.05
}
```

Formula: `synthetic future = strike + call premium - put premium`.

## Request Fields

| Field | Description |
|-------|-------------|
| `apikey` | OpenAlgo API key |
| `underlying` | Underlying symbol, for example `NIFTY` |
| `exchange` | Underlying exchange, for example `NSE_INDEX` |
| `expiry_date` | Expiry in `DDMMMYY` format |

Synthetic-futures order entry and exit are handled by [`SyntheticFutureOrder`](./syntheticfutureorder.md).

---

**Back to**: [API Documentation](../README.md)
