#!/usr/bin/env python3
"""
Security Configuration Migration Script

This script safely migrates JWT secrets and password salts while preserving
existing user accounts. It handles the /etc/sysmanage.yaml priority correctly.

Cross-platform compatible with Windows, macOS, Linux, and BSD.

Usage:
    Python 3.7+:
        python3 scripts/migrate-security-config.py [--jwt-only] [--salt-only] [--dry-run]
        python scripts/migrate-security-config.py [--jwt-only] [--salt-only] [--dry-run]

    Windows:
        py -3 scripts/migrate-security-config.py [--jwt-only] [--salt-only] [--dry-run]
        python scripts/migrate-security-config.py [--jwt-only] [--salt-only] [--dry-run]

Options:
    --jwt-only    Only update JWT secret (safe, no user migration needed)
    --salt-only   Only update password salt (requires user migration)
    --dry-run     Show what would be changed without making changes
"""

import argparse
import secrets
import base64
import os
import sys
import shutil
import subprocess
import yaml
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from argon2 import PasswordHasher

# Add backend to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from backend.config import config
from backend.persistence import models
from backend.services.email_service import email_service


def find_privilege_escalation_tool():
    """Find available privilege escalation tool (sudo, doas, etc.)."""
    if os.name == 'nt':  # Windows
        return 'runas'  # Windows UAC

    # Unix-like systems: check for sudo, doas, etc.
    tools = ['sudo', 'doas', 'su']

    for tool in tools:
        try:
            # Check if tool exists and is executable
            result = subprocess.run(['which', tool], capture_output=True, text=True)
            if result.returncode == 0:
                return tool
        except (subprocess.SubprocessError, FileNotFoundError):
            continue

    return None


def requires_elevated_privileges(file_path):
    """Check if a file requires elevated privileges to modify."""
    try:
        # Try to open file for writing to test permissions
        with open(file_path, 'r+') as f:
            pass
        return False
    except PermissionError:
        return True
    except FileNotFoundError:
        # Check if we can write to the directory
        directory = os.path.dirname(file_path)
        try:
            test_file = os.path.join(directory, f'.write_test_{os.getpid()}')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return False
        except (PermissionError, OSError):
            return True


def run_with_privileges(script_args):
    """Re-run the script with elevated privileges."""
    escalation_tool = find_privilege_escalation_tool()

    if not escalation_tool:
        if os.name == 'nt':  # Windows
            print("[ERROR] Error: Unable to elevate privileges on Windows")
            print("   Please run this script as an administrator:")
            print("   1. Right-click PowerShell or Command Prompt")
            print("   2. Select 'Run as administrator'")
            print("   3. Navigate to the script directory and run again")
        else:  # Unix-like
            print("[ERROR] Error: No privilege escalation tool found (sudo, doas, su)")
            print("   Please run this script as root or install sudo/doas")
        sys.exit(1)

    # Get the current script path and arguments
    script_path = os.path.abspath(__file__)

    print("[SECURITY] Administrative privileges required to modify system configuration files.")
    if os.name == 'nt':  # Windows
        print("   Windows UAC (User Access Control) will prompt for elevation.")
    else:  # Unix-like
        print(f"   You will be prompted for your password to use '{escalation_tool}'.")
    print()

    if escalation_tool == 'runas':
        # Windows UAC
        try:
            import ctypes
            if ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script_path}" {" ".join(script_args)}', None, 1) <= 32:
                print("[ERROR] Failed to elevate privileges")
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Failed to elevate privileges: {e}")
            sys.exit(1)
    else:
        # Unix-like: sudo, doas, su
        cmd = [escalation_tool]

        if escalation_tool == 'su':
            cmd.extend(['-c', f'"{sys.executable}" "{script_path}" {" ".join(script_args)}'])
        else:
            cmd.extend([sys.executable, script_path] + script_args)

        try:
            result = subprocess.run(cmd, check=True)
            sys.exit(result.returncode)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to run with elevated privileges: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n[ERROR] Cancelled by user")
            sys.exit(1)


def generate_jwt_secret():
    """Generate a cryptographically secure JWT secret."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8')


def generate_password_salt():
    """Generate a cryptographically secure password salt."""
    return base64.b64encode(secrets.token_bytes(32)).decode('utf-8')


def generate_temporary_password():
    """Generate a secure 8-character temporary password without ambiguous characters."""
    # Exclude ambiguous characters: 0, O, 1, I, l
    safe_chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz"
    return ''.join(secrets.choice(safe_chars) for _ in range(8))




def get_config_file_path():
    """Get the actual config file path being used (respects priority and cross-platform paths)."""
    # Platform-specific system config locations
    system_config_paths = []

    if os.name == 'nt':  # Windows
        # Windows: Use ProgramData for system-wide config
        system_config_paths = [
            os.path.join(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'), 'SysManage', 'sysmanage.yaml'),
            os.path.join(os.environ.get('ALLUSERSPROFILE', 'C:\\ProgramData'), 'SysManage', 'sysmanage.yaml'),
        ]
    else:  # Unix-like (Linux, macOS, BSD)
        system_config_paths = [
            "/etc/sysmanage.yaml",
            "/usr/local/etc/sysmanage.yaml",  # BSD/macOS alternative
        ]

    # Check system config locations first (security priority)
    for config_path in system_config_paths:
        if os.path.exists(config_path):
            return config_path

    # Fall back to local development config
    local_configs = ["sysmanage-dev.yaml", "sysmanage.yaml"]
    for local_config in local_configs:
        if os.path.exists(local_config):
            return local_config

    print("[ERROR] Error: No configuration file found!")
    print("   Expected locations (in priority order):")
    for path in system_config_paths + local_configs:
        print(f"     - {path}")
    sys.exit(1)


def backup_config_file(config_path, debug=False):
    """Create a backup of the configuration file."""
    backup_path = f"{config_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if debug:
        print(f"[DEBUG] DEBUG: Creating backup from {config_path} to {backup_path}")
    try:
        shutil.copy2(config_path, backup_path)
        print(f"[FILE] Config backup created: {backup_path}")
        if debug:
            print(f"[DEBUG] DEBUG: Backup file exists: {os.path.exists(backup_path)}")
        return backup_path
    except Exception as e:
        print(f"[ERROR] Error creating backup: {e}")
        if debug:
            print(f"[DEBUG] DEBUG: Backup error details: {type(e).__name__}: {e}")
        raise


def load_config_file(config_path):
    """Load YAML configuration file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)
    except Exception as e:
        print(f"[ERROR] Error reading config file {config_path}: {e}")
        sys.exit(1)


def save_config_file(config_path, config_data, debug=False):
    """Save YAML configuration file."""
    if debug:
        print(f"[DEBUG] DEBUG: Attempting to save config to {config_path}")
        print(f"[DEBUG] DEBUG: Config data keys: {list(config_data.keys())}")
        if 'security' in config_data:
            security_keys = list(config_data['security'].keys())
            print(f"[DEBUG] DEBUG: Security section keys: {security_keys}")

    try:
        with open(config_path, 'w', encoding='utf-8') as file:
            yaml.dump(config_data, file, default_flow_style=False, indent=2)
        print(f"[OK] Configuration saved to {config_path}")
        if debug:
            print(f"[DEBUG] DEBUG: File written successfully, checking if file exists: {os.path.exists(config_path)}")
    except Exception as e:
        print(f"[ERROR] Error writing config file {config_path}: {e}")
        if debug:
            print(f"[DEBUG] DEBUG: Save error details: {type(e).__name__}: {e}")
        sys.exit(1)


def get_database_users():
    """Get all users from the database."""
    try:
        app_config = config.get_config()
        db_config = app_config['database']
        DATABASE_URL = f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['name']}"

        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        with SessionLocal() as session:
            users = session.query(models.User).all()
            return [(user.id, user.userid, user.hashed_password) for user in users]
    except Exception as e:
        print(f"[ERROR] Error accessing database: {e}")
        sys.exit(1)


def create_password_reset_token(user_id, session):
    """Create a password reset token for a user."""
    # Generate token
    token = str(uuid.uuid4())

    # Set expiration (24 hours from now)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    # Create token record
    reset_token = models.PasswordResetToken(
        user_id=user_id,
        token=token,
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at,
        is_used=False
    )

    session.add(reset_token)
    return token


def send_password_reset_emails(user_migrations, app_config):
    """Send password reset emails to users after salt migration."""
    if not email_service.is_enabled():
        print("[WARNING] Email service is disabled - cannot send password reset emails")
        print("   Users will need to request password reset manually through the UI")
        return False

    # Build reset URL
    # Check if we have TLS configured to determine protocol
    is_secure = (
        app_config.get("api", {}).get("certFile") is not None
        and len(app_config.get("api", {}).get("certFile", "")) > 0
    )
    protocol = "https" if is_secure else "http"

    # Get configured hostname and frontend port
    hostname = app_config.get("api", {}).get("hostname", "localhost")
    frontend_port = app_config.get("frontend", {}).get("port", 3000)
    base_url = f"{protocol}://{hostname}:{frontend_port}"

    print(f"📧 Sending password reset emails to {len(user_migrations)} users...")

    success_count = 0
    failed_users = []

    for migration in user_migrations:
        reset_url = f"{base_url}/reset-password?token={migration['reset_token']}"

        # Email content
        subject = "Password Reset Required - SysManage Salt Update"

        body = f"""Hello,

Your SysManage account password has been reset due to a security configuration update.

To set a new password, please click the following link:
{reset_url}

This link will expire in 24 hours.

If you have any questions, please contact your system administrator.

--
SysManage System"""

        html_body = f"""<html>
<body>
<p>Hello,</p>

<p>Your SysManage account password has been reset due to a security configuration update.</p>

<p>To set a new password, please click the following link:</p>
<p><a href="{reset_url}">Set New Password</a></p>

<p>This link will expire in 24 hours.</p>

<p>If you have any questions, please contact your system administrator.</p>

<hr>
<p><em>SysManage System</em></p>
</body>
</html>"""

        success = email_service.send_email(
            to_addresses=[migration['userid']],
            subject=subject,
            body=body,
            html_body=html_body
        )

        if success:
            success_count += 1
            print(f"   ✓ Email sent to {migration['userid']}")
        else:
            failed_users.append(migration['userid'])
            print(f"   ✗ Failed to send email to {migration['userid']}")

    print(f"\n📈 Email Results:")
    print(f"   Successfully sent: {success_count}")
    print(f"   Failed to send: {len(failed_users)}")

    if failed_users:
        print(f"\n[WARNING] Failed to send emails to the following users:")
        for user in failed_users:
            print(f"   - {user}")
        print("   These users will need to request password reset manually through the UI")

    return success_count > 0


def migrate_user_passwords(old_salt, new_salt, dry_run=False):
    """Migrate user passwords from old salt to new salt."""
    users = get_database_users()

    if not users:
        print("[INFO]  No database users found - password salt migration not needed")
        return []

    print(f"👥 Found {len(users)} users to migrate:")

    migrations = []
    for user_id, userid, old_hash in users:
        # User will need to reset password through UI - no temporary password needed
        migrations.append({
            'user_id': user_id,
            'userid': userid,
            'temp_password': None  # No password needed - will use password reset
        })

        if dry_run:
            print(f"   - {userid} (ID: {user_id}) -> would receive password reset email")
        else:
            print(f"   - {userid} (ID: {user_id})")

    if dry_run:
        print("[INFO] DRY RUN: Would reset passwords and send password reset emails to all users")
        return migrations

    print("[WARNING]  WARNING: Changing password salt will reset all user passwords!")
    print("   After running this script:")
    print("   1. All user passwords will be reset to secure defaults")
    print("   2. Password reset emails will be sent to users (if email is enabled)")
    print("   3. Users must use the reset links to set new passwords")

    confirm = input("Continue with password salt migration? (yes/no): ")
    if confirm.lower() != 'yes':
        print("[ERROR] Password salt migration cancelled")
        sys.exit(0)

    # Update users with new temporary passwords
    try:
        app_config = config.get_config()
        db_config = app_config['database']
        DATABASE_URL = f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['name']}"

        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        with SessionLocal() as session:
            for migration in migrations:
                user = session.query(models.User).filter(models.User.id == migration['user_id']).first()
                if user:
                    # Set password to a secure default that requires password reset
                    # Use a known invalid hash that forces password reset through UI
                    user.hashed_password = "RESET_REQUIRED_" + base64.b64encode(secrets.token_bytes(16)).decode()
                    user.is_locked = False  # Ensure user can use password reset

                    # Create password reset token for this user
                    reset_token = create_password_reset_token(user.id, session)
                    migration['reset_token'] = reset_token

            session.commit()

            print(f"\n[OK] Updated {len(migrations)} users - passwords reset to secure defaults")

            # Send password reset emails if email service is enabled
            if email_service.is_enabled():
                send_password_reset_emails(migrations, app_config)
            else:
                print("\n[KEY] PASSWORD RESET NOTIFICATION:")
                print("   All user passwords have been reset for security.")
                print("   Email service is not enabled - users must use the 'Forgot Password' feature manually.")
                print("   Alternatively, admins can manually reset passwords through the UI.")

            print("\n[WARNING]  Users MUST set new passwords using the password reset links!")

    except Exception as e:
        print(f"[ERROR] Error updating user accounts: {e}")
        sys.exit(1)

    return migrations


def main():
    parser = argparse.ArgumentParser(description='Migrate SysManage security configuration')
    parser.add_argument('--jwt-only', action='store_true', help='Only update JWT secret')
    parser.add_argument('--salt-only', action='store_true', help='Only update password salt')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without applying them')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')

    args = parser.parse_args()

    debug = args.debug

    print("[SECURITY] SysManage Security Configuration Migration")
    print("=" * 50)

    if debug:
        print(f"[DEBUG] DEBUG: Script arguments: {sys.argv}")
        print(f"[DEBUG] DEBUG: Parsed args: jwt_only={args.jwt_only}, salt_only={args.salt_only}, dry_run={args.dry_run}")
        print(f"[DEBUG] DEBUG: Running as user: {os.getenv('USER', 'unknown')}")
        print(f"[DEBUG] DEBUG: Effective UID: {os.getuid() if hasattr(os, 'getuid') else 'N/A'}")
        print(f"[DEBUG] DEBUG: Current working directory: {os.getcwd()}")

    # Get the config file path (respects /etc priority)
    config_path = get_config_file_path()
    print(f"[FILE] Using configuration file: {config_path}")

    if debug:
        print(f"[DEBUG] DEBUG: Config file exists: {os.path.exists(config_path)}")
        print(f"[DEBUG] DEBUG: Config file readable: {os.access(config_path, os.R_OK)}")
        print(f"[DEBUG] DEBUG: Config file writable: {os.access(config_path, os.W_OK)}")

    # Check if we need elevated privileges for non-dry-run operations
    needs_privileges = not args.dry_run and requires_elevated_privileges(config_path)
    if debug:
        print(f"[DEBUG] DEBUG: Needs elevated privileges: {needs_privileges}")

    if needs_privileges:
        print("[SECURITY] This configuration file requires administrative privileges to modify.")
        if debug:
            print(f"[DEBUG] DEBUG: About to re-run with privileges using args: {sys.argv[1:]}")
        run_with_privileges(sys.argv[1:])  # Re-run with same arguments
        # If we get here, privilege escalation failed, but run_with_privileges should exit
        if debug:
            print("[DEBUG] DEBUG: Privilege escalation returned unexpectedly")
        return

    if debug:
        print("[DEBUG] DEBUG: Proceeding with current privileges")

    # Load current configuration
    if debug:
        print(f"[DEBUG] DEBUG: Loading configuration from {config_path}")
    current_config = load_config_file(config_path)

    # Check current security values
    current_jwt = current_config.get('security', {}).get('jwt_secret', '')
    current_salt = current_config.get('security', {}).get('password_salt', '')

    if debug:
        print(f"[DEBUG] DEBUG: Current JWT secret: [REDACTED - {len(current_jwt)} chars]")
        print(f"[DEBUG] DEBUG: Current password salt: [REDACTED - {len(current_salt)} chars]")

    print(f"[INFO] Current JWT secret: {'DEFAULT' if current_jwt == 'I+Z74n/CFHser01E47pyrL91OuonEX9hNSvVFr/KLi4=' else 'CUSTOM'}")
    print(f"[INFO] Current password salt: {'DEFAULT' if current_salt == '6/InQvDb8f3cM6sao8kWzIiYVHKGH9sqkEJ3uZhIo9Q=' else 'CUSTOM'}")

    # Determine what to update
    update_jwt = not args.salt_only
    update_salt = not args.jwt_only

    if debug:
        print(f"[DEBUG] DEBUG: Will update JWT: {update_jwt}")
        print(f"[DEBUG] DEBUG: Will update salt: {update_salt}")

    new_config = current_config.copy()
    migrations_needed = []

    # Generate new JWT secret
    if update_jwt:
        new_jwt = generate_jwt_secret()
        new_config['security']['jwt_secret'] = new_jwt
        print(f"[KEY] New JWT secret generated: [REDACTED - {len(new_jwt)} chars]")
        if debug:
            print(f"[DEBUG] DEBUG: Full new JWT secret: [REDACTED - {len(new_jwt)} chars]")

    # Generate new password salt and handle user migration
    if update_salt:
        new_salt = generate_password_salt()
        new_config['security']['password_salt'] = new_salt
        print(f"🧂 New password salt generated: [REDACTED - {len(new_salt)} chars]")
        if debug:
            print(f"[DEBUG] DEBUG: Full new password salt: [REDACTED - {len(new_salt)} chars]")

        # Check for existing users and plan migration
        migrations_needed = migrate_user_passwords(current_salt, new_salt, dry_run=True)

    if args.dry_run:
        print("\n[INFO] DRY RUN - Changes that would be made:")
        print(f"   Configuration file: {config_path}")
        if update_jwt:
            print(f"   JWT secret: UPDATE")
        if update_salt:
            print(f"   Password salt: UPDATE")
            if migrations_needed:
                print(f"   User accounts: {len(migrations_needed)} would need password resets")
        return

    if debug:
        print("[DEBUG] DEBUG: About to create backup and save changes")

    # Create backup
    backup_path = backup_config_file(config_path, debug=debug)

    # Perform user migration if needed
    if update_salt and migrations_needed:
        if debug:
            print("[DEBUG] DEBUG: Performing user migration")
        migrate_user_passwords(current_salt, new_salt, dry_run=False)

    # Update configuration file
    if debug:
        print("[DEBUG] DEBUG: About to save updated configuration")
    save_config_file(config_path, new_config, debug=debug)

    print("\n[OK] Security migration completed successfully!")
    print("\n📋 Next steps:")
    print("   1. Restart the SysManage server: ./run.sh")
    if update_salt and migrations_needed:
        print("   2. Share temporary passwords with affected users (shown above)")
        print("   3. Ensure users change their temporary passwords immediately")
        print("   4. Monitor user login activity to confirm successful migration")
    print(f"   {'5' if update_salt and migrations_needed else '2'}. Backup available at: {backup_path}")
    print("\n[SECURITY] Your SysManage installation is now more secure!")


if __name__ == '__main__':
    main()