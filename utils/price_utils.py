"""
Price utilities for order placement.

This module provides centralized price validation and rounding functionality
to ensure order prices are valid multiples of exchange tick sizes.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from utils.logging import get_logger

logger = get_logger(__name__)


def round_price_to_tick_size(price: float, tick_size: Optional[float]) -> float:
    """
    Round price to the nearest valid tick size.

    Args:
        price: The price to round
        tick_size: The tick size for the instrument (from database)

    Returns:
        float: Price rounded to nearest tick size, or 2 decimal places if no tick size

    Example:
        >>> round_price_to_tick_size(102.0111, 0.05)  # Returns 102.0
        >>> round_price_to_tick_size(102.0111, 0.01)  # Returns 102.01
        >>> round_price_to_tick_size(102.0111, None)  # Returns 102.01 (2 decimal places)
    """
    if tick_size is None or tick_size <= 0:
        # No tick size available, just round to 2 decimal places
        return round(price, 2)

    # Round to nearest tick size using Decimal with ROUND_HALF_UP
    d_price = Decimal(str(price))
    d_tick = Decimal(str(tick_size))
    d_rounded = (d_price / d_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * d_tick

    # Ensure 2 decimal places for display
    return float(d_rounded.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def validate_and_round_price(
    price: float,
    tick_size: Optional[float],
    symbol: str,
    log_rounding: bool = True,
) -> Tuple[float, bool]:
    """
    Validate and round a price to tick size if applicable.

    Args:
        price: The price to validate and round
        tick_size: The tick size for the instrument (from database)
        symbol: The symbol for logging purposes
        log_rounding: Whether to log when rounding occurs

    Returns:
        Tuple containing:
        - The (potentially rounded) price
        - Boolean indicating if rounding was applied
    """
    if price <= 0 or tick_size is None or tick_size <= 0:
        return price, False

    rounded_price = round_price_to_tick_size(price, tick_size)

    if rounded_price != price:
        if log_rounding:
            logger.info(
                f"Price {price} rounded to {rounded_price} (tick_size={tick_size}) for {symbol}"
            )
        return rounded_price, True

    return price, False
