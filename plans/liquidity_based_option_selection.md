# Plan: Liquidity-Based Option Selection

## Problem

When placing options orders, if the resolved strike has `ask=0` or `bid=0` (no market participants), the order fails with "Invalid base price: 0". This is common for illiquid strikes.

## Solution

When a strike has poor liquidity, automatically evaluate ATM + 3 ITM strikes and select the one with best liquidity (highest OI + volume) that has valid bid/ask prices.

## Implementation

### Phase 1: Liquidity Selection Function

**File**: `services/place_options_order_service.py`

Add `select_best_liquid_strike()`:
- Input: underlying, expiry, option_type, api_key
- Evaluates ATM + 3 ITM strikes (4 total)
- Score: `liquidity_score = (oi * 0.7) + (volume * 0.3)`
- Must have bid > 0 AND ask > 0 to be eligible
- Returns strike with highest score, or error if none valid

### Phase 2: Integrate with Price Discovery

**File**: `services/place_options_order_service.py`

Modify price discovery (lines 235-386):

```
1. Read liquidity_fallback from get_smart_trade_rules()
2. If disabled → existing behavior (no fallback)
3. If offset == "ATM":
   - Always call select_best_liquid_strike()
4. Else:
   - Fetch quotes for original strike
   - If ask=0 or bid=0 → call select_best_liquid_strike()
5. Continue with price discovery
```

### Phase 3: Smart Trade Rules Integration

Add `liquidity_fallback` (default: True) as a global admin setting.

#### Database — `database/settings_db.py`
- Add column: `liquidity_fallback = Column(Boolean, default=True)`
- Add to `get_smart_trade_rules()` return dict
- Add to `set_smart_trade_rules()` parameters

#### Migrations
- `migrations/add_smart_trade_rules_columns.py` — add `("liquidity_fallback", "INTEGER DEFAULT 1")`
- `upgrade/migrate_smart_trade_rules.py` — add `("liquidity_fallback", "BOOLEAN DEFAULT 1")`

#### API — `blueprints/settings.py`
- Add `liquidity_fallback = data.get("liquidity_fallback")` to `update_smart_trade_rules_api()`

#### Frontend — `frontend/src/pages/admin/SmartTradeRules.tsx`
- Add `liquidity_fallback: boolean` to interface
- Add state, wire into fetch/save
- Add Switch toggle in "Order Rules" card:
```tsx
<div className="flex items-center justify-between">
  <div>
    <Label>Liquidity Fallback</Label>
    <p className="text-sm text-muted-foreground">
      Auto-select most liquid strike when requested option has no buyers/sellers
    </p>
  </div>
  <Switch checked={liquidityFallback} onCheckedChange={setLiquidityFallback} disabled={!smartTradeEnabled} />
</div>
```

### Phase 4: Logging

Log strikes evaluated, scores, selected strike, and fallback trigger reason.

## Response Enhancement

When fallback occurs, add to order response:
```json
{
  "symbol": "NIFTY28APR2622500PE",
  "original_symbol": "NIFTY28APR2622450PE",
  "liquidity_fallback": true,
  "fallback_reason": "Original strike had ask=0"
}
```

## Files to Modify

1. `services/place_options_order_service.py` — core logic + read setting
2. `database/settings_db.py` — column, getter, setter
3. `migrations/add_smart_trade_rules_columns.py` — column migration
4. `upgrade/migrate_smart_trade_rules.py` — upgrade migration
5. `blueprints/settings.py` — API endpoint
6. `frontend/src/pages/admin/SmartTradeRules.tsx` — UI toggle

## Testing

| Case | Expected |
|------|----------|
| Normal option (valid bid/ask) | No fallback |
| Illiquid option (ask=0) | Fallback to best strike |
| All strikes illiquid | Clear error |
| `liquidity_fallback=False` | Fail on ask=0 (existing behavior) |
