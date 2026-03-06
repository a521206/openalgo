"""
Smart Trade Rules Enforcement Service

This service validates orders against configured smart trade rules including:
- Prevent duplicate BUY/SELL orders
- Maximum position size limits (lots for F&O, quantity for equity)
- Maximum order value limits
- Product type restrictions (MIS/CNC/NRML)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from database.settings_db import get_smart_trade_rules
from database.token_db_enhanced import get_symbol_info
from utils.logging import get_logger

logger = get_logger(__name__)


class PositionFetchStatus(Enum):
    """Status of position fetch operation."""
    SUCCESS = "success"
    FAILED = "failed"
    NOT_SUPPORTED = "not_supported"


@dataclass
class PositionFetchResult:
    """Result of position fetch operation."""
    quantity: int
    status: PositionFetchStatus
    error_message: str | None = None


class LotSizeFetchStatus(Enum):
    """Status of lot size fetch operation."""
    SUCCESS = "success"
    FAILED = "failed"
    NOT_FOUND = "not_found"
    EQUITY_DEFAULT = "equity_default"  # Equity exchanges always have lot size 1


@dataclass
class LotSizeResult:
    """Result of lot size fetch operation."""
    lot_size: int
    status: LotSizeFetchStatus
    exchange: str
    error_message: str | None = None


class PositionChangeType(Enum):
    """Type of position change."""
    REDUCING = "reducing"        # Position size decreasing (risk reduces)
    INCREASING = "increasing"    # Position size increasing, same direction
    REVERSING = "reversing"      # Position direction changing (long to short or vice versa)
    OPENING = "opening"          # New position being opened from flat


@dataclass
class PositionChange:
    """Details about a position change."""
    change_type: PositionChangeType
    current_qty: int
    new_qty: int
    increment: int  # The change in absolute position size
    direction: str  # LONG, SHORT, or FLAT for the new position


def analyze_position_change(
    current_position_qty: int,
    action: str,
    quantity: int
) -> PositionChange:
    """
    Analyze how an order would change the current position.
    
    This function determines whether an order is:
    - REDUCING: Decreasing position size (should skip limit checks)
    - INCREASING: Increasing position size in same direction (should check limits)
    - REVERSING: Changing position direction (should check new position limits)
    - OPENING: Creating a new position from flat (should check limits)
    
    Args:
        current_position_qty: Current position quantity (positive=long, negative=short, 0=flat)
        action: Order action - BUY or SELL
        quantity: Order quantity (must be positive)
    
    Returns:
        PositionChange with change type and details
    """
    # Normalize action to uppercase
    action = action.upper() if isinstance(action, str) else "BUY"
    
    # Calculate new position
    if action == "BUY":
        new_position_qty = current_position_qty + quantity
    else:  # SELL
        new_position_qty = current_position_qty - quantity
    
    current_abs = abs(current_position_qty)
    new_abs = abs(new_position_qty)
    
    # Determine change type
    if current_position_qty == 0:
        # Starting from flat - opening a new position
        change_type = PositionChangeType.OPENING
    elif new_position_qty == 0:
        # Closing the position completely
        change_type = PositionChangeType.REDUCING
    elif current_position_qty * new_position_qty < 0:
        # Signs differ - position reversal (long to short or short to long)
        change_type = PositionChangeType.REVERSING
    elif new_abs > current_abs:
        # Same direction, larger size - increasing
        change_type = PositionChangeType.INCREASING
    else:
        # Same direction, smaller size - reducing
        change_type = PositionChangeType.REDUCING
    
    # Determine direction of new position
    if new_position_qty > 0:
        direction = "LONG"
    elif new_position_qty < 0:
        direction = "SHORT"
    else:
        direction = "FLAT"
    
    # Calculate increment (increase in absolute position)
    # For reversals, the increment is the new position size
    # For increases, the increment is the difference
    if change_type == PositionChangeType.REVERSING:
        increment = new_abs
    else:
        increment = max(0, new_abs - current_abs)
    
    return PositionChange(
        change_type=change_type,
        current_qty=current_position_qty,
        new_qty=new_position_qty,
        increment=increment,
        direction=direction
    )


def get_lot_size(symbol: str, exchange: str) -> int:
    """
    Get lot size for a symbol. Returns 1 for equity, actual lot size for F&O.
    
    This function is kept for backward compatibility.
    For new code, use get_lot_size_with_status() instead.
    
    Args:
        symbol: Trading symbol
        exchange: Exchange code (NSE, NFO, BFO, etc.)
    
    Returns:
        Lot size (1 for equity, actual lot size for F&O)
    """
    result = get_lot_size_with_status(symbol, exchange)
    return result.lot_size


def get_lot_size_with_status(symbol: str, exchange: str) -> LotSizeResult:
    """
    Get lot size for a symbol with status information.
    
    Args:
        symbol: Trading symbol
        exchange: Exchange code (NSE, NFO, BFO, etc.)
    
    Returns:
        LotSizeResult containing lot size, status, and optional error message
    """
    # For equity exchanges, lot size is always 1
    if exchange in ["NSE", "BSE"]:
        return LotSizeResult(
            lot_size=1,
            status=LotSizeFetchStatus.EQUITY_DEFAULT,
            exchange=exchange
        )
    
    # For F&O exchanges, get lot size from master contract
    if exchange in ["NFO", "BFO", "MCX", "CDS"]:
        try:
            symbol_info = get_symbol_info(symbol, exchange)
            if symbol_info and symbol_info.lotsize:
                return LotSizeResult(
                    lot_size=symbol_info.lotsize,
                    status=LotSizeFetchStatus.SUCCESS,
                    exchange=exchange
                )
            else:
                # Lot size not found in master contract
                logger.warning(f"Lot size not found for {symbol} on {exchange}")
                return LotSizeResult(
                    lot_size=1,
                    status=LotSizeFetchStatus.NOT_FOUND,
                    exchange=exchange,
                    error_message=f"Lot size not found in master contract for {symbol} on {exchange}"
                )
        except Exception as e:
            logger.error(f"Error fetching lot size for {symbol} on {exchange}: {e}")
            return LotSizeResult(
                lot_size=1,
                status=LotSizeFetchStatus.FAILED,
                exchange=exchange,
                error_message=str(e)
            )
    
    # Unknown exchange - default to 1 with NOT_FOUND status
    logger.warning(f"Unknown exchange '{exchange}' for {symbol}, defaulting lot size to 1")
    return LotSizeResult(
        lot_size=1,
        status=LotSizeFetchStatus.NOT_FOUND,
        exchange=exchange,
        error_message=f"Unknown exchange: {exchange}"
    )


def validate_against_smart_trade_rules(
    order_data: dict[str, Any],
    position_result: PositionFetchResult,
    broker: str | None = None,
) -> tuple[bool, str | None]:
    """
    Validate an order against smart trade rules.
    
    Args:
        order_data: Order data containing symbol, exchange, action, quantity, product_type, price
        position_result: Position fetch result with quantity, status, and error message
        broker: Broker name (for future use)
    
    Returns:
        Tuple containing:
        - Success status (bool): True if validation passed, False if order should be blocked
        - Error message (str | None): Error message if validation failed, None if passed
    """
    # Get smart trade rules configuration
    rules = get_smart_trade_rules()
    
    # If smart trade rules are disabled, allow all orders
    if not rules.get("smart_trade_enabled", False):
        return True, None
    
    # FAIL-SAFE: If position fetch failed and position-based rules are enabled, block the order
    position_based_rules_enabled = (
        rules.get("prevent_duplicate_buy", False) or
        rules.get("prevent_duplicate_sell", False) or
        rules.get("max_position_size") is not None
    )
    
    if position_result.status == PositionFetchStatus.FAILED and position_based_rules_enabled:
        return False, f"Smart Trade Rule: Cannot validate order - position fetch failed: {position_result.error_message}"
    
    # Use the position quantity (will be 0 for NOT_SUPPORTED or FAILED with no position rules)
    current_position_qty = position_result.quantity
    
    symbol = order_data.get("symbol", "")
    exchange = order_data.get("exchange", "")
    action = order_data.get("action", "").upper()
    quantity = int(order_data.get("quantity", 0))
    product_type = order_data.get("product_type", "MIS").upper()
    price = float(order_data.get("price", 0))
    
    # Rule 1: Prevent Duplicate BUY
    if rules.get("prevent_duplicate_buy", False):
        if action == "BUY" and current_position_qty > 0:
            return False, f"Smart Trade Rule: Duplicate BUY blocked. You already have a long position of {current_position_qty} in {symbol}"
    
    # Rule 2: Prevent Duplicate SELL (adding to existing short position)
    if rules.get("prevent_duplicate_sell", False):
        if action == "SELL" and current_position_qty < 0:
            return False, f"Smart Trade Rule: Duplicate SELL blocked. Already have a short position of {abs(current_position_qty)} in {symbol}"
    
    # Rule 3: Maximum Position Size (in lots for F&O, quantity for equity)
    # IMPORTANT: Position limits only apply when position is INCREASING, not when reducing
    max_position_size = rules.get("max_position_size")
    if max_position_size is not None and max_position_size > 0:
        lot_size_result = get_lot_size_with_status(symbol, exchange)
        
        # FAIL-SAFE: For F&O instruments, if lot size fetch failed, block the order
        # This prevents incorrect position size calculations
        if lot_size_result.status in [LotSizeFetchStatus.FAILED, LotSizeFetchStatus.NOT_FOUND]:
            # Only block if this is an F&O exchange (where lot size matters)
            if exchange in ["NFO", "BFO", "MCX", "CDS"]:
                return False, (
                    f"Smart Trade Rule: Cannot validate position size - "
                    f"lot size fetch failed for {symbol} on {exchange}: {lot_size_result.error_message}"
                )
        
        lot_size = lot_size_result.lot_size
        
        # Analyze the position change to determine if limit check is needed
        position_change = analyze_position_change(current_position_qty, action, quantity)
        
        # Only check limits when position is increasing, opening, or reversing
        # REDUCING positions should NOT be checked (risk is decreasing)
        if position_change.change_type in [PositionChangeType.INCREASING, PositionChangeType.OPENING, PositionChangeType.REVERSING]:
            
            # For all these cases, check the NEW total position against the limit
            # This is the most conservative and correct approach:
            # - OPENING: new position is the order quantity
            # - INCREASING: new position is current + order quantity
            # - REVERSING: new position is the opposite direction position
            check_qty = abs(position_change.new_qty)
            
            # Convert to lots for F&O
            if lot_size > 1:
                # F&O: Check in lots
                check_lots = check_qty / lot_size
                if check_lots > max_position_size:
                    return False, (
                        f"Smart Trade Rule: Maximum position size exceeded. "
                        f"Limit: {max_position_size} lots ({max_position_size * lot_size} qty), "
                        f"New {position_change.direction} position would be: {check_lots:.2f} lots ({check_qty} qty)"
                    )
            else:
                # Equity: Check in quantity
                if check_qty > max_position_size:
                    return False, (
                        f"Smart Trade Rule: Maximum position size exceeded. "
                        f"Limit: {max_position_size} qty, "
                        f"New {position_change.direction} position would be: {check_qty} qty"
                    )
    
    # Rule 4: Maximum Order Value
    max_order_value = rules.get("max_order_value")
    if max_order_value is not None and max_order_value > 0:
        # Calculate order value
        order_value = quantity * price
        if order_value > max_order_value:
            return False, f"Smart Trade Rule: Maximum order value exceeded. Limit: ₹{max_order_value:,.2f}, Order value: ₹{order_value:,.2f}"
    
    # Rule 5: Allow Intraday Only (MIS)
    if rules.get("allow_intraday_only", False):
        if product_type not in ["MIS", "INTRADAY"]:
            return False, f"Smart Trade Rule: Only intraday (MIS) orders allowed. Product type '{product_type}' is blocked"
    
    # Rule 6: Block CNC Orders
    if rules.get("block_cnc_orders", False):
        if product_type in ["CNC", "DELIVERY"]:
            return False, "Smart Trade Rule: CNC (delivery) orders are blocked"
    
    # Rule 7: Block NRML Orders
    if rules.get("block_nrml_orders", False):
        if product_type in ["NRML", "CARRYFORWARD"]:
            return False, "Smart Trade Rule: NRML (carryforward) orders are blocked"
    
    # All validations passed
    return True, None
