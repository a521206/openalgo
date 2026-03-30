# Smart Trade Rules & Maximum Position Lots - Test Plan

## Overview

This test plan covers comprehensive testing of the Smart Trade Rules functionality and maximum position lots feature in OpenAlgo. The Smart Trade Rules system validates orders against configured rules before placement, including position size limits, duplicate order prevention, and product type restrictions.

## Architecture Summary

### Core Components

1. **Smart Trade Rules Service** ([`services/smart_trade_rules_service.py`](services/smart_trade_rules_service.py))
   - [`analyze_position_change()`](services/smart_trade_rules_service.py:72) - Analyzes how an order would change the current position
   - [`get_lot_size()`](services/smart_trade_rules_service.py:148) / [`get_lot_size_with_status()`](services/smart_trade_rules_service.py:166) - Gets lot size for a symbol
   - [`validate_against_smart_trade_rules()`](services/smart_trade_rules_service.py:223) - Validates an order against smart trade rules

2. **Place Smart Order Service** ([`services/place_smart_order_service.py`](services/place_smart_order_service.py))
   - [`_fetch_position_for_validation()`](services/place_smart_order_service.py:89) - Fetches current position with retry logic
   - [`place_smart_order_with_auth()`](services/place_smart_order_service.py:187) - Places smart order with validation
   - [`place_smart_order()`](services/place_smart_order_service.py:429) - Main entry point for smart order placement

3. **Sandbox Service** ([`services/sandbox_service.py`](services/sandbox_service.py))
   - [`sandbox_place_smart_order()`](services/sandbox_service.py:447) - Places smart order in sandbox mode

4. **API Endpoint** ([`restx_api/place_smart_order.py`](restx_api/place_smart_order.py))
   - POST `/api/v1/placesmartorder` - API endpoint for placing smart orders

### Smart Trade Rules

| Rule | Description | Validation Logic |
|------|-------------|------------------|
| **Prevent Duplicate BUY** | Block BUY if long position exists | `action == "BUY" and current_position_qty > 0` |
| **Prevent Duplicate SELL** | Block SELL if short position exists | `action == "SELL" and current_position_qty < 0` |
| **Max Position Size** | Limit position size (lots for F&O, qty for equity) | Only checked when position is INCREASING/OPENING/REVERSING |
| **Max Order Value** | Limit order value in INR | `quantity * price > max_order_value` |
| **Allow Intraday Only** | Only allow MIS orders | `product_type not in ["MIS", "INTRADAY"]` |
| **Block CNC Orders** | Block CNC (delivery) orders | `product_type in ["CNC", "DELIVERY"]` |
| **Block NRML Orders** | Block NRML (carryforward) orders | `product_type in ["NRML", "CARRYFORWARD"]` |

### Position Change Types

| Type | Description | Limit Check |
|------|-------------|-------------|
| **OPENING** | New position from flat | ✅ Yes |
| **INCREASING** | Same direction, larger size | ✅ Yes |
| **REDUCING** | Position size decreasing | ❌ No (risk decreases) |
| **REVERSING** | Direction changing (long↔short) | ✅ Yes (new position) |

---

## Test Categories

### 1. Unit Tests - Smart Trade Rules Service

#### 1.1 Position Change Analysis Tests

**Test File**: [`test/test_smart_trade_rules_service.py`](test/test_smart_trade_rules_service.py)

##### 1.1.1 OPENING Position Tests

| Test Case | Input | Expected Output | Status |
|-----------|-------|-----------------|--------|
| Open long from flat | `current=0, action=BUY, qty=100` | `change_type=OPENING, new_qty=100, direction=LONG` | ✅ Existing |
| Open short from flat | `current=0, action=SELL, qty=100` | `change_type=OPENING, new_qty=-100, direction=SHORT` | ✅ Existing |
| Open with lowercase action | `current=0, action=buy, qty=50` | `change_type=OPENING, new_qty=50, direction=LONG` | ✅ Existing |

##### 1.1.2 INCREASING Position Tests

| Test Case | Input | Expected Output | Status |
|-----------|-------|-----------------|--------|
| Increase long | `current=50, action=BUY, qty=50` | `change_type=INCREASING, new_qty=100, direction=LONG` | ✅ Existing |
| Increase short | `current=-50, action=SELL, qty=50` | `change_type=INCREASING, new_qty=-100, direction=SHORT` | ✅ Existing |

##### 1.1.3 REDUCING Position Tests

| Test Case | Input | Expected Output | Status |
|-----------|-------|-----------------|--------|
| Reduce long | `current=100, action=SELL, qty=50` | `change_type=REDUCING, new_qty=50, direction=LONG` | ✅ Existing |
| Reduce short | `current=-100, action=BUY, qty=50` | `change_type=REDUCING, new_qty=-50, direction=SHORT` | ✅ Existing |
| Close long completely | `current=100, action=SELL, qty=100` | `change_type=REDUCING, new_qty=0, direction=FLAT` | ✅ Existing |
| Close short completely | `current=-100, action=BUY, qty=100` | `change_type=REDUCING, new_qty=0, direction=FLAT` | ✅ Existing |

##### 1.1.4 REVERSING Position Tests

| Test Case | Input | Expected Output | Status |
|-----------|-------|-----------------|--------|
| Reverse long to short | `current=50, action=SELL, qty=150` | `change_type=REVERSING, new_qty=-100, direction=SHORT` | ✅ Existing |
| Reverse short to long | `current=-50, action=BUY, qty=150` | `change_type=REVERSING, new_qty=100, direction=LONG` | ✅ Existing |
| Reverse long to smaller short | `current=100, action=SELL, qty=150` | `change_type=REVERSING, new_qty=-50, direction=SHORT` | ✅ Existing |

##### 1.1.5 Edge Cases

| Test Case | Input | Expected Output | Status |
|-----------|-------|-----------------|--------|
| Zero quantity buy | `current=100, action=BUY, qty=0` | `change_type=REDUCING, new_qty=100` | ✅ Existing |
| Zero quantity sell | `current=100, action=SELL, qty=0` | `change_type=REDUCING, new_qty=100` | ✅ Existing |

#### 1.2 Position Size Validation Tests

##### 1.2.1 REDUCING Position (Should Skip Limit Check)

| Test Case | Current Position | Order | Limit | Expected | Status |
|-----------|------------------|-------|-------|----------|--------|
| Reduce long skips limit | 100 | SELL 50 | 50 | ✅ Pass | ✅ Existing |
| Reduce short skips limit | -100 | BUY 50 | 50 | ✅ Pass | ✅ Existing |
| Close long position allowed | 100 | SELL 100 | 50 | ✅ Pass | ✅ Existing |

##### 1.2.2 OPENING Position (Should Check Limit)

| Test Case | Current Position | Order | Limit | Expected | Status |
|-----------|------------------|-------|-------|----------|--------|
| Open long within limit | 0 | BUY 50 | 100 | ✅ Pass | ✅ Existing |
| Open long exceeds limit | 0 | BUY 100 | 50 | ❌ Fail | ✅ Existing |
| Open short within limit | 0 | SELL 50 | 100 | ✅ Pass | ✅ Existing |
| Open short exceeds limit | 0 | SELL 100 | 50 | ❌ Fail | ✅ Existing |

##### 1.2.3 INCREASING Position (Should Check Limit)

| Test Case | Current Position | Order | Limit | Expected | Status |
|-----------|------------------|-------|-------|----------|--------|
| Increase long within limit | 50 | BUY 50 | 100 | ✅ Pass | ✅ Existing |
| Increase long exceeds limit | 75 | BUY 50 | 100 | ❌ Fail | ✅ Existing |
| Increase short within limit | -50 | SELL 50 | 100 | ✅ Pass | ✅ Existing |
| Increase short exceeds limit | -75 | SELL 50 | 100 | ❌ Fail | ✅ Existing |

##### 1.2.4 REVERSING Position (Should Check New Position Limit)

| Test Case | Current Position | Order | Limit | Expected | Status |
|-----------|------------------|-------|-------|----------|--------|
| Reverse long to short within limit | 50 | SELL 100 | 100 | ✅ Pass | ✅ Existing |
| Reverse long to short exceeds limit | 50 | SELL 150 | 50 | ❌ Fail | ✅ Existing |
| Reverse short to long within limit | -50 | BUY 100 | 100 | ✅ Pass | ✅ Existing |
| Reverse short to long exceeds limit | -50 | BUY 150 | 50 | ❌ Fail | ✅ Existing |

#### 1.3 F&O Position Size Validation with Lot Sizes

| Test Case | Current Position | Order | Lot Size | Limit (lots) | Expected | Status |
|-----------|------------------|-------|----------|--------------|----------|--------|
| F&O reduce skips limit | 150 (3 lots) | SELL 50 | 50 | 2 | ✅ Pass | ✅ Existing |
| F&O increase within limit | 100 (2 lots) | BUY 100 | 50 | 5 | ✅ Pass | ✅ Existing |
| F&O increase exceeds limit | 100 (2 lots) | BUY 100 | 50 | 3 | ❌ Fail | ✅ Existing |

#### 1.4 Lot Size Fetch Tests

| Test Case | Exchange | Expected Lot Size | Status |
|-----------|----------|-------------------|--------|
| Equity (NSE) | NSE | 1 | 🆕 New |
| Equity (BSE) | BSE | 1 | 🆕 New |
| F&O (NFO) | NFO | From master contract | 🆕 New |
| F&O (BFO) | BFO | From master contract | 🆕 New |
| Commodity (MCX) | MCX | From master contract | 🆕 New |
| Currency (CDS) | CDS | From master contract | 🆕 New |
| Unknown exchange | UNKNOWN | 1 (default) | 🆕 New |

#### 1.5 Integration Scenarios

| Test Case | Description | Expected | Status |
|-----------|-------------|----------|--------|
| Reduce large position in steps | Reduce 500 to 100 in steps | ✅ All pass | ✅ Existing |
| Build position up to limit | Build from 0 to 100 in steps | ✅ All pass | ✅ Existing |
| Reverse position | Reverse from 50 long to 50 short | ✅ Pass | ✅ Existing |
| Reverse exceeds limit | Reverse from 50 long to 100 short (limit 50) | ❌ Fail | ✅ Existing |

---

### 2. Integration Tests - Place Smart Order Service

**Test File**: `test/test_place_smart_order_service.py` (🆕 New)

#### 2.1 Position Fetch Tests

| Test Case | Description | Expected | Priority |
|-----------|-------------|----------|----------|
| Position fetch success | Fetch position successfully | Returns quantity | High |
| Position fetch retry | Retry on failure | Returns after retry | High |
| Position fetch max retries | Fail after max retries | Returns FAILED status | High |
| Position fetch not supported | Broker doesn't support | Returns NOT_SUPPORTED | Medium |

#### 2.2 Smart Trade Rules Integration

| Test Case | Description | Expected | Priority |
|-----------|-------------|----------|----------|
| Rules disabled | Smart trade disabled | Order passes | High |
| Rules enabled - pass | Order passes all rules | Order proceeds | High |
| Rules enabled - fail | Order fails a rule | Order blocked | High |
| Position fetch failed + rules enabled | Position fetch fails | Order blocked | High |

#### 2.3 Order Validation Tests

| Test Case | Description | Expected | Priority |
|-----------|-------------|----------|----------|
| Missing required fields | Missing symbol | Validation fails | High |
| Invalid exchange | Invalid exchange code | Validation fails | High |
| Invalid action | Invalid action | Validation fails | High |
| Invalid price type | Invalid price type | Validation fails | High |
| Invalid product type | Invalid product type | Validation fails | High |

#### 2.4 Price Discovery Tests

| Test Case | Description | Expected | Priority |
|-----------|-------------|----------|----------|
| LIMIT with price=0 | Trigger price discovery | Price discovered | Medium |
| LIMIT with price>0 | No price discovery | Price used as-is | Medium |
| Price discovery fails | Quote fetch fails | Order proceeds with warning | Medium |

---

### 3. API Tests - Place Smart Order Endpoint

**Test File**: `test/test_place_smart_order_api.py` (🆕 New)

#### 3.1 API Authentication

| Test Case | Description | Expected | Priority |
|-----------|-------------|----------|----------|
| Valid API key | Valid API key | Order processed | High |
| Invalid API key | Invalid API key | 403 Forbidden | High |
| Missing API key | No API key | 400 Bad Request | High |

#### 3.2 API Request Validation

| Test Case | Description | Expected | Priority |
|-----------|-------------|----------|----------|
| Valid request | All fields valid | 200 OK | High |
| Missing required field | Missing symbol | 400 Bad Request | High |
| Invalid field value | Invalid exchange | 400 Bad Request | High |

#### 3.3 API Response Format

| Test Case | Description | Expected | Priority |
|-----------|-------------|----------|----------|
| Success response | Order placed | Correct response format | High |
| Error response | Order blocked | Correct error format | High |
| Analyzer mode response | Analyzer mode | Correct mode in response | Medium |

---

### 4. Edge Cases & Error Handling

#### 6.1 Boundary Conditions

| Test Case | Description | Expected | Priority |
|-----------|-------------|----------|----------|
| Position at exact limit | Position = limit | ✅ Pass | High |
| Position just over limit | Position = limit + 1 | ❌ Fail | High |
| Zero quantity order | Quantity = 0 | ✅ Pass (no change) | Medium |
| Negative quantity | Quantity < 0 | ❌ Fail (validation) | Medium |
| Very large quantity | Quantity = MAX_INT | ❌ Fail (overflow check) | Low |

#### 6.2 Error Scenarios

| Test Case | Description | Expected | Priority |
|-----------|-------------|----------|----------|
| Database connection failure | DB unavailable | Graceful error | High |
| Symbol not found | Invalid symbol | Graceful error | High |
| Lot size fetch failure | Master contract missing | Fail-safe block | High |
| Position fetch timeout | Timeout | Retry then fail | Medium |
| Concurrent order placement | Race condition | Handled correctly | Low |

---



---

## Test Data Requirements

### Symbols

| Symbol | Exchange | Type | Lot Size |
|--------|----------|------|----------|
| RELIANCE | NSE | Equity | 1 |
| TCS | NSE | Equity | 1 |
| NIFTY24FEB18000CE | NFO | Option | 50 |
| NIFTY24FEB18000PE | NFO | Option | 50 |
| BANKNIFTY24FEB45000CE | NFO | Option | 15 |
| CRUDEOIL24FEB6000CE | MCX | Commodity | 100 |
| USDINR24FEB8200CE | CDS | Currency | 1000 |

### Position Scenarios

| Scenario | Current Position | Order | Expected Result |
|----------|------------------|-------|-----------------|
| Flat to Long | 0 | BUY 100 | OPENING, LONG |
| Flat to Short | 0 | SELL 100 | OPENING, SHORT |
| Long to Larger Long | 50 | BUY 50 | INCREASING, LONG |
| Short to Larger Short | -50 | SELL 50 | INCREASING, SHORT |
| Long to Smaller Long | 100 | SELL 50 | REDUCING, LONG |
| Short to Smaller Short | -100 | BUY 50 | REDUCING, SHORT |
| Long to Flat | 100 | SELL 100 | REDUCING, FLAT |
| Short to Flat | -100 | BUY 100 | REDUCING, FLAT |
| Long to Short | 50 | SELL 150 | REVERSING, SHORT |
| Short to Long | -50 | BUY 150 | REVERSING, LONG |

### Smart Trade Rules Configurations

| Configuration | Value | Description |
|---------------|-------|-------------|
| Disabled | `smart_trade_enabled=False` | All orders pass |
| Duplicate prevention | `prevent_duplicate_buy=True, prevent_duplicate_sell=True` | Block duplicates |
| Position limit (equity) | `max_position_size=100` | Max 100 shares |
| Position limit (F&O) | `max_position_size=5` | Max 5 lots |
| Order value limit | `max_order_value=100000` | Max ₹1,00,000 |
| Intraday only | `allow_intraday_only=True` | Only MIS orders |
| Block CNC | `block_cnc_orders=True` | Block CNC orders |
| Block NRML | `block_nrml_orders=True` | Block NRML orders |

---

## Test Execution Strategy

### Phase 1: Unit Tests (Week 1)

1. **Day 1-2**: Position change analysis tests
   - Run existing tests in [`test/test_smart_trade_rules_service.py`](test/test_smart_trade_rules_service.py)
   - Add missing edge cases
   - Verify all position change types

2. **Day 3-4**: Position size validation tests
   - Run existing validation tests
   - Add F&O lot size tests
   - Add boundary condition tests

3. **Day 5**: Lot size fetch tests
   - Add tests for different exchanges
   - Add error handling tests
   - Add unknown exchange tests

### Phase 2: Integration Tests (Week 2)

1. **Day 1-2**: Place smart order service tests
   - Create [`test/test_place_smart_order_service.py`](test/test_place_smart_order_service.py)
   - Test position fetch logic
   - Test smart trade rules integration

2. **Day 3-4**: API tests
   - Create [`test/test_place_smart_order_api.py`](test/test_place_smart_order_api.py)
   - Test API authentication
   - Test request validation
   - Test response format

3. **Day 5**: Edge cases & error handling
   - Add boundary condition tests
   - Add error scenario tests
   - Add concurrent access tests

---

## Test Tools & Frameworks

### Required Tools

| Tool | Version | Purpose |
|------|---------|---------|
| pytest | >= 7.0 | Test framework |
| pytest-cov | >= 4.0 | Coverage reporting |
| pytest-mock | >= 3.0 | Mocking |
| pytest-asyncio | >= 0.21 | Async test support |
| fakeredis | >= 2.0 | Redis mocking (if needed) |

### Test Commands

```bash
# Run all smart trade rules tests
pytest test/test_smart_trade_rules_service.py -v

# Run with coverage
pytest test/test_smart_trade_rules_service.py --cov=services.smart_trade_rules_service --cov-report=html

# Run specific test class
pytest test/test_smart_trade_rules_service.py::TestPositionSizeValidationWithShortPositions -v

# Run specific test
pytest test/test_smart_trade_rules_service.py::TestPositionSizeValidationWithShortPositions::test_reduce_long_skips_limit_check -v
```

---

## Success Criteria

### Unit Tests

- [ ] All existing tests pass
- [ ] Code coverage > 90% for [`smart_trade_rules_service.py`](services/smart_trade_rules_service.py)
- [ ] All position change types tested
- [ ] All validation rules tested
- [ ] All edge cases covered

### Integration Tests

- [ ] Place smart order service tests pass
- [ ] Error handling tests pass

### API Tests

- [ ] API authentication tests pass
- [ ] API validation tests pass
- [ ] API response format tests pass
- [ ] API error handling tests pass



---

## Risk Assessment

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Position fetch failure | Orders blocked incorrectly | Fail-safe design, retry logic |
| Lot size fetch failure | F&O orders blocked | Fail-safe design, default to 1 |
| Race condition | Concurrent order issues | Database transactions, locking |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cache staleness | Outdated rules | TTL-based cache, manual invalidation |
| Database connection failure | Service unavailable | Connection pooling, retry logic |
| Invalid symbol | Order rejected | Symbol validation, error handling |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Performance degradation | Slow validation | Caching, optimization |
| Memory leak | Service crash | Resource cleanup, monitoring |

---

## Test Environment

### Local Development

```bash
# Start the application
python app.py

# Run tests
pytest test/test_smart_trade_rules_service.py -v
```

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest test/test_smart_trade_rules_service.py -v --cov=services.smart_trade_rules_service
```

---

## Appendix

### A. Existing Test Coverage

**File**: [`test/test_smart_trade_rules_service.py`](test/test_smart_trade_rules_service.py)

**Test Classes**:
1. `TestPositionChangeTypeEnum` - 1 test
2. `TestPositionChangeDataclass` - 1 test
3. `TestAnalyzePositionChange` - 15 tests
4. `TestPositionSizeValidationWithShortPositions` - 12 tests
5. `TestPositionSizeValidationForFO` - 3 tests
6. `TestIntegrationScenarios` - 4 tests

**Total**: 36 tests

### B. Missing Test Coverage

1. **Lot size fetch tests** - Different exchanges, error handling
2. **Place smart order service tests** - Integration with smart trade rules
3. **API endpoint tests** - Authentication, validation, response format
4. **Edge cases** - Boundary conditions, error scenarios

### C. Related Documentation

- [Smart Trade Rules Service](services/smart_trade_rules_service.py)
- [Place Smart Order Service](services/place_smart_order_service.py)
- [Sandbox Service](services/sandbox_service.py)
- [Place Smart Order API](restx_api/place_smart_order.py)
- [Settings Database](database/settings_db.py)
- [Migration Script](migrations/add_smart_trade_rules_columns.py)


---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-29 | Kilo Code | Initial test plan |
| 1.1 | 2026-03-29 | Kilo Code | Added Zerodha API mocking tests section |
| 1.2 | 2026-03-29 | Kilo Code | Simplified test plan - removed Zerodha integration and performance tests |
| 1.3 | 2026-03-29 | Kilo Code | Removed Database Tests and Sandbox Mode Tests |
