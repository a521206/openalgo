# utils/config.py

import functools
import os

from dotenv import load_dotenv

# Load environment variables from .env file with override=True to ensure values are updated
load_dotenv(override=True)


def get_broker_api_key():
    return os.getenv("BROKER_API_KEY")


def get_broker_api_secret():
    return os.getenv("BROKER_API_SECRET")


def get_login_rate_limit_min():
    return os.getenv("LOGIN_RATE_LIMIT_MIN", "5 per minute")


def get_login_rate_limit_hour():
    return os.getenv("LOGIN_RATE_LIMIT_HOUR", "25 per hour")


def get_host_server():
    return os.getenv("HOST_SERVER", "http://127.0.0.1:5000")


@functools.lru_cache(maxsize=None)
def get_execution_buffer_options():
    """Return the execution buffer for options as a validated float. Default: 5% (0.05)."""
    try:
        value = os.getenv("EXECUTION_BUFFER_OPTIONS", "0.05")
        buffer = float(value)
        if buffer < 0 or buffer > 0.50:
            return 0.05
        return buffer
    except (ValueError, TypeError):
        return 0.05


@functools.lru_cache(maxsize=None)
def get_execution_buffer_futures():
    """Return the execution buffer for futures as a validated float. Default: 0.1% (0.001)."""
    try:
        value = os.getenv("EXECUTION_BUFFER_FUTURES", "0.001")
        buffer = float(value)
        if buffer < 0 or buffer > 0.50:
            return 0.001
        return buffer
    except (ValueError, TypeError):
        return 0.001


def get_execution_buffer(instrument_type: str = None) -> float:
    """Return the execution buffer as a validated float.

    Args:
        instrument_type: Optional instrument type ("FUT", "CE", "PE"). If None, defaults to options buffer.

    Returns:
        Buffer value based on instrument type.
    """
    if instrument_type == "FUT":
        return get_execution_buffer_futures()
    return get_execution_buffer_options()
