"""
User Access data handlers for SysManage agent communication.
Handles user accounts and groups update messages with Windows SID support.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host, UserAccount, UserGroup

# Logger for debugging - use existing root logger configuration
debug_logger = logging.getLogger("debug_logger")

# System usernames for classification
SYSTEM_USERNAMES = {
    "root",
    "daemon",
    "bin",
    "sys",
    "sync",
    "games",
    "man",
    "lp",
    "mail",
    "news",
    "uucp",
    "proxy",
    "www-data",
    "backup",
    "list",
    "irc",
    "gnats",
    "nobody",
    "systemd-network",
    "systemd-resolve",
    "syslog",
    "messagebus",
    "uuidd",
    "dnsmasq",
    "landscape",
    "pollinate",
    "sshd",
    "chrony",
    # Windows system accounts
    "system",
    "local service",
    "network service",
    "administrator",
    # macOS system accounts (starting with _)
    "_www",
    "_taskgated",
    "_networkd",
    "_installassistant",
    "_lp",
    "_postfix",
    "_scsd",
    "_ces",
    "_mcxalr",
    "_appleevents",
    "_geod",
    "_devdocs",
    "_sandbox",
    "_mdnsresponder",
    "_ard",
    "_eppc",
    "_cvs",
    "_svn",
    "_mysql",
    "_pgsql",
    "_krb_krbtgt",
    "_krb_kadmin",
    "_krb_changepw",
    "_devicemgr",
    "_spotlight",
}


def _create_user_account_with_security_id(connection, account, now):  # NOSONAR
    """Create a UserAccount with proper Windows SID handling."""
    uid = account.get("uid", 0)
    username = account.get("username", "")

    # Initialize values
    is_system_user = False
    uid_value = None
    security_id_value = None
    shell_value = account.get("shell")

    if uid is not None and uid != "":
        # Handle both integer UIDs (Unix) and string SIDs (Windows)
        try:
            # Try to convert to integer (Unix UID)
            uid_int = int(uid)
            uid_value = uid_int
            debug_logger.info("DEBUG: User %s - Unix UID: %s", username, uid_int)

            # macOS: UIDs < 500 are typically system users
            # Linux: UIDs < 1000 are typically system users
            if uid_int < 500:
                is_system_user = True

        except (ValueError, TypeError):
            # This is a Windows SID (string)
            security_id_value = str(uid)
            debug_logger.info(
                "DEBUG: User %s - Windows SID: %s", username, security_id_value
            )

            # Windows system account classification by SID pattern
            if security_id_value.startswith("S-1-5-"):
                try:
                    # Check RID (last part of SID) - system accounts typically have RIDs < 1000
                    rid = int(security_id_value.split("-")[-1])
                    if rid < 1000:
                        is_system_user = True
                except (ValueError, IndexError):
                    pass

    # Also check for common system usernames
    system_usernames = {
        "root",
        "daemon",
        "bin",
        "sys",
        "sync",
        "games",
        "man",
        "lp",
        "mail",
        "news",
        "uucp",
        "proxy",
        "www-data",
        "backup",
        "list",
        "irc",
        "gnats",
        "nobody",
        "systemd-network",
        "systemd-resolve",
        "syslog",
        "messagebus",
        "uuidd",
        "dnsmasq",
        "landscape",
        "pollinate",
        "sshd",
        "chrony",
        # Windows system accounts
        "system",
        "local service",
        "network service",
        "administrator",
        # macOS system accounts (starting with _)
        "_www",
        "_taskgated",
        "_networkd",
        "_installassistant",
        "_lp",
        "_postfix",
        "_scsd",
        "_ces",
        "_mcxalr",
        "_appleevents",
        "_geod",
        "_devdocs",
        "_sandbox",
        "_mdnsresponder",
        "_ard",
        "_eppc",
        "_cvs",
        "_svn",
        "_mysql",
        "_pgsql",
        "_krb_krbtgt",
        "_krb_kadmin",
        "_krb_changepw",
        "_devicemgr",
        "_spotlight",
    }
    if username.lower() in system_usernames:
        is_system_user = True

    return UserAccount(
        host_id=connection.host_id,
        username=username,
        uid=uid_value,  # Integer UID for Unix systems, None for Windows
        security_id=security_id_value,  # Windows SID string, None for Unix
        home_directory=account.get("home_directory"),
        shell=shell_value,  # nosec B604 - Database field assignment, not shell execution
        is_system_user=is_system_user,
        created_at=now,
        updated_at=now,
    )


def _create_user_group_with_security_id(connection, group, now):
    """Create a UserGroup with proper Windows SID handling."""
    gid = group.get("gid")
    group_name = group.get("group_name")

    # Initialize values
    is_system_group = group.get("is_system_group", False)
    gid_value = None
    security_id_value = None

    debug_logger.info(
        "DEBUG: Processing group %s with gid: %s (type: %s)", group_name, gid, type(gid)
    )

    if gid is not None:
        try:
            # Try to convert to integer (Unix GID)
            gid_int = int(gid)
            gid_value = gid_int
            debug_logger.info("DEBUG: Group %s - Unix GID: %s", group_name, gid_int)

        except (ValueError, TypeError):
            # This is a Windows SID (string)
            if isinstance(gid, str) and gid.startswith("S-1-"):
                security_id_value = str(gid)
                debug_logger.info(
                    "DEBUG: Group %s - Windows SID: %s", group_name, security_id_value
                )
            else:
                debug_logger.info(
                    "DEBUG: Group %s - unknown gid format, storing as None", group_name
                )
    else:
        debug_logger.info("DEBUG: Group %s - no gid provided", group_name)

    return UserGroup(
        host_id=connection.host_id,
        group_name=group_name,
        gid=gid_value,  # Integer GID for Unix systems, None for Windows
        security_id=security_id_value,  # Windows SID string, None for Unix
        is_system_group=is_system_group,
        created_at=now,
        updated_at=now,
    )


async def handle_user_access_update(db: Session, connection, message_data: dict):
    """Handle user access information update message from agent with Windows SID support."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": _("Host not registered"),
            "data": {},
        }

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": _("Host not registered"),
            "data": {},
        }

    try:
        # Handle user accounts
        user_accounts = message_data.get("user_accounts", [])
        if not user_accounts:
            user_accounts = message_data.get("users", [])

        if user_accounts:
            debug_logger.info("Found %d users under 'users' key", len(user_accounts))

            # Delete existing user accounts for this host
            db.execute(
                delete(UserAccount).where(UserAccount.host_id == connection.host_id)
            )

            # Add new user accounts with security_id support
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for account in user_accounts:
                user_account = _create_user_account_with_security_id(
                    connection, account, now
                )
                db.add(user_account)

        # Handle user groups
        user_groups = message_data.get("user_groups", [])
        if not user_groups:
            user_groups = message_data.get("groups", [])

        if user_groups:
            debug_logger.info("Found %d groups under 'groups' key", len(user_groups))

            # Delete existing user groups for this host
            db.execute(delete(UserGroup).where(UserGroup.host_id == connection.host_id))

            # Add new user groups with security_id support
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for group in user_groups:
                user_group = _create_user_group_with_security_id(connection, group, now)
                db.add(user_group)

        # Commit the transaction
        db.commit()
        debug_logger.info(
            "Successfully processed user access update with security_id support"
        )

        return {
            "message_type": "success",
            "result": "user_access_updated",
        }

    except Exception as e:
        import traceback

        debug_logger.error("Error updating user access: %s", e)
        debug_logger.error("Full traceback: %s", traceback.format_exc())
        db.rollback()
        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": _("Failed to update user access information"),
            "data": {},
        }
