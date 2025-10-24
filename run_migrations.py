#!/usr/bin/env python
"""
Simple script to run Alembic migrations programmatically.
This works cross-platform including Windows where the alembic command may not be in PATH.
"""
import sys
from alembic.config import Config
from alembic import command

def main():
    """Run alembic upgrade head"""
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        print("✓ Database migrations completed successfully")
        return 0
    except Exception as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
