# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Logging-configuration resolution + delivery (Phase 13.3).

Central helpers for the DB-stored logging settings:

* map an OS string to a family + list its valid native targets,
* resolve the EFFECTIVE config (DB row wins over the yaml file),
* (re)apply the server's own native log handler at runtime,
* push the resolved per-OS config to agents over the durable queue.

DB-over-yaml: a stored ``logging_setting`` row always wins; when absent the
yaml value (or a sane default) is used.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence.models import Host, LoggingSetting
from backend.persistence.models.logging_config import (
    OS_FAMILIES,
    SCOPE_AGENT,
    SCOPE_SERVER,
)
from backend.utils.native_logging import build_native_handler

logger = logging.getLogger(__name__)

# Native targets that make sense per OS family (drives the UI + validation).
# ``syslog_remote`` is network-based so it's offered on every family (incl.
# Windows); the API/UI gate it behind the Professional LOG_ROUTING feature.
_VALID_TARGETS: Dict[str, List[str]] = {
    "linux": ["auto", "journald", "syslog", "syslog_remote", "none"],
    "windows": ["auto", "eventlog", "syslog_remote", "none"],
    "macos": ["auto", "syslog", "syslog_remote", "none"],
    "bsd": ["auto", "syslog", "syslog_remote", "none"],
}


def os_family_for_system(system: Optional[str]) -> str:
    """Map a platform string (``platform.system()`` / Host.platform) to a family."""
    value = (system or "").strip().lower()
    if "windows" in value:
        return "windows"
    if "darwin" in value or "mac" in value:
        return "macos"
    if any(b in value for b in ("freebsd", "openbsd", "netbsd", "dragonfly", "bsd")):
        return "bsd"
    return "linux"  # default / Linux


def valid_targets_for_family(family: str) -> List[str]:
    """Native log targets valid for an OS family."""
    return _VALID_TARGETS.get(family, ["auto", "syslog", "syslog_remote", "none"])


def get_setting(
    db: Session, scope: str, os_family: Optional[str] = None
) -> Optional[LoggingSetting]:
    """Fetch a logging_setting row by scope (+ os_family for agents)."""
    query = db.query(LoggingSetting).filter(LoggingSetting.scope == scope)
    if scope == SCOPE_AGENT:
        query = query.filter(LoggingSetting.os_family == os_family)
    else:
        query = query.filter(LoggingSetting.os_family.is_(None))
    return query.first()


def resolve_server_logging(db: Session, yaml_logging: Optional[dict] = None) -> dict:
    """Effective server logging config: DB row wins over the yaml ``logging``."""
    yaml_logging = yaml_logging or {}
    row = get_setting(db, SCOPE_SERVER)
    if row is not None:
        return row.to_dict()
    return {
        "scope": SCOPE_SERVER,
        "os_family": None,
        "native_enabled": bool(yaml_logging.get("native", False)),
        "native_target": yaml_logging.get("native_target", "auto"),
        "native_identifier": yaml_logging.get("native_identifier", "sysmanage"),
        "log_level": yaml_logging.get("level"),
        "verbosity": yaml_logging.get("verbosity"),
        "syslog_host": yaml_logging.get("syslog_host"),
        "syslog_port": yaml_logging.get("syslog_port"),
        "syslog_facility": yaml_logging.get("syslog_facility"),
        "syslog_protocol": yaml_logging.get("syslog_protocol"),
    }


def resolve_agent_logging(db: Session, os_family: str) -> Optional[dict]:
    """The stored default config for an agent OS family, or None if unset.

    None means "no server override" — the agent keeps using its own yaml.
    """
    row = get_setting(db, SCOPE_AGENT, os_family)
    return row.to_dict() if row is not None else None


def upsert_setting(
    db: Session, scope: str, os_family: Optional[str], values: dict
) -> LoggingSetting:
    """Create or update a logging_setting row (caller commits)."""
    row = get_setting(db, scope, os_family)
    if row is None:
        row = LoggingSetting(scope=scope, os_family=os_family)
        db.add(row)
    row.native_enabled = bool(values.get("native_enabled", False))
    row.native_target = values.get("native_target", "auto") or "auto"
    row.native_identifier = values.get("native_identifier") or None
    row.log_level = values.get("log_level") or None
    row.verbosity = values.get("verbosity") or None
    row.syslog_host = values.get("syslog_host") or None
    row.syslog_port = values.get("syslog_port") or None
    row.syslog_facility = values.get("syslog_facility") or None
    row.syslog_protocol = values.get("syslog_protocol") or None
    return row


def delete_agent_setting(db: Session, os_family: str) -> bool:
    """Delete an agent OS family's stored row so it reverts to its yaml.

    Returns True if a row existed and was removed (caller commits).  Turning an
    OS's "override" off in the UI omits it from the save payload; removing the
    row is what makes that OS's agents fall back to their own yaml.
    """
    row = get_setting(db, SCOPE_AGENT, os_family)
    if row is None:
        return False
    db.delete(row)
    return True


def apply_server_native_logging(resolved: dict) -> None:
    """(Re)configure the server's own OS-native log handler from a resolved dict.

    Removes any previously-attached native handler, then adds a fresh one when
    enabled — so a UI change applied at runtime takes effect without a restart.
    """
    root = logging.getLogger()
    # Snapshot the matching handlers first so we can safely removeHandler()
    # while iterating (mutating root.handlers mid-loop otherwise skips entries).
    native_handlers = [
        handler
        for handler in root.handlers
        if getattr(handler, "_sysmanage_native", False)
    ]
    for handler in native_handlers:
        handler.close()
        root.removeHandler(handler)

    if not resolved.get("native_enabled"):
        return

    handler = build_native_handler(
        target=resolved.get("native_target", "auto"),
        identifier=resolved.get("native_identifier") or "sysmanage",
        host=resolved.get("syslog_host"),
        port=resolved.get("syslog_port"),
        facility=resolved.get("syslog_facility"),
        protocol=resolved.get("syslog_protocol"),
    )
    if handler is not None:
        handler._sysmanage_native = True  # pylint: disable=protected-access
        root.addHandler(handler)
        logger.info("Applied DB server native log handler: %s", type(handler).__name__)


def _agent_payload(resolved: dict) -> dict:
    """Trim a resolved row to the fields the agent needs."""
    return {
        "native_enabled": resolved.get("native_enabled", False),
        "native_target": resolved.get("native_target", "auto"),
        "native_identifier": resolved.get("native_identifier"),
        "log_level": resolved.get("log_level"),
        "verbosity": resolved.get("verbosity"),
        "syslog_host": resolved.get("syslog_host"),
        "syslog_port": resolved.get("syslog_port"),
        "syslog_facility": resolved.get("syslog_facility"),
        "syslog_protocol": resolved.get("syslog_protocol"),
    }


def _main_session():
    """A session bound to the bootstrap/main engine (where settings live)."""
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence import db as db_module  # noqa: PLC0415

    return sessionmaker(bind=db_module.get_engine())()


def push_logging_to_host(db: Session, host: Host) -> bool:
    """Enqueue the resolved logging config for one host (used on connect).

    ``db`` is the host's (partition-routed) session for the queue write; the
    server-global settings are read from the main engine.  Returns True if a
    config was enqueued (a server default exists for the host's OS family).
    """
    # Never push to an unapproved host — its outbound queue is rejected, and a
    # stale/pending duplicate (e.g. a leftover bootstrap row) must not swallow
    # the config meant for the real, approved host.
    if getattr(host, "approval_status", None) != "approved":
        return False
    family = os_family_for_system(getattr(host, "platform", None))
    main = _main_session()
    try:
        resolved = resolve_agent_logging(main, family)
    finally:
        main.close()
    if resolved is None:
        return False
    _enqueue_logging_update(db, str(host.id), resolved)
    # enqueue_message only FLUSHES a caller-provided session — the commit is the
    # caller's job.  The system_info handler that invokes us does not commit
    # afterward, so own the commit here (as push_logging_to_all_agents does) or
    # the queued config is silently rolled back when the session closes.
    try:
        db.commit()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception(
            "Failed to commit on-connect logging push for host %s", host.id
        )
        db.rollback()
        return False
    return True


def push_logging_to_all_agents(revert_families=None) -> int:
    """Enqueue resolved logging config to every active host across all partitions.

    Settings (server-global) are read once from the main engine; hosts are
    iterated across the bootstrap DB and every tenant DB so the push reaches the
    whole fleet whether or not multi-tenancy is enabled.  Returns the count.

    ``revert_families`` is the set of OS families whose stored row was just
    removed (their UI override was turned off): agents of those OSes are sent an
    empty override so they fall back to their own yaml live, without a restart.
    """
    revert = set(revert_families or ())
    main = _main_session()
    try:
        by_family = {f: resolve_agent_logging(main, f) for f in OS_FAMILIES}
    finally:
        main.close()
    if not any(by_family.values()) and not revert:
        return 0

    from backend.persistence.partitions import iter_host_databases  # noqa: PLC0415

    count = 0
    for _label, _tenant_id, session in iter_host_databases():
        try:
            approved_hosts = (
                session.query(Host)
                .filter(Host.active.is_(True), Host.approval_status == "approved")
                .all()
            )
            for host in approved_hosts:
                family = os_family_for_system(getattr(host, "platform", None))
                resolved = by_family.get(family)
                if resolved is not None:
                    _enqueue_logging_update(session, str(host.id), resolved)
                    count += 1
                elif family in revert:
                    # Override just removed → revert this agent to its yaml.
                    _enqueue_logging_update(session, str(host.id), None)
                    count += 1
            session.commit()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("Logging push failed for a host partition: %s", exc)
            session.rollback()
        finally:
            session.close()
    return count


def _enqueue_logging_update(db: Session, host_id: str, resolved) -> None:
    """Persist one OUTBOUND ``logging_config_update`` message for a host.

    ``resolved`` is the resolved config dict, or ``None`` to send an empty
    override (``{}``) — the agent treats that as "revert to yaml".
    """
    # Imported lazily to avoid a heavy import at module load.
    from backend.websocket.messages import (  # noqa: PLC0415
        Message,
        MessageType,
    )
    from backend.websocket.queue_enums import QueueDirection  # noqa: PLC0415
    from backend.websocket.queue_operations import QueueOperations  # noqa: PLC0415

    payload = _agent_payload(resolved) if resolved is not None else {}
    message = Message(
        message_type=MessageType.LOGGING_CONFIG_UPDATE.value,
        data={"logging": payload},
    )
    QueueOperations().enqueue_message(
        message_type=MessageType.LOGGING_CONFIG_UPDATE.value,
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=db,
    )
