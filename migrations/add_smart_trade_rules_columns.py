"""
Migration script to add Smart Trade Rules columns to the Settings table.

This script adds the following columns to the settings table:
- smart_trade_enabled (Boolean)
- prevent_duplicate_buy (Boolean)
- prevent_duplicate_sell (Boolean)
- max_position_size (Integer, nullable)
- max_order_value (Integer, nullable)
- allow_intraday_only (Boolean)
- block_cnc_orders (Boolean)
- block_nrml_orders (Boolean)

Usage:
    uv run python migrations/add_smart_trade_rules_columns.py
"""

import sqlite3
import sys
from pathlib import Path

# Database path
DB_PATH = "db/openalgo.db"


def column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def add_smart_trade_columns():
    """Add smart trade rules columns to the settings table"""
    conn = None
    try:
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        print("Starting migration: Adding Smart Trade Rules columns to settings table")
        print()

        # Define columns to add
        columns_to_add = [
            ("smart_trade_enabled", "INTEGER DEFAULT 1"),
            ("prevent_duplicate_buy", "INTEGER DEFAULT 1"),
            ("prevent_duplicate_sell", "INTEGER DEFAULT 1"),
            ("max_position_size", "INTEGER"),
            ("max_order_value", "INTEGER"),
            ("allow_intraday_only", "INTEGER DEFAULT 0"),
            ("block_cnc_orders", "INTEGER DEFAULT 0"),
            ("block_nrml_orders", "INTEGER DEFAULT 0"),
        ]

        # Add each column if it doesn't exist
        for column_name, column_type in columns_to_add:
            if not column_exists(cursor, "settings", column_name):
                print(f"Adding column: {column_name}")
                cursor.execute(f"ALTER TABLE settings ADD COLUMN {column_name} {column_type}")
                print(f"✓ Column {column_name} added successfully")
            else:
                print(f"⊘ Column {column_name} already exists, skipping")

        # Commit changes
        conn.commit()
        print()
        print("Migration completed successfully!")

        # Verify columns were added
        cursor.execute("PRAGMA table_info(settings)")
        all_columns = [row[1] for row in cursor.fetchall()]
        print(f"Settings table now has {len(all_columns)} columns")

        # Close connection
        conn.close()

        return True

    except Exception as e:
        print(f"Migration failed: {str(e)}")
        if conn:
            conn.rollback()
            conn.close()
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("Smart Trade Rules Migration Script")
    print("=" * 70)
    print()

    success = add_smart_trade_columns()

    print()
    if success:
        print("✓ Migration completed successfully!")
        print("You can now restart the application.")
    else:
        print("✗ Migration failed. Please check the logs for details.")
        sys.exit(1)

