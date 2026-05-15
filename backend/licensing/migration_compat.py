"""
Migration compatibility check for Pro+ modules.

Each Pro+ module may declare ``min_oss_alembic_revision`` in its
``get_module_info()``.  At module-load time the OSS server compares this
against the current ``alembic_version`` row.  If migrations are stale, the
module is unloaded and recorded in the registry below so the UI can
display a banner instructing the operator to run ``alembic upgrade head``.

The check is a fallback: the normal path is for the operator to run
migrations as part of their upgrade procedure.  This catches the case where
a Pro+ module is downloaded after an OSS upgrade but before migrations have
been applied — without it, the module would load against a stale schema
and fail in subtle ways (missing columns, missing tables, etc.).
"""

from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.licensing.migration_compat")


@dataclass
class ModuleIncompatibility:
    """One module's failed compatibility check."""

    module_code: str
    required_revision: str
    required_revision_human: Optional[str]
    current_revision: Optional[str]


class _Registry:
    """In-memory registry of incompatible Pro+ modules."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._entries: Dict[str, ModuleIncompatibility] = {}

    def record(self, entry: ModuleIncompatibility) -> None:
        with self._lock:
            self._entries[entry.module_code] = entry

    def clear(self, module_code: str) -> None:
        with self._lock:
            self._entries.pop(module_code, None)

    def all(self) -> List[ModuleIncompatibility]:
        with self._lock:
            return list(self._entries.values())


_registry = _Registry()


def get_incompatibilities() -> List[ModuleIncompatibility]:
    """Return the current list of modules that failed the compatibility check."""
    return _registry.all()


def clear_incompatibility(module_code: str) -> None:
    """Remove a module from the incompatibility registry (e.g. after a successful re-load)."""
    _registry.clear(module_code)


def get_current_oss_revision(session: Session) -> Optional[str]:
    """Read the current alembic head from the alembic_version table.

    Returns None if the table doesn't exist or is empty (i.e. fresh DB).
    Multiple heads (merge-pending state) returns the first deterministically;
    callers should treat that as "indeterminate" but it shouldn't happen in
    a well-managed deployment.
    """
    try:
        rows = session.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num")
        ).fetchall()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not read alembic_version: %s", exc)
        return None
    if not rows:
        return None
    return rows[0][0]


def is_at_or_above(
    current: Optional[str],
    target: str,
    alembic_cfg_path: str,
) -> bool:
    """Return True if ``current`` is ``target`` or a descendant of ``target``.

    Walks the alembic ScriptDirectory backward from ``current`` through
    ``down_revision`` chains, looking for ``target``.  Handles merge
    revisions whose ``down_revision`` is a tuple by recursing into all
    branches (any branch hit = compatible).

    Returns False if ``current`` is None (no migrations applied),
    if ``target`` is unreachable from ``current`` (ancestor),
    or if the alembic configuration cannot be read.
    """
    if current is None:
        return False
    if current == target:
        return True

    try:
        # pylint: disable=import-outside-toplevel
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError:
        logger.warning("alembic not importable; assuming incompatibility")
        return False

    try:
        cfg = Config(alembic_cfg_path)
        script = ScriptDirectory.from_config(cfg)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not read alembic config %s: %s", alembic_cfg_path, exc)
        return False

    visited: Set[str] = set()

    def _walk(rev_id: str) -> bool:
        if rev_id in visited:
            return False
        visited.add(rev_id)
        if rev_id == target:
            return True
        try:
            rev = script.get_revision(rev_id)
        except Exception:  # pylint: disable=broad-exception-caught
            return False
        if rev is None or rev.down_revision is None:
            return False
        if isinstance(rev.down_revision, tuple):
            return any(_walk(parent) for parent in rev.down_revision)
        return _walk(rev.down_revision)

    return _walk(current)


def check_module_compatibility(
    module_code: str,
    module_info: Dict[str, Any],
    session: Session,
    alembic_cfg_path: str,
) -> Optional[ModuleIncompatibility]:
    """Compare a module's required min revision against the current OSS head.

    Returns None if the module is compatible (or doesn't declare a minimum).
    Returns a ``ModuleIncompatibility`` if the check fails.

    Side effect: records the incompatibility in the registry on failure;
    clears any previous registry entry for this module on success.
    """
    required = module_info.get("min_oss_alembic_revision")
    if not required:
        # Module doesn't declare a minimum — assume compatible.
        _registry.clear(module_code)
        return None

    current = get_current_oss_revision(session)
    if is_at_or_above(current, required, alembic_cfg_path):
        _registry.clear(module_code)
        return None

    incompat = ModuleIncompatibility(
        module_code=module_code,
        required_revision=required,
        required_revision_human=module_info.get("min_oss_alembic_revision_human"),
        current_revision=current,
    )
    _registry.record(incompat)
    logger.error(
        "Pro+ module %s requires OSS alembic revision %s (%s); "
        "current is %s. Run 'alembic upgrade head' to apply pending migrations.",
        module_code,
        required,
        incompat.required_revision_human or "no human description",
        current or "(none)",
    )
    return incompat
