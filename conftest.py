"""
Root-level conftest for unit tests.

Sets up sys.modules mocks for heavy/missing dependencies so that
services like LiquidityFallbackService can be imported without
requiring a live database or full Flask app context.
"""

import sys
from unittest.mock import MagicMock


def _install_mocks():
    # Third-party packages
    for name in [
        "argon2", "argon2.classifiers",
        "cryptography", "cryptography.fernet",
    ]:
        sys.modules.setdefault(name, MagicMock())

    # Database submodules (real package exists, but we mock sub-DB access)
    import database

    for submod in [
        "settings_db", "auth_db", "apilog_db", "analyzer_db",
        "qty_freeze_db", "symtoken_db", "chart_prefs_db", "chartink_db",
        "action_center_db", "cache_invalidation", "cache_restoration",
        "token_db_enhanced",
    ]:
        full = f"database.{submod}"
        if full not in sys.modules:
            mock = MagicMock()
            sys.modules[full] = mock
            setattr(database, submod, mock)

    # Heavy service modules that trigger their own deep import chains
    for mod_name in [
        "services.option_symbol_service",
        "services.quotes_service",
        "services.place_order_service",
        "services.telegram_alert_service",
        "services.order_router_service",
    ]:
        sys.modules.setdefault(mod_name, MagicMock())


_install_mocks()


def pytest_configure(config):
    _install_mocks()
