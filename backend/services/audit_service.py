# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Audit logging service for SysManage.

This service provides functionality to log all user actions and system changes
for compliance, security, and troubleshooting purposes.

WHERE AN ENTRY IS WRITTEN (multi-tenancy, 2026-10-16)
-----------------------------------------------------
Audit rows are PER TENANT.  An event about a tenant's hosts, packages,
scripts, secrets, firewalls, antivirus, maintenance windows ... belongs in
that tenant's database, so the tenant's own audit view shows it and no other
tenant's does.  Events about server-global state -- logins and password
resets, users, security roles, tenants themselves, server settings -- belong
in the bootstrap database, where that state lives (``SERVER_SCOPED_*``).

Callers used to pick the session themselves and many picked the main engine,
so a tenant's actions were split across two databases (production: 24 rows in
each).  ``log`` now routes:

* a server-scoped event goes to the bootstrap database;
* a tenant-scoped event handed a BOOTSTRAP session while a tenant is active
  goes to that tenant's database;
* a session already bound to a tenant database is never moved -- background
  ticks iterate tenant databases without binding the active tenant, and the
  session they pass is the right answer.

Single-tenant / collapsed deployments are untouched: every engine is the
bootstrap engine there.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.i18n import _
from backend.persistence.models import AuditLog


class ActionType(str, Enum):
    """Enumeration of audit log action types"""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    EXECUTE = "EXECUTE"
    AGENT_MESSAGE = "AGENT_MESSAGE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    LOGIN_FAILED = "LOGIN_FAILED"
    PASSWORD_RESET = (
        "PASSWORD_RESET"  # nosec B105  # This is an enum value, not a password
    )
    PERMISSION_CHANGE = "PERMISSION_CHANGE"


class EntityType(str, Enum):
    """Enumeration of entity types that can be audited"""

    HOST = "host"
    AGENT = "agent"
    USER = "user"
    PACKAGE = "package"
    SCRIPT = "script"
    SECRET = "secret"  # nosec B105  # This is an enum value, not a password
    TAG = "tag"
    ROLE = "role"
    REPOSITORY = "repository"
    CERTIFICATE = "certificate"
    FIREWALL = "firewall"
    ANTIVIRUS = "antivirus"
    UPDATE = "update"
    SETTING = "setting"
    SECURITY_ROLE = "security_role"
    AUTHENTICATION = "authentication"
    TENANT = "tenant"
    MAINTENANCE_WINDOW = "maintenance_window"
    POSTURE_WAIVER = "posture_waiver"
    DISCOVERED_ASSET = "discovered_asset"
    NETWORK_SWEEP = "network_sweep"
    MALWARE_SCAN = "malware_scan"
    MALWARE_FINDING = "malware_finding"
    MALWARE_RULESET = "malware_ruleset"


class Result(str, Enum):
    """Enumeration of audit log result statuses"""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PENDING = "PENDING"


# Server-global state: always audited in the bootstrap database (see above).
SERVER_SCOPED_ACTIONS = frozenset(
    {
        "LOGIN",
        "LOGOUT",
        "LOGIN_FAILED",
        "PASSWORD_RESET",
    }
)
SERVER_SCOPED_ENTITIES = frozenset(
    {
        "user",
        "security_role",
        "authentication",
        "tenant",
        "setting",
    }
)


def _bind_of(db) -> Optional[Engine]:
    """The engine ``db`` is bound to, or None for anything else (test doubles)."""
    try:
        bind = db.get_bind()
    except Exception:  # pylint: disable=broad-except
        return None
    return bind if isinstance(bind, Engine) else None


def _target_engine(db, action_type: str, entity_type: str) -> Optional[Engine]:
    """The engine this entry must be written to when it is NOT ``db``'s own,
    else None (write to ``db``).  The rule is in the module docstring."""
    # Imported here: config and partitions import the models this module does.
    from backend.config import config  # noqa: PLC0415
    from backend.persistence import db as db_module  # noqa: PLC0415

    if not config.is_multitenancy_enabled():
        return None
    bind = _bind_of(db)
    if bind is None:
        return None
    bootstrap = db_module.get_engine()
    if action_type in SERVER_SCOPED_ACTIONS or entity_type in SERVER_SCOPED_ENTITIES:
        return None if bind is bootstrap else bootstrap
    if bind is not bootstrap:
        return None  # already a tenant database: never second-guessed
    from backend.persistence.partitions import (  # noqa: PLC0415
        get_request_engine,
    )

    target = get_request_engine()
    return None if target is bootstrap else target


class AuditService:
    """
    Service for managing audit logs.

    This service provides methods to create and query audit log entries
    for tracking user actions and system changes.
    """

    @staticmethod
    def log(
        db: Session,
        action_type: ActionType,
        entity_type: EntityType,
        description: str,
        result: Result = Result.SUCCESS,
        user_id: Optional[uuid.UUID] = None,
        username: Optional[str] = None,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        commit: bool = True,
        **kwargs,
    ) -> AuditLog:
        """
        Create an audit log entry.

        ``commit=False`` only adds it to ``db``: a caller logging many entries
        (a fleet-wide push, Phase 22.3) commits once for all of them.

        Args:
            db: Database session
            action_type: Type of action performed
            entity_type: Type of entity affected
            description: Human-readable description of the action
            result: Result status of the action
            user_id: ID of the user who performed the action (optional for system actions)
            username: Username for historical record (optional)
            entity_id: ID of the affected entity (optional)
            entity_name: Name of the affected entity for display (optional)
            details: Additional structured data about the action (optional)
            ip_address: IP address of the client (optional)
            error_message: Error details if action failed (optional)
            **kwargs: Additional fields (ip_address, error_message,
                user_agent, category, entry_type)

        Returns:
            The created AuditLog entry
        """
        entry_id = uuid.uuid4()
        entry_timestamp = datetime.now(timezone.utc).replace(tzinfo=None)

        # Compute integrity hash for tamper-evident logging
        hash_parts = [
            str(entry_id),
            str(entry_timestamp),
            str(user_id),
            str(action_type.value),
            str(entity_type.value),
            str(entity_id),
            str(description),
            str(result.value),
        ]
        integrity_hash = hashlib.sha256("|".join(hash_parts).encode()).hexdigest()

        audit_entry = AuditLog(
            id=entry_id,
            timestamp=entry_timestamp,
            user_id=user_id,
            username=username,
            action_type=action_type.value,
            entity_type=entity_type.value,
            entity_id=entity_id,
            entity_name=entity_name,
            description=description,
            details=details,
            ip_address=kwargs.get("ip_address"),
            user_agent=kwargs.get("user_agent"),
            result=result.value,
            error_message=kwargs.get("error_message"),
            category=kwargs.get("category"),
            entry_type=kwargs.get("entry_type"),
            integrity_hash=integrity_hash,
        )

        target = _target_engine(db, action_type.value, entity_type.value)
        if target is not None:
            # Written on its own session and committed now: it belongs to a
            # different database than the caller's transaction.
            with sessionmaker(autocommit=False, autoflush=False, bind=target)() as own:
                own.add(audit_entry)
                own.commit()
                own.refresh(audit_entry)
                own.expunge(audit_entry)
            return audit_entry

        db.add(audit_entry)
        if commit:
            db.commit()
            db.refresh(audit_entry)

        return audit_entry

    @staticmethod
    def log_create(
        db: Session,
        entity_type: EntityType,
        entity_name: str,
        user_id: Optional[uuid.UUID] = None,
        username: Optional[str] = None,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Log a CREATE action.

        Args:
            db: Database session
            entity_type: Type of entity created
            entity_name: Name of the created entity
            user_id: ID of the user who created the entity
            username: Username for historical record
            entity_id: ID of the created entity
            details: Additional details about the creation
            ip_address: IP address of the client
            user_agent: Browser/client user agent string

        Returns:
            The created AuditLog entry
        """
        description = _("Created {entity_type} '{entity_name}'").format(
            entity_type=entity_type.value, entity_name=entity_name
        )

        return AuditService.log(
            db=db,
            action_type=ActionType.CREATE,
            entity_type=entity_type,
            description=description,
            result=Result.SUCCESS,
            user_id=user_id,
            username=username,
            entity_id=entity_id,
            entity_name=entity_name,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @staticmethod
    def log_update(
        db: Session,
        entity_type: EntityType,
        entity_name: str,
        user_id: Optional[uuid.UUID] = None,
        username: Optional[str] = None,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Log an UPDATE action.

        Args:
            db: Database session
            entity_type: Type of entity updated
            entity_name: Name of the updated entity
            user_id: ID of the user who updated the entity
            username: Username for historical record
            entity_id: ID of the updated entity
            details: Additional details about the update (old/new values)
            ip_address: IP address of the client
            user_agent: Browser/client user agent string

        Returns:
            The created AuditLog entry
        """
        description = _("Updated {entity_type} '{entity_name}'").format(
            entity_type=entity_type.value, entity_name=entity_name
        )

        return AuditService.log(
            db=db,
            action_type=ActionType.UPDATE,
            entity_type=entity_type,
            description=description,
            result=Result.SUCCESS,
            user_id=user_id,
            username=username,
            entity_id=entity_id,
            entity_name=entity_name,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @staticmethod
    def log_delete(
        db: Session,
        entity_type: EntityType,
        entity_name: str,
        user_id: Optional[uuid.UUID] = None,
        username: Optional[str] = None,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Log a DELETE action.

        Args:
            db: Database session
            entity_type: Type of entity deleted
            entity_name: Name of the deleted entity
            user_id: ID of the user who deleted the entity
            username: Username for historical record
            entity_id: ID of the deleted entity
            details: Additional details about the deletion
            ip_address: IP address of the client
            user_agent: Browser/client user agent string

        Returns:
            The created AuditLog entry
        """
        description = _("Deleted {entity_type} '{entity_name}'").format(
            entity_type=entity_type.value, entity_name=entity_name
        )

        return AuditService.log(
            db=db,
            action_type=ActionType.DELETE,
            entity_type=entity_type,
            description=description,
            result=Result.SUCCESS,
            user_id=user_id,
            username=username,
            entity_id=entity_id,
            entity_name=entity_name,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @staticmethod
    def log_agent_message(
        db: Session,
        host_name: str,
        message_type: str,
        description: str,
        user_id: Optional[uuid.UUID] = None,
        username: Optional[str] = None,
        host_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        result: Result = Result.SUCCESS,
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """
        Log an agent message that will cause a change on a remote host.

        Args:
            db: Database session
            host_name: Name of the host receiving the message
            message_type: Type of message being sent
            description: Human-readable description of the action
            user_id: ID of the user who initiated the message
            username: Username for historical record
            host_id: ID of the host
            details: Additional details about the message
            ip_address: IP address of the client
            user_agent: Browser/client user agent string
            result: Result status of the action
            error_message: Error details if action failed

        Returns:
            The created AuditLog entry
        """
        # Add message type to details
        if details is None:
            details = {}
        details["message_type"] = message_type

        return AuditService.log(
            db=db,
            action_type=ActionType.AGENT_MESSAGE,
            entity_type=EntityType.HOST,
            description=description,
            result=result,
            user_id=user_id,
            username=username,
            entity_id=host_id,
            entity_name=host_name,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            error_message=error_message,
        )
