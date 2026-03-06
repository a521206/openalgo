"""
Database backup utility for OpenAlgo.

Creates timestamped backups of all OpenAlgo databases.

Usage:
    uv run python utils/backup_database.py
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path


def backup_databases():
    """Create backups of all OpenAlgo databases"""

    # Timestamp for backup files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Database files to backup
    databases = [
        "db/openalgo.db",
        "db/logs.db",
        "db/latency.db",
        "db/sandbox.db",
        "db/historify.duckdb",
    ]
    
    # Create backup directory if it doesn't exist
    backup_dir = Path("db/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"Database Backup - {timestamp}")
    print("=" * 70)
    print()

    backed_up = []
    skipped = []

    for db_path in databases:
        db_file = Path(db_path)

        if not db_file.exists():
            skipped.append(db_path)
            print(f"⊘ Skipped: {db_path} (not found)")
            continue

        # Create backup filename
        backup_filename = f"{db_file.stem}_{timestamp}{db_file.suffix}"
        backup_path = backup_dir / backup_filename

        try:
            # Copy database file
            shutil.copy2(db_file, backup_path)

            # Get file size
            backup_size = backup_path.stat().st_size

            backed_up.append((db_path, backup_path, backup_size))
            print(f"✓ Backed up: {db_path}")
            print(f"  → {backup_path} ({backup_size:,} bytes)")

        except Exception as e:
            print(f"✗ Failed: {db_path} - {str(e)}")
    
    print()
    print("=" * 70)
    print(f"Backup Summary:")
    print(f"  Successfully backed up: {len(backed_up)} database(s)")
    print(f"  Skipped: {len(skipped)} database(s)")
    print(f"  Backup location: {backup_dir.absolute()}")
    print("=" * 70)
    
    return len(backed_up) > 0


if __name__ == "__main__":
    success = backup_databases()
    
    if success:
        print("\n✓ Backup completed successfully!")
        sys.exit(0)
    else:
        print("\n✗ Backup failed or no databases found!")
        sys.exit(1)

