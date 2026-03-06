"""
Migration script to add download tracking columns to master_contract_status table.

This script adds the following columns to the master_contract_status table:
- last_download_time (DATETIME)
- download_date (DATE)
- exchange_stats (TEXT)
- download_duration_seconds (INTEGER)

Usage:
    uv run python migrations/add_master_contract_download_time.py
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


def add_download_tracking_columns():
    """Add download tracking columns to master_contract_status table"""
    conn = None
    try:
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        print("Starting migration: Adding download tracking columns to master_contract_status table")
        print()

        # Add last_download_time column if it doesn't exist
        if not column_exists(cursor, "master_contract_status", "last_download_time"):
            print("Adding column: last_download_time")
            cursor.execute("ALTER TABLE master_contract_status ADD COLUMN last_download_time DATETIME")
            print("✓ Column last_download_time added successfully")
        else:
            print("⊘ Column last_download_time already exists, skipping")

        # Add download_date column if it doesn't exist
        if not column_exists(cursor, "master_contract_status", "download_date"):
            print("Adding column: download_date")
            cursor.execute("ALTER TABLE master_contract_status ADD COLUMN download_date DATE")
            print("✓ Column download_date added successfully")
        else:
            print("⊘ Column download_date already exists, skipping")

        # Add exchange_stats column if it doesn't exist
        if not column_exists(cursor, "master_contract_status", "exchange_stats"):
            print("Adding column: exchange_stats")
            cursor.execute("ALTER TABLE master_contract_status ADD COLUMN exchange_stats TEXT")
            print("✓ Column exchange_stats added successfully")
        else:
            print("⊘ Column exchange_stats already exists, skipping")

        # Add download_duration_seconds column if it doesn't exist
        if not column_exists(cursor, "master_contract_status", "download_duration_seconds"):
            print("Adding column: download_duration_seconds")
            cursor.execute("ALTER TABLE master_contract_status ADD COLUMN download_duration_seconds INTEGER")
            print("✓ Column download_duration_seconds added successfully")
        else:
            print("⊘ Column download_duration_seconds already exists, skipping")

        # Commit changes
        conn.commit()
        print()
        print("Migration completed successfully!")

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
    print("Master Contract Download Tracking Columns Migration Script")
    print("=" * 70)
    print()

    success = add_download_tracking_columns()

    print()
    if success:
        print("✓ Migration completed successfully!")
        print("You can now restart the application.")
    else:
        print("✗ Migration failed. Please check the logs for details.")
        sys.exit(1)
