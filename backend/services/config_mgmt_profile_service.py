# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Profile persistence helpers (Phase 20.1).

Sits between the HTTP layer and the Pro+ engine. Every RULE -- what makes a
profile valid, how versions are numbered, what a snapshot contains -- is asked
of the engine; this module only serialises and persists.

That division is deliberate rather than tidy-minded. The engine is the licensed
artefact and the rules are the licensed part; reimplementing "is this cron
valid" here would put the same logic in two places, and the copy in the
open-source tree would be the one people edit.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import config_mgmt_spec_shim as shim

logger = logging.getLogger(__name__)

# Fields an update may change. Anything else in a request body is ignored
# rather than trusted -- version, timestamps and identity are ours to set.
_UPDATABLE = ("name", "engine", "content", "description", "is_active")

# Changing any of these makes the outgoing body worth keeping. A description
# edit is not a new version of the configuration; treating it as one would
# fill the history with rows nobody can tell apart.
_VERSIONED_FIELDS = ("engine", "content")


def _engine():
    """The Pro+ module, or None when it is not loaded."""
    from backend.licensing.module_loader import module_loader  # noqa: PLC0415

    return module_loader.get_module(shim.ENGINE_CODE)


def validate_profile(name: str, engine: str, content: str) -> Optional[str]:
    """Ask the engine whether a profile is acceptable."""
    module = _engine()
    if module is None:
        # The router is gated on the module being loaded, so this is
        # unreachable in practice; failing closed keeps it that way if the
        # gate is ever relaxed.
        return "configuration management engine is not available"
    return module.validate_profile(name, engine, content)


def validate_assignment(
    host_id: Optional[str],
    tag_id: Optional[str],
    site_id: Optional[str],
    schedule: Optional[str],
) -> Optional[str]:
    """Ask the engine whether an assignment is acceptable."""
    module = _engine()
    if module is None:
        return "configuration management engine is not available"
    return module.validate_assignment(host_id, tag_id, site_id, schedule)


def validate_update(profile, changes: Dict[str, Any]) -> Optional[str]:
    """Validate an update against the profile it would produce.

    Validates the RESULT, not the delta: a request that changes only the
    engine still has to be valid alongside the existing content, and checking
    the delta alone would let a valid-looking change produce an invalid
    profile.
    """
    merged_name = changes.get("name", profile.name)
    merged_engine = changes.get("engine", profile.engine)
    merged_content = changes.get("content", profile.content)
    return validate_profile(merged_name, merged_engine, merged_content)


def name_taken(
    db_session: Session, name: str, exclude_id: Optional[Any] = None
) -> bool:
    """Whether another profile already holds this name."""
    query = db_session.query(models.ConfigProfile).filter(
        models.ConfigProfile.name == (name or "").strip()
    )
    if exclude_id is not None:
        query = query.filter(models.ConfigProfile.id != exclude_id)
    return query.first() is not None


def apply_update(
    db_session: Session, profile, changes: Dict[str, Any], actor: str
) -> None:
    """Apply changes, snapshotting the outgoing body when it matters.

    The snapshot is taken BEFORE the overwrite and from the engine, so version
    N in the history is what version N actually contained.
    """
    module = _engine()
    versioned = any(
        field in changes and changes[field] != getattr(profile, field)
        for field in _VERSIONED_FIELDS
    )

    if versioned and module is not None:
        snapshot = module.snapshot_of(profile)
        db_session.add(
            models.ConfigProfileVersion(
                profile_id=snapshot["profile_id"],
                version=snapshot["version"],
                engine=snapshot["engine"],
                content=snapshot["content"],
                created_by=snapshot["created_by"],
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        profile.version = module.next_version(profile.version)

    for field in _UPDATABLE:
        if field in changes:
            value = changes[field]
            if field == "engine" and value:
                value = str(value).strip().lower()
            if field == "name" and value:
                value = str(value).strip()
            setattr(profile, field, value)

    profile.updated_by = actor
    profile.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


def profile_to_dict(profile) -> Dict[str, Any]:
    """Serialise a profile for the API."""
    return {
        "id": str(profile.id),
        "name": profile.name,
        "description": profile.description,
        "engine": profile.engine,
        "content": profile.content,
        "version": profile.version,
        "is_active": bool(profile.is_active),
        "created_by": profile.created_by,
        "updated_by": profile.updated_by,
        "created_at": _utc(profile.created_at),
        "updated_at": _utc(profile.updated_at),
    }


def version_to_dict(row) -> Dict[str, Any]:
    """Serialise a stored version for the API."""
    return {
        "id": str(row.id),
        "profile_id": str(row.profile_id),
        "version": row.version,
        "engine": row.engine,
        "content": row.content,
        "created_by": row.created_by,
        "created_at": _utc(row.created_at),
    }


def assignment_to_dict(row) -> Dict[str, Any]:
    """Serialise an assignment for the API."""
    return {
        "id": str(row.id),
        "profile_id": str(row.profile_id),
        "host_id": str(row.host_id) if row.host_id else None,
        "tag_id": str(row.tag_id) if row.tag_id else None,
        "site_id": str(row.site_id) if row.site_id else None,
        "enabled": bool(row.enabled),
        "schedule": row.schedule,
        "check_mode": bool(row.check_mode),
        "created_by": row.created_by,
        "created_at": _utc(row.created_at),
        "last_applied_at": _utc(row.last_applied_at),
    }


def _utc(value):
    """Stamp naive timestamps as UTC.

    Rows are stored naive-UTC; handing a naive datetime to a browser makes it
    render as local time, so a profile edited an hour ago can appear to have
    been edited in the future.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
