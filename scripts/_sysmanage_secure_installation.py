#!/usr/bin/env python3
"""
SysManage Secure Installation Script (Internal)
Initializes a fresh SysManage installation with a new admin user.
Inspired by mysql_secure_installation.

This is the internal Python script. Users should run:
  scripts/sysmanage_secure_installation

The wrapper script handles privilege elevation and virtual environment setup.
"""

import getpass
import os
import platform
import re
import secrets
import shutil
import string
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

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
    import yaml
    from argon2 import PasswordHasher

    from alembic import command
    from alembic.config import Config
except ImportError as e:
    print(f"Error: Missing required dependency: {e}")
    print("Please ensure you have activated the virtual environment and installed all dependencies.")
    print("Run: source .venv/bin/activate && pip install -r requirements.txt")
    sys.exit(1)

# Import backend modules for config loading
try:
    from backend.config.config import CONFIG_PATH, get_config
    from backend.persistence import models
    from backend.persistence.db import SessionLocal, get_engine
except ImportError as e:
    print(f"Error importing backend modules: {e}")
    print("Please ensure you are running this script from the SysManage project root directory.")
    sys.exit(1)

def check_elevated_privileges():
    """Check if the script is running with elevated privileges."""
    system = platform.system()

    if system in ["Linux", "Darwin", "FreeBSD", "OpenBSD", "NetBSD"]:
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

def get_make_command():
    """Get the appropriate make command for the current platform."""
    system = platform.system()

    # On BSD systems, prefer gmake if available for GNU Make compatibility
    if system in ["OpenBSD", "FreeBSD", "NetBSD"]:
        try:
            # Check if gmake is available
            subprocess.run(['gmake', '--version'], capture_output=True, text=True, timeout=5)
            return 'gmake'
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            # Fall back to make if gmake is not available
            return 'make'

    # For Linux, macOS, and other systems, use make
    return 'make'

def get_original_user():
    """Get the original user who invoked sudo/doas, if running under elevated privileges."""
    # Check for explicitly passed original user (for doas)
    original_user = os.environ.get('ORIGINAL_USER')
    if original_user:
        return original_user

    # Check if running under sudo
    sudo_user = os.environ.get('SUDO_USER')
    if sudo_user:
        return sudo_user

    # Check if running under doas (OpenBSD/FreeBSD)
    doas_user = os.environ.get('DOAS_USER')
    if doas_user:
        return doas_user

    # Fall back to current user
    if platform.system() == "Windows":
        return os.environ.get('USERNAME', 'user')
    else:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name

def fix_file_ownership(file_path):
    """Fix file ownership to the original user if running under sudo/doas."""
    # Windows doesn't need ownership fixing (no sudo/doas concept)
    if platform.system() == "Windows":
        return

    try:
        original_user = get_original_user()
        elevated_user = os.environ.get('SUDO_USER') or os.environ.get('DOAS_USER') or os.environ.get('ORIGINAL_USER')

        if elevated_user and original_user:
            import grp
            import pwd

            # Get user and group info
            user_info = pwd.getpwnam(original_user)
            uid = user_info.pw_uid
            gid = user_info.pw_gid

            # Change ownership back to original user
            os.chown(file_path, uid, gid)
            print(f"  Fixed ownership of {file_path} to {original_user}")

    except Exception as e:
        print(f"  Warning: Could not fix ownership of {file_path}: {e}")

def setup_netbsd_gcc14_libstdcpp():
    """Create libstdc++.so.9 symlink for NetBSD GCC 14 compatibility."""
    if platform.system() != "NetBSD":
        return

    print("\n--- Setting up NetBSD GCC 14 libstdc++ compatibility ---")

    gcc14_lib = Path("/usr/pkg/gcc14/lib")
    if not gcc14_lib.exists():
        print("  GCC 14 not found at /usr/pkg/gcc14, skipping symlink setup")
        return

    symlink_path = gcc14_lib / "libstdc++.so.9"
    target = "libstdc++.so.7.33"

    if symlink_path.exists() or symlink_path.is_symlink():
        print(f"  libstdc++.so.9 symlink already exists")
        return

    try:
        print(f"  Creating symlink: {symlink_path} -> {target}")
        symlink_path.symlink_to(target)
        print("  ✅ Symlink created successfully")
    except PermissionError:
        print("  ❌ Permission denied. Please run manually:")
        print(f"     sudo ln -s {target} {symlink_path}")
        sys.exit(1)
    except Exception as e:
        print(f"  ⚠️ Warning: Could not create symlink: {e}")

def run_make_install_dev():
    """Run make install-dev to set up dependencies."""
    print("\n--- Installing Development Dependencies ---")

    # Set up NetBSD GCC 14 libstdc++ symlink first (requires root)
    setup_netbsd_gcc14_libstdcpp()

    make_cmd = get_make_command()
    print(f"This will run '{make_cmd} install-dev' to install Python dependencies,")
    print("set up the virtual environment, and install OpenBAO if needed.")

    confirm = input("\nPress Enter to continue or Ctrl+C to cancel...")

    try:
        print(f"Running {make_cmd} install-dev...")
        print("(This may take several minutes and may prompt for sudo password...)")

        # Preserve user's PATH to ensure tools like 'bao' are found
        env = os.environ.copy()
        original_user = os.environ.get('SUDO_USER') or os.environ.get('DOAS_USER') or os.environ.get('ORIGINAL_USER')
        if original_user:
            # Get the user's home directory
            import pwd
            try:
                user_info = pwd.getpwnam(original_user)
                user_home = user_info.pw_dir

                # Add ~/.local/bin to PATH if not already present
                current_path = env.get('PATH', '')
                local_bin = os.path.join(user_home, '.local', 'bin')
                if local_bin not in current_path:
                    env['PATH'] = f"{local_bin}:{current_path}"

            except (KeyError, ImportError):
                pass  # Fall back to default environment

        result = subprocess.run([make_cmd, 'install-dev'], cwd=project_root,
                              text=True, timeout=900, env=env)

        if result.returncode != 0:
            print(f"Error: make install-dev failed with return code {result.returncode}")
            sys.exit(1)

        print("Dependencies installed successfully!")

    except subprocess.TimeoutExpired:
        print("Error: make install-dev timed out after 15 minutes")
        sys.exit(1)
    except Exception as e:
        print(f"Error running make install-dev: {e}")
        sys.exit(1)

def generate_secure_db_password(length=32):
    """Generate a secure random password for the database."""
    # Use alphanumeric characters (avoid special chars for DB compatibility)
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def update_postgres_user_password(username, password):
    """Update the PostgreSQL user's password using psql."""
    try:
        # Use sudo -u postgres to run psql as the postgres user
        sql_command = f"ALTER USER {username} PASSWORD '{password}';"
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c', sql_command],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print("  PostgreSQL password updated successfully.")
            return True
        else:
            print(f"  Failed to update PostgreSQL password: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("  Error: PostgreSQL password update timed out")
        return False
    except Exception as e:
        print(f"  Error updating PostgreSQL password: {e}")
        return False

def get_database_config():
    """Prompt for database configuration."""
    print("\n--- Database Configuration ---")

    while True:
        host = input("Database host [localhost]: ").strip() or "localhost"
        port = input("Database port [5432]: ").strip() or "5432"
        try:
            port = int(port)
            break
        except ValueError:
            print("Invalid port number. Please enter a valid integer.")

    database = input("Database name [sysmanage]: ").strip() or "sysmanage"
    username = input("Database username [sysmanage]: ").strip() or "sysmanage"

    while True:
        password = getpass.getpass("Database password: ")
        if password:
            break
        print("Password cannot be empty.")

    return {
        'host': host,
        'port': port,
        'database': database,
        'username': username,
        'password': password
    }

def test_database_connection(db_config):
    """Test database connectivity."""
    try:
        import psycopg2

        conn_str = (f"host={db_config['host']} "
                   f"port={db_config['port']} "
                   f"dbname={db_config['database']} "
                   f"user={db_config['username']} "
                   f"password={db_config['password']}")

        conn = psycopg2.connect(conn_str)
        conn.close()
        return True
    except ImportError:
        print("Error: psycopg2 not installed. This should have been installed by make install-dev.")
        return False
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False

def update_database_config(config_path, db_config):
    """Update configuration file with database settings."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}

        # Update database configuration
        if 'database' not in config:
            config['database'] = {}

        config['database'].update({
            'host': db_config['host'],
            'port': db_config['port'],
            'database': db_config['database'],
            'username': db_config['username'],
            'password': db_config['password']
        })

        # Write updated config
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print("  Database configuration updated successfully.")

    except Exception as e:
        print(f"Error updating database configuration: {e}")
        sys.exit(1)

def check_database_connectivity():
    """Check database connectivity and configure if needed."""
    print("\n--- Checking Database Connectivity ---")

    config_path = get_config_file_path()
    if not config_path:
        print("Error: Could not find configuration file.")
        sys.exit(1)

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}

        # Check if database config exists
        db_config = config.get('database', {})

        # Check for the correct field names used in sysmanage.yaml
        required_fields = ['host', 'port', 'password']
        db_name_field = 'name' if 'name' in db_config else 'database'
        user_field = 'user' if 'user' in db_config else 'username'

        # Add the name and user fields to required check
        if db_name_field in db_config:
            required_fields.append(db_name_field)
        if user_field in db_config:
            required_fields.append(user_field)

        # Check if password is a placeholder that needs to be changed
        password_is_placeholder = False
        if 'password' in db_config:
            placeholder_passwords = ['CHANGE_ME_PLEASE!', 'changeme', 'password', 'GENERATE_NEW_PASSWORD']
            if db_config['password'] in placeholder_passwords:
                password_is_placeholder = True
                print("  Detected placeholder database password - will generate secure password")

        if not all(key in db_config for key in required_fields):
            print("  Database configuration is incomplete or missing.")
            print(f"  Found fields: {list(db_config.keys())}")
            print(f"  Required fields: {required_fields}")
        else:
            print("  Testing existing database configuration...")
            # Normalize the config for the connection test
            normalized_config = {
                'host': db_config['host'],
                'port': db_config['port'],
                'database': db_config.get('name', db_config.get('database')),
                'username': db_config.get('user', db_config.get('username')),
                'password': db_config['password']
            }

            # If password is a placeholder or connection fails, generate new password
            connection_failed = not test_database_connection(normalized_config)

            if password_is_placeholder or connection_failed:
                if connection_failed:
                    print("  Database connection failed with existing configuration.")

                print("  Generating secure database password...")
                new_password = generate_secure_db_password()

                print("  Updating PostgreSQL password for database user...")
                if update_postgres_user_password(normalized_config['username'], new_password):
                    # Update the config with new password
                    normalized_config['password'] = new_password

                    # Test connection with new password
                    print("  Testing database connection with new password...")
                    if test_database_connection(normalized_config):
                        print("  Database connection successful with new password!")
                        # Update the YAML file
                        update_database_config(config_path, normalized_config)
                        return
                    else:
                        print("  Error: Connection failed even after updating password.")
                        print("  You may need to manually configure the database.")
                else:
                    print("  Error: Failed to update PostgreSQL password.")
                    print("  Please ensure PostgreSQL is running and you have sudo access.")
            else:
                print("  Database connection successful!")
                return

        # Offer to configure database
        print("\nDatabase configuration is needed.")
        while True:
            choice = input("Do you want me to help configure the database settings? (yes/no): ").strip().lower()
            if choice in ['yes', 'y']:
                db_config = get_database_config()

                print("  Testing database connection...")
                if test_database_connection(db_config):
                    print("  Database connection successful!")
                    update_database_config(config_path, db_config)
                    return
                else:
                    print("  Connection failed. Please check your database settings and try again.")
                    retry = input("Would you like to try different settings? (yes/no): ").strip().lower()
                    if retry not in ['yes', 'y']:
                        print("Database setup cancelled.")
                        sys.exit(1)
            elif choice in ['no', 'n']:
                print("Error: Database connectivity is required for SysManage installation.")
                print("Please configure your database settings in the YAML file manually.")
                sys.exit(1)
            else:
                print("Please answer 'yes' or 'no'.")

    except Exception as e:
        print(f"Error checking database connectivity: {e}")
        sys.exit(1)

def run_database_migrations():
    """Run database migrations, handling existing databases intelligently."""
    print("\n--- Running Database Migrations ---")

    try:
        from sqlalchemy import text
        engine = get_engine()

        # Check current database state
        print("Analyzing current database state...")
        with engine.begin() as connection:
            # Get all existing tables
            result = connection.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
            """))
            existing_tables = [row[0] for row in result]

            # Check if alembic_version table exists and get current revision
            has_alembic_version = 'alembic_version' in existing_tables
            current_revision = None

            if has_alembic_version:
                try:
                    rev_result = connection.execute(text("SELECT version_num FROM alembic_version"))
                    row = rev_result.fetchone()
                    current_revision = row[0] if row else None
                except Exception:
                    pass

            print(f"  Found {len(existing_tables)} tables in database")
            if has_alembic_version and current_revision:
                print(f"  Current alembic revision: {current_revision}")
            elif has_alembic_version:
                print("  Alembic version table exists but is empty")
            else:
                print("  No alembic version tracking found")

        # Determine strategy based on database state
        expected_tables = ['user', 'host', 'secret', 'host_certificates']  # Core tables we expect
        has_core_tables = any(table in existing_tables for table in expected_tables)

        if has_core_tables and not current_revision:
            print("  Strategy: Existing database detected, synchronizing alembic tracking...")
            # Database has tables but no proper alembic tracking - stamp it
            strategy = "stamp"
        elif existing_tables and current_revision:
            print("  Strategy: Database properly tracked, running incremental migrations...")
            # Database is properly tracked - just run normal upgrade
            strategy = "upgrade"
        else:
            print("  Strategy: Empty or incomplete database, running full migration...")
            # Empty database or problematic state - clean slate
            strategy = "clean"

        # Set DATABASE_URL environment variable to match sysmanage config
        # This ensures alembic uses the same database as our script
        import yaml
        config_path = get_config_file_path()
        if config_path:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}

            db_config = config.get('database', {})
            host = db_config.get('host', 'localhost')
            port = db_config.get('port', 5432)
            database = db_config.get('name', db_config.get('database', 'sysmanage'))
            username = db_config.get('user', db_config.get('username', 'sysmanage'))
            password = db_config.get('password', '')

            database_url = f"postgresql://{username}:{password}@{host}:{port}/{database}"
            print(f"  Setting DATABASE_URL for alembic: postgresql://{username}:***@{host}:{port}/{database}")
        else:
            database_url = None
            print("  Warning: Could not determine database URL from config")

        # Set up environment for subprocess
        env = os.environ.copy()
        if database_url:
            env['DATABASE_URL'] = database_url

        # Execute strategy
        if strategy == "stamp":
            print("Synchronizing alembic tracking with existing database...")
            result = subprocess.run([sys.executable, '-m', 'alembic', 'stamp', 'head'], cwd=project_root,
                                  capture_output=True, text=True, timeout=60, env=env)
            if result.returncode == 0:
                print("  Database tracking synchronized successfully!")
            else:
                print(f"  Failed to stamp database: {result.stderr}")
                sys.exit(1)

        elif strategy == "upgrade":
            print("Running incremental database migrations...")
            make_cmd = get_make_command()
            result = subprocess.run([make_cmd, 'migrate'], cwd=project_root,
                                  capture_output=True, text=True, timeout=120, env=env)
            if result.returncode == 0:
                print("  Incremental migrations completed successfully!")
            else:
                print(f"  Migration failed: {result.stderr}")
                sys.exit(1)

        elif strategy == "clean":
            print("Performing clean database migration...")

            # Clean up any existing tables
            with engine.begin() as connection:
                if existing_tables:
                    for table in existing_tables:
                        try:
                            # Use SQLAlchemy's quoted identifier to prevent SQL injection
                            from sqlalchemy import DDL
                            drop_stmt = DDL(f'DROP TABLE IF EXISTS "{table}" CASCADE')
                            connection.execute(drop_stmt)
                            print(f"  Dropped existing table: {table}")
                        except Exception as e:
                            print(f"  Warning: Could not drop {table}: {e}")

            # Use the comprehensive migration specifically
            print("  Running comprehensive database migration from scratch...")
            # Use python -m alembic to ensure we use the virtual environment's alembic
            result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=project_root,
                                  capture_output=True, text=True, timeout=120, env=env)
            if result.returncode == 0:
                print("  Comprehensive migration completed successfully!")
            else:
                print(f"  Migration failed: {result.stderr}")
                print(f"  STDOUT: {result.stdout}")
                sys.exit(1)

        # Show final output if there is any
        if result.stdout:
            print("Migration output:")
            for line in result.stdout.split('\n'):
                if line.strip():
                    print(f"  {line}")

    except subprocess.TimeoutExpired:
        print("Error: Database migrations timed out after 2 minutes")
        sys.exit(1)
    except Exception as e:
        print(f"Error running database migrations: {e}")
        sys.exit(1)

def get_user_input():
    """Prompt for initial admin user information."""
    print("\n" + "="*60)
    print("SysManage Secure Installation")
    print("="*60)
    print("\nThis script will initialize a fresh SysManage installation.")
    print("It will:")
    print("  1. Install development dependencies")
    print("  2. Check database connectivity")
    print("  3. Generate new security keys")
    print("  4. Drop and recreate all database tables")
    print("  5. Run database migrations")
    print("  6. Initialize OpenBAO vault (if available)")
    print("  7. Install telemetry stack (optional)")
    print("  8. Create an initial admin user")
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
    """Drop all tables properly while preserving migration system integrity."""
    print("\n--- Dropping existing database tables ---")

    try:
        # Import text for raw SQL execution
        from sqlalchemy import text

        # Get the engine instance
        engine = get_engine()

        # Use a separate connection to ensure we see the same state as alembic will
        with engine.begin() as connection:
            current_schema = connection.execute(text("SELECT current_schema()")).scalar()
            print(f"  Current schema: {current_schema}")

            # Get all table names including system tables
            result = connection.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """))
            table_names = [row[0] for row in result]

            print(f"  Found {len(table_names)} tables in public schema:")
            for table_name in table_names:
                print(f"    - {table_name}")

            if table_names:
                # Drop tables in dependency order (reverse of typical creation order)
                # This helps avoid foreign key constraint issues
                print("  Dropping tables with CASCADE...")

                for table_name in table_names:
                    try:
                        print(f"  Dropping table: {table_name}")
                        # Use SQLAlchemy's quoted identifier to prevent SQL injection
                        from sqlalchemy import DDL
                        drop_stmt = DDL(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
                        connection.execute(drop_stmt)
                    except Exception as e:
                        print(f"    Warning: Could not drop table {table_name}: {e}")

                print("  All tables dropped successfully.")
            else:
                print("  No tables found to drop.")

            # Force a connection refresh to ensure subsequent queries see the changes
            # This addresses potential transaction isolation issues
            connection.execute(text('SELECT 1'))  # Force a round-trip

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

        config['security']['password_salt'] = salt
        config['security']['jwt_secret'] = jwt_secret

        # Remove deprecated admin credentials (admin user is now created via the installation script)
        if 'admin_userid' in config['security']:
            del config['security']['admin_userid']
            print("  Removed deprecated admin_userid from config")
        if 'admin_password' in config['security']:
            del config['security']['admin_password']
            print("  Removed deprecated admin_password from config")

        # Try to write directly first
        try:
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            print("  Configuration updated successfully.")
        except PermissionError:
            # If permission denied, use privilege escalation
            print("  Requires elevated privileges to update system config file...")

            # Create temporary file with updated config
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp_file:
                yaml.dump(config, tmp_file, default_flow_style=False, sort_keys=False)
                tmp_path = tmp_file.name

            try:
                # Detect privilege escalation command
                priv_cmd = None
                if platform.system() in ['OpenBSD', 'FreeBSD', 'NetBSD']:
                    import subprocess
                    try:
                        subprocess.run(['doas', 'true'], check=True, capture_output=True)
                        priv_cmd = 'doas'
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        try:
                            subprocess.run(['sudo', '-n', 'true'], check=True, capture_output=True)
                            priv_cmd = 'sudo'
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            pass
                else:
                    import subprocess
                    try:
                        subprocess.run(['sudo', '-n', 'true'], check=True, capture_output=True)
                        priv_cmd = 'sudo'
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        pass

                if priv_cmd:
                    print(f"  Using {priv_cmd} to update configuration file...")
                    import subprocess
                    result = subprocess.run([priv_cmd, 'cp', tmp_path, config_path],
                                          capture_output=True, text=True)

                    if result.returncode == 0:
                        print("  Configuration updated successfully with elevated privileges.")
                    else:
                        print(f"Error updating configuration with {priv_cmd}: {result.stderr}")
                        sys.exit(1)
                else:
                    print("Error: No privilege escalation method available (doas/sudo).")
                    print("Please run with appropriate privileges or copy the config manually.")
                    sys.exit(1)

            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_path)
                except:
                    pass

    except Exception as e:
        print(f"Error updating configuration: {e}")
        sys.exit(1)

def find_vault_binary():
    """Find OpenBAO or Vault binary."""
    system = platform.system()

    if system == "Windows":
        # Windows-specific search
        # Check for bao/vault in PATH first
        for cmd in ['bao.exe', 'bao', 'vault.exe', 'vault']:
            binary_path = shutil.which(cmd)
            if binary_path and os.path.exists(binary_path):
                return binary_path

        # Check common Windows locations
        common_paths = [
            os.path.expanduser(r'~\AppData\Local\bin\bao.exe'),
            r'C:\Program Files\OpenBAO\bao.exe',
            r'C:\Program Files (x86)\OpenBAO\bao.exe',
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path

    else:
        # Unix-like systems (Linux, BSD, macOS)
        # Get the original user's home directory (before sudo)
        original_user = get_original_user()

        # Check for bao in original user's home directory first
        try:
            import pwd
            user_info = pwd.getpwnam(original_user)
            user_home = user_info.pw_dir
            bao_path = os.path.join(user_home, '.local', 'bin', 'bao')
            if os.path.exists(bao_path):
                return bao_path
        except Exception as e:
            print(f"  Debug: Could not check user home for bao: {e}")

        # Check system PATH
        for cmd in ['bao', 'vault']:
            try:
                result = subprocess.run(['which', cmd], capture_output=True, text=True)
                if result.returncode == 0:
                    binary_path = result.stdout.strip()
                    if binary_path:
                        # Expand ~ if present (which sometimes returns unexpanded paths)
                        expanded_path = os.path.expanduser(binary_path)
                        if os.path.exists(expanded_path):
                            return expanded_path
            except:
                pass

    return None

def install_telemetry_stack():
    """Install OpenTelemetry and Prometheus for performance monitoring."""
    print("\n--- Installing Telemetry Stack ---")

    telemetry_script = project_root / 'scripts' / 'install-telemetry.py'
    if not telemetry_script.exists():
        print("  Telemetry installation script not found, skipping telemetry setup")
        return False

    print("  This will install OpenTelemetry Collector and Prometheus for monitoring SysManage performance.")
    install_telemetry = input("  Install telemetry stack? (y/n): ").strip().lower()

    if install_telemetry != 'y' and install_telemetry != 'yes':
        print("  Skipping telemetry stack installation")
        return False

    try:
        print("  Running telemetry installation script...")
        # Run the telemetry installation script with elevated privileges
        result = subprocess.run([
            sys.executable, str(telemetry_script)
        ], timeout=300, capture_output=False)

        if result.returncode == 0:
            print("  ✅ Telemetry stack installed successfully!")
            return True
        else:
            print("  ❌ Telemetry stack installation failed")
            return False

    except subprocess.TimeoutExpired:
        print("  ❌ Telemetry installation timed out")
        return False
    except Exception as e:
        print(f"  ❌ Error installing telemetry stack: {e}")
        return False


def initialize_vault():
    """Initialize OpenBAO vault with production configuration."""
    print("\n--- Initializing OpenBAO Vault ---")

    vault_cmd = find_vault_binary()
    if not vault_cmd:
        print("  OpenBAO/Vault not found, skipping vault initialization")
        print("  You can install OpenBAO later with: make install-dev")
        return

    print(f"  Using vault binary: {vault_cmd}")

    # Clean up any stale vault data from previous failed attempts
    data_dir = project_root / 'data' / 'openbao'
    if data_dir.exists() and any(data_dir.iterdir()):
        print("  Cleaning up stale vault data from previous installation...")
        import shutil
        shutil.rmtree(data_dir, ignore_errors=True)
        data_dir.mkdir(parents=True, exist_ok=True)

    # Create production configuration
    vault_config_path = project_root / 'openbao.hcl'
    vault_config = '''storage "file" {
  path = "./data/openbao"
}

listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = true
}

api_addr = "http://127.0.0.1:8200"
cluster_addr = "https://127.0.0.1:8201"
ui = true
'''

    print("  Creating OpenBAO configuration file...")
    with open(vault_config_path, 'w') as f:
        f.write(vault_config)

    # Create data directory
    data_dir = project_root / 'data' / 'openbao'
    data_dir.mkdir(parents=True, exist_ok=True)

    # Fix ownership of data directory (if running under sudo)
    fix_file_ownership(data_dir)

    # Start vault server
    print("  Starting OpenBAO server...")
    log_file = project_root / 'logs' / 'openbao.log'
    log_file.parent.mkdir(exist_ok=True)

    # Fix ownership of logs directory (if running under sudo)
    fix_file_ownership(log_file.parent)

    # Use absolute path for config file
    vault_config_abs_path = str(vault_config_path.absolute())

    # Start vault server with platform-specific handling
    if platform.system() == "Windows":
        # On Windows, use CREATE_NEW_PROCESS_GROUP to properly detach
        vault_process = subprocess.Popen([
            vault_cmd, 'server', f'-config={vault_config_abs_path}'
        ],
        stdout=open(log_file, 'w'),
        stderr=subprocess.STDOUT,
        cwd=str(project_root),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        vault_process = subprocess.Popen([
            vault_cmd, 'server', f'-config={vault_config_abs_path}'
        ], stdout=open(log_file, 'w'), stderr=subprocess.STDOUT, cwd=str(project_root))

    # Fix ownership of the log file after it's created
    fix_file_ownership(log_file)

    # Wait for server to start (longer on Windows)
    if platform.system() == "Windows":
        time.sleep(8)
    else:
        time.sleep(5)

    # Set vault address
    env = os.environ.copy()
    env['BAO_ADDR'] = 'http://127.0.0.1:8200'

    # Verify the vault server is actually running and responding
    print("  Verifying vault server is running...")
    try:
        status_result = subprocess.run([
            vault_cmd, 'status'
        ], env=env, capture_output=True, text=True, timeout=10)
        print(f"  Vault status check: {status_result.returncode}")
        if "storage type" in status_result.stdout.lower():
            print(f"  Vault is using correct storage configuration")
    except Exception as e:
        print(f"  Warning: Could not verify vault status: {e}")

    try:
        # Initialize vault
        print("  Initializing vault...")
        print(f"  DEBUG: Running command: {vault_cmd} operator init -key-shares=1 -key-threshold=1 -format=json")
        print(f"  DEBUG: BAO_ADDR={env.get('BAO_ADDR')}")
        result = subprocess.run([
            vault_cmd, 'operator', 'init',
            '-key-shares=1', '-key-threshold=1', '-format=json'
        ], env=env, capture_output=True, text=True, timeout=30)

        print(f"  DEBUG: Init result return code: {result.returncode}")
        print(f"  DEBUG: Init result stdout: {result.stdout[:200] if result.stdout else 'None'}")
        print(f"  DEBUG: Init result stderr: {result.stderr[:200] if result.stderr else 'None'}")

        if result.returncode != 0:
            print(f"  Error initializing vault (return code {result.returncode})")
            print(f"  STDERR: {result.stderr}")
            print(f"  STDOUT: {result.stdout}")
            # If vault is already initialized, check if credentials exist
            if "already initialized" in result.stderr.lower():
                print("  Vault already initialized")
                credentials_file = project_root / '.vault_credentials'
                if credentials_file.exists():
                    print("  Vault credentials file exists, fixing ownership...")
                    fix_file_ownership(credentials_file)
                    pid_file = project_root / '.openbao.pid'
                    if pid_file.exists():
                        fix_file_ownership(pid_file)
                else:
                    print("  ERROR: Vault is initialized but credentials file is missing!")
                    print("  This means the vault was previously initialized but the credentials were not saved.")
                    print("  You need to either:")
                    print("    1. Delete the vault data directory and re-run: rm -rf data/openbao")
                    print("    2. Or manually unseal the vault if you have the credentials")
            else:
                print(f"  Vault initialization failed for another reason")
            vault_process.terminate()
            return

        import json
        init_data = json.loads(result.stdout)
        unseal_key = init_data['unseal_keys_b64'][0]
        root_token = init_data['root_token']

        # Unseal vault
        print("  Unsealing vault...")
        result = subprocess.run([
            vault_cmd, 'operator', 'unseal', unseal_key
        ], env=env, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            print(f"  Error unsealing vault: {result.stderr}")
            vault_process.terminate()
            return

        # Set root token
        env['BAO_TOKEN'] = root_token

        # Enable KV v2 secrets engine
        print("  Enabling KV v2 secrets engine...")
        result = subprocess.run([
            vault_cmd, 'secrets', 'enable', '-version=2', '-path=secret', 'kv'
        ], env=env, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            print(f"  Warning: Could not enable KV v2 secrets engine: {result.stderr}")

        # Save credentials
        credentials_file = project_root / '.vault_credentials'
        print("  Saving vault credentials...")
        with open(credentials_file, 'w') as f:
            f.write("# OpenBAO Vault Credentials - KEEP SECURE\n")
            f.write("# Generated during vault initialization\n")
            f.write(f"UNSEAL_KEY={unseal_key}\n")
            f.write(f"ROOT_TOKEN={root_token}\n")

        # Set restrictive permissions on credentials file
        os.chmod(credentials_file, 0o600)

        # Fix ownership back to original user (if running under sudo)
        fix_file_ownership(credentials_file)

        # Save PID file
        pid_file = project_root / '.openbao.pid'
        with open(pid_file, 'w') as f:
            f.write(str(vault_process.pid))

        # Fix ownership of PID file too
        fix_file_ownership(pid_file)

        print("  OpenBAO vault initialized successfully!")
        print(f"    Root token: {root_token}")
        print(f"    Credentials saved to: {credentials_file}")

        return unseal_key, root_token

    except Exception as e:
        print(f"  Error during vault initialization: {e}")
        vault_process.terminate()
        return None

def update_config_with_vault(config_path, unseal_key=None, root_token=None):
    """Update configuration file with vault settings."""
    if not unseal_key or not root_token:
        return

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}

        # Update vault configuration
        if 'vault' not in config:
            config['vault'] = {}

        config['vault'].update({
            'enabled': True,
            'url': 'http://localhost:8200',
            'token': root_token,
            'mount_path': 'secret',
            'timeout': 30,
            'verify_ssl': False,
            'dev_mode': False,  # Always use production mode
            'server': {
                'enabled': True,
                'config_file': './openbao.hcl',
                'data_path': './data/openbao',
                'unseal_keys': [unseal_key],
                'initialized': True
            }
        })

        # Write updated config
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print("  Configuration updated with vault settings.")

    except Exception as e:
        print(f"  Warning: Could not update config with vault settings: {e}")

def fix_existing_vault_config(config_path):
    """Fix existing vault configuration to use production mode and proper token."""
    print("\n--- Updating Existing Vault Configuration ---")

    try:
        # Check if .vault_credentials exists
        vault_creds_file = project_root / '.vault_credentials'
        if not vault_creds_file.exists():
            print("  No vault credentials found, skipping vault config update")
            return

        # Read credentials
        vault_env = {}
        with open(vault_creds_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    vault_env[key] = value

        root_token = vault_env.get('ROOT_TOKEN')
        if not root_token:
            print("  No ROOT_TOKEN found in credentials, skipping vault config update")
            return

        # Update config file
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}

        if 'vault' in config:
            # Update existing vault configuration to production mode
            config['vault']['dev_mode'] = False
            config['vault']['token'] = root_token
            print(f"  Updated vault configuration:")
            print(f"    - dev_mode: false")
            print(f"    - token: {root_token[:12]}...")

            # Write updated config
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            print("  Vault configuration updated to production mode")
        else:
            print("  No vault configuration found in config file")

    except Exception as e:
        print(f"  Error updating vault configuration: {e}")

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

            print("  Admin user created successfully.")

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

        # Check and fix database password BEFORE running install-dev
        # (install-dev runs migrations which need a working database connection)
        check_database_connectivity()

        # IMPORTANT: Reload config module to pick up the new database password
        # The config module caches the config at import time, so we need to reload it
        import importlib
        import backend.config.config
        import backend.persistence.db
        importlib.reload(backend.config.config)
        importlib.reload(backend.persistence.db)
        from backend.config.config import get_config
        from backend.persistence.db import get_engine

        # Install development dependencies (includes migrations)
        run_make_install_dev()

        # Generate new security keys
        salt, jwt_secret = generate_security_keys()

        # Update configuration file with new keys
        update_config_file(salt, jwt_secret)

        # Reload config AGAIN after updating security keys
        importlib.reload(backend.config.config)
        importlib.reload(backend.persistence.db)
        from backend.config.config import get_config
        from backend.persistence.db import get_engine

        # Load current configuration (after potential database config updates)
        config = get_config()
        if not config:
            print("Error: Could not load configuration.")
            sys.exit(1)

        # Stop SysManage server to release database locks
        print("\n--- Stopping SysManage Server ---")
        try:
            make_cmd = get_make_command()
            result = subprocess.run([make_cmd, 'stop'], cwd=project_root,
                                  capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print("  SysManage server stopped successfully")
            else:
                print(f"  Warning: Could not stop server: {result.stderr}")
                print("  Continuing anyway - database operations may be slower")
        except Exception as e:
            print(f"  Warning: Could not stop server: {e}")
            print("  Continuing anyway - database operations may be slower")

        # Drop all existing tables first
        drop_all_tables(config)

        # Run database migrations to rebuild schema
        run_database_migrations()

        # Fix existing vault configuration if present (updates dev_mode and token)
        config_path = get_config_file_path()
        if config_path:
            fix_existing_vault_config(config_path)

        # Initialize OpenBAO vault (for fresh installations)
        vault_result = initialize_vault()
        if vault_result:
            unseal_key, root_token = vault_result
            if config_path:
                update_config_with_vault(config_path, unseal_key, root_token)

        # Install telemetry stack (optional)
        telemetry_installed = install_telemetry_stack()

        # Reload configuration to ensure we're using the updated salt
        config = get_config()
        if not config:
            print("Error: Could not reload configuration after update.")
            sys.exit(1)

        # Create admin user with new salt
        create_admin_user(user_data, salt)

        # Fix ownership of all created files (important for macOS/Linux when running under sudo)
        print("\n--- Fixing file ownership ---")
        files_to_fix = [
            project_root / '.vault_credentials',
            project_root / '.openbao.pid',
            project_root / 'logs',
            project_root / 'logs' / 'openbao.log',
            project_root / 'openbao.hcl',
            project_root / 'data',
            project_root / 'data' / 'openbao'
        ]

        for file_path in files_to_fix:
            if file_path.exists():
                fix_file_ownership(file_path)

        print("\n" + "="*60)
        print("Installation completed successfully!")
        print("="*60)
        print(f"\nYou can now log in with the credentials you provided")
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
