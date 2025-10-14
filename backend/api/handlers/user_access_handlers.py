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
debug_logger.setLevel(logging.DEBUG)

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


def _create_user_account_with_security_id(connection, account, now):
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
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

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
            "error": "Failed to update user access information",
        }


async def handle_user_access_update_legacy(db: Session, connection, message_data: dict):
    """Handle user access information update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Debug: log what keys we're receiving
        debug_logger.info("User access message keys: %s", list(message_data.keys()))

        # Handle user accounts - try both possible field names
        user_accounts = message_data.get("user_accounts", [])
        if not user_accounts:
            # Try alternate field name the agent might be using
            user_accounts = message_data.get("users", [])
            if user_accounts:
                debug_logger.info(
                    "Found %d users under 'users' key", len(user_accounts)
                )
        if user_accounts:
            # Delete existing user accounts for this host
            db.execute(
                delete(UserAccount).where(UserAccount.host_id == connection.host_id)
            )

            # Add new user accounts
            for account in user_accounts:
                now = datetime.now(timezone.utc).replace(tzinfo=None)

                # Determine if this is a system user based on UID and username
                uid = account.get("uid", 0)
                username = account.get("username", "")

                # System user detection logic
                is_system_user = False
                if uid is not None and uid != "":
                    # Handle both integer UIDs (Unix) and string SIDs (Windows)
                    try:
                        # Ensure uid is not a string before comparison
                        uid_int = int(uid)
                        debug_logger.info(
                            "DEBUG: Successfully converted uid %s to int %s (type: %s)",
                            uid,
                            uid_int,
                            type(uid_int),
                        )
                        # macOS: UIDs < 500 are typically system users
                        # Linux: UIDs < 1000 are typically system users
                        # Force reload trigger
                        if isinstance(uid_int, int) and uid_int < 500:
                            is_system_user = True
                    except (ValueError, TypeError) as e:
                        # For Windows SIDs (strings), use different logic
                        # Windows system accounts typically have well-known SIDs
                        debug_logger.info(
                            "DEBUG: Failed to convert uid %s to int: %s (type: %s)",
                            uid,
                            e,
                            type(uid),
                        )
                        uid_str = str(uid)
                        # Windows system account classification by SID pattern
                        if uid_str.startswith("S-1-5-"):
                            # Check RID (last part of SID) - system accounts typically have RIDs < 1000
                            try:
                                rid = int(uid_str.split("-")[-1])
                                if isinstance(rid, int) and rid < 1000:
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
                    "_windowserver",
                    "_securityagent",
                    "_calendar",
                    "_teamsserver",
                    "_update_sharing",
                    "_appstore",
                    "_lpd",
                    "_postdrop",
                    "_qtss",
                    "_coreaudiod",
                    "_screensaver",
                    "_locationd",
                    "_trustevaluationagent",
                    "_timezone",
                    "_cvmsroot",
                    "_usbmuxd",
                    "_dovecot",
                    "_dpaudio",
                    "_postgres",
                    "_krbtgt",
                    "_kadmin_admin",
                    "_kadmin_changepw",
                }

                if username in system_usernames or username.startswith("_"):
                    is_system_user = True

                # Handle uid field - only store integers, Windows SIDs in shell field
                # Fixed: Type error when comparing string SIDs with integer column
                uid_value = None
                shell_value = account.get("shell")  # Default shell value

                # DEBUG: Log what we received
                debug_logger.info(
                    "DEBUG: User %s - uid received: %s (type: %s)",
                    username,
                    uid,
                    type(uid),
                )

                if uid is not None:
                    try:
                        uid_value = int(uid)
                        debug_logger.info(
                            "DEBUG: User %s - converted to integer UID: %s",
                            username,
                            uid_value,
                        )
                    except (ValueError, TypeError):
                        # Windows SIDs are strings, store in shell field for later retrieval
                        # since shell field is unused for Windows and can hold string data
                        uid_value = None
                        shell_value = str(uid)  # Store Windows SID in shell field
                        debug_logger.info(
                            "DEBUG: User %s - storing SID in shell field: %s",
                            username,
                            shell_value,
                        )
                else:
                    debug_logger.info("DEBUG: User %s - uid is None/empty", username)

                user_account = UserAccount(
                    host_id=connection.host_id,
                    username=username,
                    uid=uid_value,
                    home_directory=account.get("home_directory"),
                    shell=shell_value,  # nosec B604 - May contain Windows SID
                    is_system_user=is_system_user,  # Set proper classification
                    created_at=now,
                    updated_at=now,
                )
                db.add(user_account)

        # Handle user groups - try both possible field names
        user_groups = message_data.get("user_groups", [])
        if not user_groups:
            # Try alternate field name the agent might be using
            user_groups = message_data.get("groups", [])
            if user_groups:
                debug_logger.info(
                    "Found %d groups under 'groups' key", len(user_groups)
                )
        if user_groups:
            # Delete existing user groups for this host
            db.execute(delete(UserGroup).where(UserGroup.host_id == connection.host_id))

            # Add new user groups
            for group in user_groups:
                now = datetime.now(timezone.utc).replace(tzinfo=None)

                # Handle gid field - store integers for Unix, for Windows store a hash of the SID
                gid_value = None
                gid = group.get("gid")
                debug_logger.info(
                    "DEBUG: Processing group %s with gid: %s (type: %s)",
                    group.get("group_name"),
                    gid,
                    type(gid),
                )

                if gid is not None:
                    try:
                        gid_value = int(gid)
                        debug_logger.info(
                            "DEBUG: Group %s - stored integer GID: %s",
                            group.get("group_name"),
                            gid_value,
                        )
                    except (ValueError, TypeError):
                        # For Windows SIDs, create a numeric hash to store in the integer gid field
                        # This allows us to distinguish between groups while maintaining schema compatibility
                        if isinstance(gid, str) and gid.startswith("S-1-"):
                            # Create a consistent hash of the SID that fits in integer range
                            import hashlib

                            hash_object = hashlib.md5(
                                gid.encode(), usedforsecurity=False
                            )  # nosec B324
                            # Convert to positive integer within reasonable range
                            gid_value = int(hash_object.hexdigest()[:8], 16)
                            debug_logger.info(
                                "DEBUG: Group %s - Windows SID %s hashed to GID: %s",
                                group.get("group_name"),
                                gid,
                                gid_value,
                            )
                        else:
                            gid_value = None
                            debug_logger.info(
                                "DEBUG: Group %s - unknown gid format, storing as None",
                                group.get("group_name"),
                            )
                else:
                    debug_logger.info(
                        "DEBUG: Group %s - no gid provided", group.get("group_name")
                    )

                user_group = UserGroup(
                    host_id=connection.host_id,
                    group_name=group.get("group_name"),
                    gid=gid_value,
                    is_system_group=group.get("is_system_group", False),
                    # Note: members field doesn't exist in UserGroup model - removed
                    # (use UserGroupMembership table for members relationships)
                    created_at=now,
                    updated_at=now,
                )
                db.add(user_group)

        # Update the user access timestamp on the host
        stmt = (
            update(Host)
            .where(Host.id == connection.host_id)
            .values(user_access_updated_at=datetime.now(timezone.utc))
        )
        db.execute(stmt)

        db.commit()

        debug_logger.info("User access updated for host %s", connection.host_id)

        return {
            "message_type": "success",
            "result": _("user_access_updated"),
        }

    except Exception as e:
        import traceback

        debug_logger.error("Error updating user access: %s", e)
        debug_logger.error("Full traceback: %s", traceback.format_exc())
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to update user access information"),
        }
