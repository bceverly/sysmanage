#!/usr/bin/env python3
"""
Fix orphaned alembic revision references in the database.

This script directly updates the alembic_version table to fix orphaned revision
references that prevent 'alembic upgrade head' from running.

Usage:
    python3 scripts/fix_orphaned_revision.py
    ./scripts/fix_orphaned_revision.py
"""

import os
import sys
import yaml
import sqlalchemy as sa
from sqlalchemy import create_engine, text

# Add the project root to Python path so we can import sysmanage modules if needed
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)


def get_database_url():
    """Get database URL from sysmanage.yaml config file."""
    # Try multiple potential config locations (cross-platform)
    config_paths = [
        "/etc/sysmanage.yaml",  # Linux system config
        "C:\\ProgramData\\SysManage\\sysmanage.yaml",  # Windows system config
        os.path.join(project_root, "sysmanage.yaml"),  # Local dev
        os.path.join(project_root, "sysmanage-dev.yaml"),  # Local dev
    ]

    config_path = None
    for path in config_paths:
        if os.path.exists(path):
            config_path = path
            break

    if not config_path:
        print(f"Error: Config file not found. Tried: {', '.join(config_paths)}")
        sys.exit(1)

    print(f"Using config file: {config_path}")

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        db_config = config.get('database', {})

        # Build PostgreSQL URL
        host = db_config.get('host', 'localhost')
        port = db_config.get('port', 5432)
        database = db_config.get('name', 'sysmanage')  # 'name' not 'database' in config
        username = db_config.get('user', 'sysmanage')  # 'user' not 'username' in config
        password = db_config.get('password', '')

        return f"postgresql://{username}:{password}@{host}:{port}/{database}"

    except Exception as e:
        print(f"Error reading config file {config_path}: {e}")
        sys.exit(1)


def fix_orphaned_revision():
    """Fix orphaned revision references in the alembic_version table."""
    database_url = get_database_url()

    try:
        engine = create_engine(database_url)

        with engine.connect() as connection:
            # Check current revision
            result = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            current_version = result.scalar()

            print(f"Current alembic version in database: {current_version}")

            if current_version == '3cc63cc81f0c':
                print("Found orphaned revision reference. Fixing...")

                # Update to the last known good revision
                connection.execute(text("UPDATE alembic_version SET version_num = '904046eab30e'"))
                connection.commit()

                print("Successfully updated alembic_version table to revision 904046eab30e")
                print("You can now run 'alembic upgrade head' to apply pending migrations.")

            else:
                print("No orphaned revision found. Database appears to be in a valid state.")

    except Exception as e:
        print(f"Error fixing orphaned revision: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("SysManage Alembic Orphaned Revision Fixer")
    print("=" * 50)
    fix_orphaned_revision()