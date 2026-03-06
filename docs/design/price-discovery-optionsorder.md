# Price Discovery for /optionsorder Endpoint

## Problem Statement

Some brokers have discontinued support for MARKET orders on options contracts. Users need automatic price discovery to fetch the current option premium (LTP) and use it as the limit price when placing LIMIT orders.

## Current Behavior

The `/optionsorder` endpoint currently:
1. ✅ Automatically resolves option symbol based on underlying + offset (ATM/ITM/OTM)
2. ✅ Fetches underlying LTP for strike calculation
3. ❌ Does NOT fetch option premium (LTP)
4. ❌ Requires manual `price` parameter for LIMIT orders

## Proposed Solution

Add automatic price discovery using **existing parameters** - no new fields needed!

**Trigger Logic:**
- When `pricetype="LIMIT"` AND `price=0.0` → **Enable price discovery**
- Fetch the resolved option's current LTP
- Use it as the limit price automatically
- Provides flexibility with price adjustment (e.g., +/- percentage or absolute value)

## Design Decisions

### 1. Use Existing `price` Parameter as Trigger

**No new parameter needed!**

**Behavior:**
- When `pricetype="LIMIT"` AND `price=0.0`: Automatically fetch option LTP and use as price
- When `pricetype="LIMIT"` AND `price>0.0`: Use manual price (existing behavior)
- When `pricetype="MARKET"`: Ignore price parameter (existing behavior)

**Benefits:**
- ✅ Zero breaking changes
- ✅ Intuitive: "I want LIMIT order but don't know the price (0.0) → discover it"
- ✅ No schema changes needed
- ✅ Cleaner API design

### 2. Optional Price Adjustment Parameters (NEW)

**`price_adjustment_type`**: `"percentage"` | `"absolute"` | `null` (default: `"percentage"`)
**`price_adjustment_value`**: Float (default: `2.0`)

**Adjustment Logic (Action-Aware):**

The adjustment is applied **based on the order action** to improve fill probability.

**Default Behavior:** When `price=0.0` is set without specifying adjustment parameters, the system automatically applies a **2% adjustment** (percentage type).

- **BUY orders:** Adjustment is **ADDED** to LTP (willing to pay more)
- **SELL orders:** Adjustment is **SUBTRACTED** from LTP (willing to receive less)

**Examples:**

| Action | Type | Value | LTP | Calculation | Final Price |
|--------|------|-------|-----|-------------|-------------|
| BUY | percentage | 2.0 | 100 | 100 + (100 × 2%) | 102.00 |
| SELL | percentage | 2.0 | 100 | 100 - (100 × 2%) | 98.00 |
| BUY | absolute | 5.0 | 100 | 100 + 5 | 105.00 |
| SELL | absolute | 5.0 | 100 | 100 - 5 | 95.00 |

**Rationale:**
- For **BUY**: Adding premium increases chance of order execution (pay slightly more)
- For **SELL**: Reducing price increases chance of order execution (receive slightly less)
- This matches real-world trading behavior for better fill rates

**Note:** These are the ONLY new schema fields needed (just 2 fields, not 3!)

**Default Values:**
- If not specified, `price_adjustment_type` defaults to `"percentage"`
- If not specified, `price_adjustment_value` defaults to `2.0` (2%)
- This means `price=0.0` alone will apply a 2% adjustment automatically

### 3. Response Enhancement

**No changes to response structure needed!**

The existing response already contains all necessary information:
- `orderid`: Order ID from broker
- `symbol`: Resolved option symbol
- `exchange`: Exchange (NFO/BFO)
- `underlying_ltp`: Already returned from symbol resolution
- `offset`, `option_type`: Already returned

**Rationale:**
- Price discovery is an internal implementation detail
- Users can verify the order price through order book/tradebook APIs
- Keeps response structure consistent and simple
- No breaking changes to response format

## Implementation Changes

### File 1: `restx_api/schemas.py`

**Location:** Line 167-210 (OptionsOrderSchema)

**Changes:** Add ONLY 2 new optional fields (price adjustment parameters)

```python
class OptionsOrderSchema(Schema):
    # ... existing fields (including price field) ...

    # NEW: Price adjustment fields (ONLY 2 new fields!)
    price_adjustment_type = fields.Str(
        missing=None,
        validate=validate.OneOf(["percentage", "absolute", None]),
        allow_none=True,
        metadata={"description": "Type of price adjustment: percentage or absolute"}
    )
    price_adjustment_value = fields.Float(
        missing=0.0,
        metadata={"description": "Adjustment value (% or absolute amount)"}
    )
```

**Note:** The existing `price` field (line 199-201) remains unchanged. We use `price=0.0` as the trigger for price discovery.

### File 2: `services/place_options_order_service.py`

**Location:** After line 227 (after symbol resolution, before order construction)

**Changes:**
1. Add price discovery logic after symbol resolution
2. Fetch option LTP using `get_quotes()`
3. Apply price adjustment if specified
4. Override `price` parameter with discovered price
5. Add discovered price info to response

**Pseudocode:**
```python
# After line 227 (symbol resolved)
pricetype = options_data.get("pricetype", "MARKET")
price = options_data.get("price", 0.0)
action = options_data.get("action", "BUY").upper()

option_ltp = None
discovered_price = None

# Trigger: LIMIT order with price=0.0 means "discover the price"
if pricetype == "LIMIT" and price == 0.0:
    # Fetch option LTP
    success, quote_response, status_code = get_quotes(
        symbol=resolved_symbol,
        exchange=resolved_exchange,
        api_key=symbol_api_key
    )

    if not success:
        logger.error(f"Price discovery failed: {quote_response.get('message')}")
        return False, {
            "status": "error",
            "message": f"Failed to fetch option price for {resolved_symbol}"
        }, status_code

    option_ltp = quote_response.get("data", {}).get("ltp")

    if not option_ltp or option_ltp <= 0:
        return False, {
            "status": "error",
            "message": f"Invalid option LTP received: {option_ltp}"
        }, 400

    # Apply adjustment based on action
    adjustment_type = options_data.get("price_adjustment_type")
    adjustment_value = options_data.get("price_adjustment_value", 0.0)

    if adjustment_type == "percentage":
        # BUY: Add premium (pay more), SELL: Reduce price (receive less)
        if action == "BUY":
            discovered_price = option_ltp * (1 + adjustment_value / 100)
        else:  # SELL
            discovered_price = option_ltp * (1 - adjustment_value / 100)
    elif adjustment_type == "absolute":
        # BUY: Add amount, SELL: Subtract amount
        if action == "BUY":
            discovered_price = option_ltp + adjustment_value
        else:  # SELL
            discovered_price = option_ltp - adjustment_value
    else:
        # No adjustment
        discovered_price = option_ltp

    # Round to tick size (0.05 for options)
    discovered_price = round(discovered_price / 0.05) * 0.05

    # Validate final price
    if discovered_price <= 0:
        return False, {
            "status": "error",
            "message": f"Invalid discovered price: {discovered_price}"
        }, 400

    # Override price parameter
    options_data["price"] = discovered_price

    logger.info(
        f"Price discovery: Symbol={resolved_symbol}, Action={action}, "
        f"LTP={option_ltp}, Adjustment={adjustment_type}:{adjustment_value}, "
        f"Final Price={discovered_price}"
    )
else:
    logger.debug(f"Using manual price: {price} (no discovery needed)")
```

**Import Required:**
```python
from services.quotes_service import get_quotes
```

### File 3: `restx_api/options_order.py`

**Location:** Docstring (lines 1-30)

**Changes:** Update API documentation to include new parameters

```python
"""
Request Body:
{
    ...existing fields...
    "pricetype": "LIMIT",
    "price": 0.0,  // Set to 0.0 to trigger automatic price discovery
    "price_adjustment_type": null,  // Optional: "percentage" or "absolute"
    "price_adjustment_value": 0.0,  // Optional: Adjustment amount
}

Response (same as before - no changes):
{
    "status": "success",
    "orderid": "25102800000007",
    "symbol": "NIFTY28OCT2526000CE",
    "exchange": "NFO",
    "underlying": "NIFTY",
    "underlying_ltp": 25966.05,
    "offset": "ATM",
    "option_type": "CE"
}

Note: Price discovery is transparent - no new response fields.
Users can verify order price via order book/tradebook APIs.
"""
```

## Implementation Steps

### Step 1: Update Schema (Low Risk)
- Add ONLY 2 new optional fields to `OptionsOrderSchema`
  - `price_adjustment_type`
  - `price_adjustment_value`
- All fields have sensible defaults (backward compatible)
- No breaking changes
- **No `price_discovery` field needed!**

### Step 2: Implement Price Discovery Logic (Medium Risk)
- Add logic in `place_options_order_service.py` after line 227
- Import `get_quotes` from `quotes_service`
- Check if `pricetype=="LIMIT"` AND `price==0.0` → trigger discovery
- Handle quote fetch failures gracefully
- Apply price adjustments with proper rounding

### Step 3: Update Documentation (Low Risk)
- Update API docstring in `options_order.py`
- Add examples to API documentation

## Error Handling

1. **Quote Fetch Failure:**
   - Log error with details
   - Return error response: `{"status": "error", "message": "Failed to fetch option price for NIFTY28OCT2526000CE"}`
   - Do NOT fall back to price=0.0 (would result in invalid order)

2. **Invalid Adjustment Parameters:**
   - Schema validation catches invalid types
   - Ignore adjustment if `adjustment_type` is null (use raw LTP)

3. **Zero/Negative LTP:**
   - Validate LTP > 0 before using
   - Return error if invalid: `{"status": "error", "message": "Invalid option LTP received: 0.0"}`

4. **Price Discovery Not Needed:**
   - If `pricetype != "LIMIT"` or `price > 0.0`, skip discovery logic entirely
   - No error, just use existing flow

## Testing Scenarios

1. ✅ Price discovery with no adjustment (`price=0.0`, no adjustment params)
2. ✅ BUY order with percentage adjustment (2.0 → adds 2% to LTP)
3. ✅ SELL order with percentage adjustment (2.0 → subtracts 2% from LTP)
4. ✅ BUY order with absolute adjustment (5.0 → adds ₹5 to LTP)
5. ✅ SELL order with absolute adjustment (5.0 → subtracts ₹5 from LTP)
6. ✅ Price discovery failure (should return error if price=0.0 and fetch fails)
7. ✅ Backward compatibility (`price>0.0` uses manual price)
8. ✅ MARKET order (price parameter ignored as before)
9. ✅ Negative discovered price validation (should return error)
10. ✅ Tick size rounding (0.05 for options)

## Example API Calls

### Example 1: Basic Price Discovery (No Adjustment)
```json
{
  "apikey": "your_api_key",
  "strategy": "options_scalping",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "expiry_date": "28OCT25",
  "offset": "ATM",
  "option_type": "CE",
  "action": "BUY",
  "quantity": 75,
  "pricetype": "LIMIT",
  "product": "MIS",
  "price": 0.0
}
```

**Note:** `price=0.0` triggers automatic price discovery!

**Response:**
```json
{
  "status": "success",
  "orderid": "25102800000007",
  "symbol": "NIFTY28OCT2526000CE",
  "exchange": "NFO",
  "underlying": "NIFTY",
  "underlying_ltp": 25966.05,
  "offset": "ATM",
  "option_type": "CE"
}
```

**Note:** Response structure unchanged. Price discovery happens transparently.

### Example 2: SELL Order with +2% Adjustment
```json
{
  "apikey": "your_api_key",
  "strategy": "options_scalping",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "expiry_date": "28OCT25",
  "offset": "ITM2",
  "option_type": "PE",
  "action": "SELL",
  "quantity": 150,
  "pricetype": "LIMIT",
  "product": "MIS",
  "price": 0.0,
  "price_adjustment_type": "percentage",
  "price_adjustment_value": 2.0
}
```

**Note:** For SELL orders, 2% is **SUBTRACTED** from LTP for better fill probability.

**Response:**
```json
{
  "status": "success",
  "orderid": "25102800000008",
  "symbol": "NIFTY28OCT2525900PE",
  "exchange": "NFO",
  "underlying": "NIFTY",
  "underlying_ltp": 25966.05,
  "offset": "ITM2",
  "option_type": "PE"
}
```

**Calculation:** LTP = 95.75, SELL action → 95.75 - (95.75 × 2%) = 93.84 (rounded to 93.85)

---

### Example 3: BUY Order with +2% Adjustment
```json
{
  "apikey": "your_api_key",
  "underlying": "BANKNIFTY",
  "exchange": "NSE_INDEX",
  "expiry_date": "30OCT25",
  "offset": "OTM3",
  "option_type": "CE",
  "action": "BUY",
  "quantity": 45,
  "pricetype": "LIMIT",
  "product": "MIS",
  "price": 0.0,
  "price_adjustment_type": "percentage",
  "price_adjustment_value": 2.0
}
```

**Note:** For BUY orders, 2% is **ADDED** to LTP for better fill probability.

**Response:**
```json
{
  "status": "success",
  "orderid": "25102800000009",
  "symbol": "BANKNIFTY30OCT2549300CE",
  "exchange": "NFO",
  "underlying": "BANKNIFTY",
  "underlying_ltp": 48966.25,
  "offset": "OTM3",
  "option_type": "CE"
}
```

**Calculation:** LTP = 150.25, BUY action → 150.25 + (150.25 × 2%) = 153.26 (rounded to 153.25)

## Benefits

1. **Convenience:** No need to manually fetch option premium
2. **Accuracy:** Uses real-time LTP from broker
3. **Flexibility:** Supports price adjustments for better fill rates
4. **Backward Compatible:** Existing code continues to work (price>0 uses manual price)
5. **Broker Agnostic:** Works with all brokers that support quotes
6. **Clean Design:** No extra `price_discovery` boolean needed - uses existing `price` field
7. **Intuitive:** `price=0.0` naturally means "I don't know the price, discover it"
8. **Transparent:** No response changes - price discovery is an internal optimization
9. **Simple API:** Only 2 new optional parameters (adjustment type/value)

## Migration Path

**Existing users:** No changes required!
- If they're already passing `price>0` for LIMIT orders → continues to work
- If they're passing `price=0` for LIMIT orders → now gets automatic discovery (improvement!)

**New users:** Simply set `price=0.0` for LIMIT orders to enable price discovery

## Action-Aware Adjustment Summary

| Order Action | Adjustment Direction | Reason |
|--------------|---------------------|---------|
| **BUY** | Add to LTP | Willing to pay more for better fill |
| **SELL** | Subtract from LTP | Willing to receive less for better fill |

**Example with 2% adjustment:**
- LTP = ₹100
- BUY: 100 + 2% = ₹102 (pay premium)
- SELL: 100 - 2% = ₹98 (accept discount)

This ensures the adjustment **always improves fill probability** regardless of order direction.

## Future Enhancements

1. Support for bid/ask-based pricing (instead of LTP)
   - BUY: Use ask price + adjustment
   - SELL: Use bid price - adjustment
2. Configurable tick size per instrument type
3. Price discovery for multi-leg orders (`/optionsmultiorder`)
4. Price discovery caching to reduce API calls
5. Adaptive adjustment based on volatility/spread

