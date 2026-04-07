# utils/config.py

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


EXECUTION_BUFFER_CACHE = None


def get_execution_buffer():
    global EXECUTION_BUFFER_CACHE
    if EXECUTION_BUFFER_CACHE is not None:
        return EXECUTION_BUFFER_CACHE

    try:
        value = os.getenv("EXECUTION_BUFFER", "0.05")
        buffer = float(value)
        if buffer < 0 or buffer > 0.50:
            return 0.05
        EXECUTION_BUFFER_CACHE = buffer
        return buffer
    except (ValueError, TypeError):
        return 0.05
