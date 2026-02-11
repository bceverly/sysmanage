#!/usr/bin/env python3
"""
E2E Test User Management Script

Creates and removes a test user for Playwright E2E tests.
Usage:
    python scripts/e2e_test_user.py create
    python scripts/e2e_test_user.py delete
"""

import sys
import uuid
from datetime import datetime, timezone

from argon2 import PasswordHasher
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Test user credentials - must match auth.setup.ts defaults
TEST_USER_EMAIL = "e2e-test@sysmanage.org"
TEST_USER_PASSWORD = "E2ETestPassword123!"
TEST_USER_ID = "e2e-test-user-id-00000000"  # Fixed ID for easy cleanup


def get_database_url():
    """Get database URL from config file."""
    import yaml

    config_paths = ["/etc/sysmanage.yaml", "sysmanage-dev.yaml"]

    for path in config_paths:
        try:
            with open(path, "r") as f:
                config = yaml.safe_load(f)
                db_config = config.get("database", {})

                # Check if it has PostgreSQL-style config (host, port, etc.)
                if "host" in db_config:
                    host = db_config.get("host", "localhost")
                    port = db_config.get("port", 5432)
                    name = db_config.get("name", "sysmanage")
                    user = db_config.get("user", "sysmanage")
                    password = db_config.get("password", "")
                    url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
                    print(f"Using PostgreSQL database: {host}:{port}/{name}")
                    return url
                elif "path" in db_config:
                    db_path = db_config.get("path", "sysmanage.db")
                    print(f"Using SQLite database: {db_path}")
                    return f"sqlite:///{db_path}"
                else:
                    # Default to PostgreSQL with the config values
                    host = db_config.get("host", "localhost")
                    port = db_config.get("port", 5432)
                    name = db_config.get("name", "sysmanage")
                    user = db_config.get("user", "sysmanage")
                    password = db_config.get("password", "")
                    url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
                    print(f"Using PostgreSQL database: {host}:{port}/{name}")
                    return url
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Warning: Error reading {path}: {e}")
            continue

    # Default to SQLite
    print("No config found, using default SQLite database")
    return "sqlite:///sysmanage.db"


def create_test_user():
    """Create a test user for E2E tests with all security roles."""
    db_url = get_database_url()
    print(f"Connecting to database...")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Check if user already exists
        result = session.execute(
            text('SELECT id FROM "user" WHERE userid = :email'),
            {"email": TEST_USER_EMAIL},
        )
        existing = result.fetchone()

        if existing:
            user_id = existing[0]
            print(f"Test user {TEST_USER_EMAIL} already exists, ensuring roles are assigned...")
            # Ensure all security roles are assigned
            assign_all_security_roles(session, user_id)
            return True

        # Hash the password using argon2
        hasher = PasswordHasher()
        hashed_password = hasher.hash(TEST_USER_PASSWORD)

        # Generate a UUID for the user
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Insert the test user
        session.execute(
            text("""
                INSERT INTO "user" (
                    id, active, userid, hashed_password,
                    is_locked, failed_login_attempts, is_admin,
                    first_name, last_name, created_at, updated_at
                ) VALUES (
                    :id, :active, :userid, :hashed_password,
                    :is_locked, :failed_login_attempts, :is_admin,
                    :first_name, :last_name, :created_at, :updated_at
                )
            """),
            {
                "id": user_id,
                "active": True,
                "userid": TEST_USER_EMAIL,
                "hashed_password": hashed_password,
                "is_locked": False,
                "failed_login_attempts": 0,
                "is_admin": True,  # Admin so they can access all features
                "first_name": "E2E",
                "last_name": "Test",
                "created_at": now,
                "updated_at": now,
            },
        )
        session.commit()
        print(f"Created test user: {TEST_USER_EMAIL}")
        print("Password: (see TEST_USER_PASSWORD constant)")  # nosec: don't log actual password

        # Assign all security roles to the test user
        assign_all_security_roles(session, user_id)

        return True

    except Exception as e:
        session.rollback()
        print(f"Error creating test user: {e}")
        return False
    finally:
        session.close()


def assign_all_security_roles(session, user_id):
    """Assign all security roles to the test user for full permissions."""
    try:
        # Get all security role IDs
        result = session.execute(text('SELECT id, name FROM security_roles'))
        roles = result.fetchall()

        if not roles:
            print("Warning: No security roles found in database")
            return

        roles_assigned = 0
        for role_id, role_name in roles:
            # Check if user already has this role
            existing = session.execute(
                text(
                    'SELECT id FROM user_security_roles WHERE user_id = :user_id AND role_id = :role_id'
                ),
                {"user_id": user_id, "role_id": role_id},
            ).fetchone()

            if not existing:
                # Assign the role
                session.execute(
                    text("""
                        INSERT INTO user_security_roles (id, user_id, role_id)
                        VALUES (:id, :user_id, :role_id)
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "role_id": role_id,
                    },
                )
                roles_assigned += 1

        session.commit()
        print(f"Assigned {roles_assigned} security roles to test user (total roles: {len(roles)})")

    except Exception as e:
        session.rollback()
        print(f"Error assigning security roles: {e}")


def delete_test_user():
    """Delete the test user after E2E tests."""
    db_url = get_database_url()
    print(f"Connecting to database...")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get the user ID first
        result = session.execute(
            text('SELECT id FROM "user" WHERE userid = :email'),
            {"email": TEST_USER_EMAIL},
        )
        row = result.fetchone()

        if not row:
            print(f"Test user {TEST_USER_EMAIL} not found (already deleted?)")
            return True

        user_id = row[0]

        # Try to delete related records (ignore errors if tables don't exist)
        related_tables = [
            "user_security_roles",
            "user_dashboard_card_preference",
            "user_data_grid_column_preference",
        ]

        for table in related_tables:
            try:
                # Table names are from hardcoded list above, not user input
                session.execute(
                    text(f'DELETE FROM "{table}" WHERE user_id = :user_id'),  # nosec B608
                    {"user_id": user_id},
                )
            except Exception:
                # Table might not exist or have different name, ignore
                session.rollback()
                pass

        # Delete the test user
        result = session.execute(
            text('DELETE FROM "user" WHERE userid = :email'),
            {"email": TEST_USER_EMAIL},
        )
        session.commit()

        if result.rowcount > 0:
            print(f"Deleted test user: {TEST_USER_EMAIL}")
        else:
            print(f"Test user {TEST_USER_EMAIL} not found (already deleted?)")
        return True

    except Exception as e:
        session.rollback()
        print(f"Error deleting test user: {e}")
        return False
    finally:
        session.close()


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ["create", "delete"]:
        print("Usage: python scripts/e2e_test_user.py [create|delete]")
        sys.exit(1)

    action = sys.argv[1]

    if action == "create":
        success = create_test_user()
    else:
        success = delete_test_user()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
