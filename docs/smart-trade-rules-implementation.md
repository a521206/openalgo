# Smart Trade Rules Implementation

## Overview

Smart Trade Rules provide automated risk controls and position management for trading operations. These rules are applied to all incoming orders before execution.

## Features Implemented

### 1. Frontend Changes

**File: `frontend/src/pages/admin/SmartTradeRules.tsx`**

- **Default State Changes:**
  - `smartTradeEnabled`: Changed from `false` to `true` (enabled by default)
  - `preventDuplicateBuy`: Changed from `false` to `true` (enabled by default)
  - `preventDuplicateSell`: Changed from `false` to `true` (enabled by default)

- **UI Updates:**
  - Updated "Maximum Position Size" label to "Maximum Position Size (Lots)"
  - Updated helper text to clarify: "Maximum number of lots for F&O, quantity for equity"
  - Updated documentation section to reflect lot-based validation for F&O

### 2. Backend Service Layer

**New File: `services/smart_trade_rules_service.py`**

Core validation service that enforces all smart trade rules:

#### Functions:

1. **`get_lot_size(symbol: str, exchange: str) -> int`**
   - Returns 1 for equity exchanges (NSE, BSE)
   - Returns actual lot size for F&O exchanges (NFO, BFO, MCX, CDS)
   - Uses `get_symbol_info()` from token database for lot size lookup

2. **`validate_against_smart_trade_rules(order_data, current_position_qty, broker) -> tuple[bool, str | None]`**
   - Validates orders against all configured smart trade rules
   - Returns (True, None) if validation passes
   - Returns (False, error_message) if order should be blocked

#### Rules Enforced:

1. **Prevent Duplicate BUY**
   - Blocks BUY orders if a long position already exists
   - Error: "Smart Trade Rule: Duplicate BUY blocked. You already have a long position of {qty} in {symbol}"

2. **Prevent Duplicate SELL**
   - Blocks SELL orders if no long position exists
   - Error: "Smart Trade Rule: Duplicate SELL blocked. No open long position exists in {symbol}"

3. **Maximum Position Size**
   - For F&O: Validates in lots (position_qty / lot_size)
   - For Equity: Validates in quantity
   - Calculates new position after order execution
   - Error: "Smart Trade Rule: Maximum position size exceeded. Limit: X lots/qty, New position would be: Y lots/qty"

4. **Maximum Order Value**
   - Validates order value (quantity × price) against limit
   - Error: "Smart Trade Rule: Maximum order value exceeded. Limit: ₹X, Order value: ₹Y"

5. **Allow Intraday Only (MIS)**
   - Blocks all non-MIS orders when enabled
   - Error: "Smart Trade Rule: Only intraday (MIS) orders allowed. Product type '{type}' is blocked"

6. **Block CNC Orders**
   - Blocks delivery (CNC) orders
   - Error: "Smart Trade Rule: CNC (delivery) orders are blocked"

7. **Block NRML Orders**
   - Blocks carryforward (NRML) orders
   - Error: "Smart Trade Rule: NRML (carryforward) orders are blocked"

### 3. Integration with Order Placement

**Modified Files:**
- `services/place_order_service.py`
- `services/place_smart_order_service.py`

**Integration Logic:**

Both order placement services now:
1. Fetch current position quantity using broker's `get_open_position()` function
2. Call `validate_against_smart_trade_rules()` before placing the order
3. Block order and return error if validation fails
4. Proceed with order placement if validation passes

**Code Flow:**
```python
# Get current position
current_position_qty = broker_module.get_open_position(symbol, exchange, product_type, auth_token)

# Validate against smart trade rules
is_valid, error_message = validate_against_smart_trade_rules(order_data, current_position_qty, broker)

if not is_valid:
    # Block order and return error
    return False, {"status": "error", "message": error_message}, 400

# Proceed with order placement
```

### 4. Database Changes

**File: `database/settings_db.py`**

Updated default values in Settings model:
- `smart_trade_enabled`: Changed from `False` to `True`
- `prevent_duplicate_buy`: Changed from `False` to `True`
- `prevent_duplicate_sell`: Changed from `False` to `True`
- Updated comment for `max_position_size`: "Maximum position size per symbol (lots for F&O, qty for equity)"

**File: `migrations/add_smart_trade_rules_columns.py`**

Updated migration script defaults:
- `smart_trade_enabled`: Changed from `DEFAULT 0` to `DEFAULT 1`
- `prevent_duplicate_buy`: Changed from `DEFAULT 0` to `DEFAULT 1`
- `prevent_duplicate_sell`: Changed from `DEFAULT 0` to `DEFAULT 1`

## Usage

### For New Installations

Smart Trade Rules are enabled by default with:
- Master switch: ON
- Prevent Duplicate BUY: ON
- Prevent Duplicate SELL: ON
- All other rules: OFF (can be configured as needed)

### For Existing Installations

Run the migration script to add columns (if not already done):
```bash
uv run python migrations/add_smart_trade_rules_columns.py
```

Then update settings via the UI at `/admin/smart-trade-rules` or programmatically.

## Testing

Test the following scenarios:

1. **Duplicate BUY Prevention:**
   - Place a BUY order for a symbol
   - Try to place another BUY order for the same symbol
   - Should be blocked with appropriate error message

2. **Duplicate SELL Prevention:**
   - Try to place a SELL order for a symbol with no position
   - Should be blocked with appropriate error message

3. **Position Size Limits:**
   - Set max_position_size to a specific value
   - For F&O: Try to exceed the lot limit
   - For Equity: Try to exceed the quantity limit
   - Should be blocked when limit is exceeded

4. **Order Value Limits:**
   - Set max_order_value to a specific amount
   - Try to place an order exceeding this value
   - Should be blocked with appropriate error message

5. **Product Type Restrictions:**
   - Enable "Intraday Only" or block specific product types
   - Try to place orders with blocked product types
   - Should be blocked with appropriate error message

## Notes

- Smart trade rules apply to ALL order placement methods (API, webhooks, TradingView, manual orders)
- Rules are checked BEFORE the order is sent to the broker
- Position quantity is fetched in real-time from the broker
- Lot size information is retrieved from the master contract database
- All validations are logged and errors are returned to the caller

