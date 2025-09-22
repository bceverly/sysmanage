#!/usr/bin/env python3
"""
SysManage Secure Installation Script (Internal)
Initializes a fresh SysManage installation with a new admin user.
Inspired by mysql_secure_installation.

This is the internal Python script. Users should run:
  scripts/sysmanage_secure_installation

The wrapper script handles privilege elevation and virtual environment setup.
"""

import os
import sys
import platform
import getpass
import secrets
import string
import re
from pathlib import Path
from datetime import datetime, timezone
import uuid

# Add the project root to the path so we can import backend modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Also add the virtual environment's site-packages if available
venv_path = project_root / '.venv'
if venv_path.exists():
    site_packages = venv_path / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
    if site_packages.exists():
        sys.path.insert(0, str(site_packages))

try:
    import psycopg2
    from psycopg2 import sql
    from argon2 import PasswordHasher
    import yaml
    from alembic import command
    from alembic.config import Config
except ImportError as e:
    print(f"Error: Missing required dependency: {e}")
    print("Please ensure you have activated the virtual environment and installed all dependencies.")
    print("Run: source .venv/bin/activate && pip install -r requirements.txt")
    sys.exit(1)

# Import backend modules for config loading
try:
    from backend.config.config import get_config, CONFIG_PATH
    from backend.persistence import models
    from backend.persistence.db import SessionLocal, engine
except ImportError as e:
    print(f"Error importing backend modules: {e}")
    print("Please ensure you are running this script from the SysManage project root directory.")
    sys.exit(1)

def check_elevated_privileges():
    """Check if the script is running with elevated privileges."""
    system = platform.system()

    if system in ["Linux", "Darwin", "FreeBSD", "OpenBSD"]:
        # Unix-like systems
        if os.geteuid() != 0:
            print("Error: This script must be run with elevated privileges.")
            print("Please run: sudo scripts/sysmanage_secure_installation")
            sys.exit(1)
    elif system == "Windows":
        # Windows
        try:
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                print("Error: This script must be run with Administrator privileges.")
                print("Please run this script as Administrator.")
                sys.exit(1)
        except Exception:
            print("Warning: Could not verify Administrator privileges on Windows.")
            print("Please ensure you are running as Administrator.")
    else:
        print(f"Warning: Unknown operating system '{system}'. Cannot verify privileges.")

def validate_email(email):
    """Validate email format."""
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def get_user_input():
    """Prompt for initial admin user information."""
    print("\n" + "="*60)
    print("SysManage Secure Installation")
    print("="*60)
    print("\nThis script will initialize a fresh SysManage installation.")
    print("It will:")
    print("  1. Drop and recreate all database tables")
    print("  2. Generate new security keys")
    print("  3. Create an initial admin user")
    print("\nWARNING: This will DELETE all existing data!")

    confirm = input("\nDo you want to continue? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Installation cancelled.")
        sys.exit(0)

    print("\n--- Initial Admin User Setup ---")

    # Get email
    while True:
        email = input("Admin email address: ").strip()
        if validate_email(email):
            break
        print("Invalid email format. Please try again.")

    # Get password (without echo)
    while True:
        password = getpass.getpass("Admin password: ")
        if len(password) < 8:
            print("Password must be at least 8 characters long.")
            continue
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("Passwords do not match. Please try again.")
            continue
        break

    # Get first name
    while True:
        first_name = input("First name: ").strip()
        if first_name:
            break
        print("First name cannot be empty.")

    # Get last name
    while True:
        last_name = input("Last name: ").strip()
        if last_name:
            break
        print("Last name cannot be empty.")

    return {
        'email': email,
        'password': password,
        'first_name': first_name,
        'last_name': last_name
    }

def drop_all_tables(config):
    """Drop all tables including alembic version table."""
    print("\n--- Dropping existing database tables ---")

    db_config = config.get('database', {})

    # Build connection string
    conn_params = {
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'sysmanage'),
        'user': db_config.get('user', 'sysmanage'),
        'password': db_config.get('password', 'sysmanage')
    }

    try:
        # Connect to the database
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = True
        cur = conn.cursor()

        # Get all table names
        cur.execute("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
        """)
        tables = cur.fetchall()

        # Drop each table
        for table in tables:
            table_name = table[0]
            print(f"  Dropping table: {table_name}")
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                sql.Identifier(table_name)
            ))

        print(f"  Dropped {len(tables)} tables successfully.")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error dropping tables: {e}")
        sys.exit(1)

def run_alembic_migrations():
    """Run alembic migrations to create fresh database schema."""
    print("\n--- Running database migrations ---")

    try:
        # Create alembic configuration
        alembic_ini_path = project_root / 'alembic.ini'
        if not alembic_ini_path.exists():
            print(f"Error: alembic.ini not found at {alembic_ini_path}")
            sys.exit(1)

        alembic_cfg = Config(str(alembic_ini_path))

        # Run migrations
        print("  Running migrations to latest version...")
        command.upgrade(alembic_cfg, "head")
        print("  Database schema created successfully.")

    except Exception as e:
        print(f"Error running migrations: {e}")
        sys.exit(1)

def generate_security_keys():
    """Generate new salt and JWT secret."""
    print("\n--- Generating security keys ---")

    # Generate salt (32 bytes, hex encoded)
    salt = secrets.token_hex(32)

    # Generate JWT secret (64 bytes, URL-safe base64 encoded)
    jwt_secret = secrets.token_urlsafe(64)

    print("  Generated new salt and JWT secret.")

    return salt, jwt_secret

def get_config_file_path():
    """Get the actual config file path, checking multiple locations."""
    # Check system config locations first
    if platform.system() == "Windows":
        system_paths = [r"C:\ProgramData\SysManage\sysmanage.yaml"]
    else:
        system_paths = ["/etc/sysmanage.yaml"]

    # Add development/local paths
    local_paths = [
        "sysmanage.yaml",
        "sysmanage-dev.yaml",
        os.path.expanduser("~/sysmanage.yaml")
    ]

    # Check all paths
    for path in system_paths + local_paths:
        if os.path.exists(path):
            return path

    return None

def update_config_file(salt, jwt_secret):
    """Update the configuration file with new security keys."""
    print("\n--- Updating configuration file ---")

    # Find the config file
    config_path = get_config_file_path()
    if not config_path:
        print("Error: Could not find configuration file.")
        print("Searched locations: /etc/sysmanage.yaml, ./sysmanage.yaml, ~/sysmanage.yaml")
        sys.exit(1)

    print(f"  Using config file: {config_path}")

    try:
        # Load existing config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}

        # Update security section
        if 'security' not in config:
            config['security'] = {}

        config['security']['salt'] = salt
        config['security']['jwt_secret'] = jwt_secret

        # Write updated config
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print("  Configuration updated successfully.")

    except Exception as e:
        print(f"Error updating configuration: {e}")
        sys.exit(1)

def create_admin_user(user_data, salt):
    """Create the initial admin user in the database."""
    print("\n--- Creating admin user ---")

    try:
        # Hash the password (salt is handled internally by argon2)
        ph = PasswordHasher()
        hashed_password = ph.hash(user_data['password'])

        # Create database session
        db = SessionLocal()()

        try:
            # Create the admin user
            admin_user = models.User(
                userid=user_data['email'],
                hashed_password=hashed_password,
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                active=True,
                is_admin=True,
                is_locked=False,
                failed_login_attempts=0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

            db.add(admin_user)
            db.commit()

            print(f"  Admin user '{user_data['email']}' created successfully.")

        finally:
            db.close()

    except Exception as e:
        print(f"Error creating admin user: {e}")
        sys.exit(1)

def main():
    """Main installation routine."""
    try:
        # Note: Privilege elevation is handled by the wrapper script
        # check_elevated_privileges() - removed, wrapper handles this

        # Get user input
        user_data = get_user_input()

        # Load current configuration
        config = get_config()
        if not config:
            print("Error: Could not load configuration.")
            sys.exit(1)

        # Drop all existing tables
        drop_all_tables(config)

        # Run alembic migrations
        run_alembic_migrations()

        # Generate new security keys
        salt, jwt_secret = generate_security_keys()

        # Update configuration file
        update_config_file(salt, jwt_secret)

        # Reload configuration to ensure we're using the updated salt
        config = get_config()
        if not config:
            print("Error: Could not reload configuration after update.")
            sys.exit(1)

        # Create admin user with new salt
        create_admin_user(user_data, salt)

        print("\n" + "="*60)
        print("Installation completed successfully!")
        print("="*60)
        print(f"\nYou can now log in with:")
        print(f"  Email: {user_data['email']}")
        print(f"  Password: [the password you provided]")
        print("\nStart the SysManage server with: make start")
        print("Access the web interface at: http://localhost:3000")

    except KeyboardInterrupt:
        print("\n\nInstallation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()