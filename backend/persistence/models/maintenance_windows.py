# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Maintenance-window models (Phase 14.2).

Operator-defined change windows so that update installs and remote commands only
reach agents inside allowed windows — with *blackout* windows that forbid changes
and an *emergency override* that bypasses gating (audited).  These are per-tenant
operational policy, so they live in the **tenant** partition (unprefixed), soft-
referencing ``host.id`` / ``tags.id`` (same partition — plain indexed GUIDs, no
hard FK, to keep the migration order-independent and idempotent).

Model:

* ``MaintenanceWindow`` — one window: a name, a *kind* (``allow`` vs ``blackout``),
  a recurrence (``once`` | ``daily`` | ``weekly``) with an IANA timezone, and an
  enabled flag.  A ``once`` window uses absolute ``starts_at`` / ``ends_at`` (naive
  UTC); ``daily`` / ``weekly`` use a local ``start_time`` (HH:MM) + ``duration_minutes``
  (weekly also uses ``days_of_week``).
* ``MaintenanceWindowScope`` — what a window applies to: ``all`` hosts, a specific
  ``host``, or a ``tag`` (every host carrying it).  A window with no scope rows
  applies to nothing (defensive default; the API always writes at least one).
* ``MaintenanceOverride`` — a time-boxed emergency override for one host: dispatch
  is allowed regardless of windows until ``expires_at``.  Creation is audited.

Gating policy (see ``maintenance_window_service``): a host with **no** allow-window
is unrestricted (windows are opt-in per host); a host with allow-windows may
receive changes only inside one of them; a blackout always wins; an active
override beats everything.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# A window either PERMITS changes only inside it (allow) or FORBIDS changes
# inside it (blackout).  Validated at the API layer; kept here so the model,
# service, and API share one definition.
WINDOW_KIND_ALLOW = "allow"
WINDOW_KIND_BLACKOUT = "blackout"
WINDOW_KINDS = (WINDOW_KIND_ALLOW, WINDOW_KIND_BLACKOUT)

RECURRENCE_ONCE = "once"
RECURRENCE_DAILY = "daily"
RECURRENCE_WEEKLY = "weekly"
RECURRENCES = (RECURRENCE_ONCE, RECURRENCE_DAILY, RECURRENCE_WEEKLY)

SCOPE_ALL = "all"
SCOPE_HOST = "host"
SCOPE_TAG = "tag"
SCOPE_TYPES = (SCOPE_ALL, SCOPE_HOST, SCOPE_TAG)

# Canonical weekday tokens for ``days_of_week`` (comma-joined), Monday-first.
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _utcnow() -> datetime:
    """Naive-UTC now, matching the rest of the schema's timestamp convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MaintenanceWindow(Base):
    """A single maintenance (or blackout) window definition."""

    __tablename__ = "maintenance_window"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    # "allow" (changes only inside) | "blackout" (changes forbidden inside)
    kind = Column(String(10), nullable=False, default=WINDOW_KIND_ALLOW)
    # "once" | "daily" | "weekly"
    recurrence = Column(String(10), nullable=False, default=RECURRENCE_DAILY)
    timezone = Column(String(64), nullable=False, default="UTC")  # IANA name

    # Recurring (daily/weekly): local start time + length.
    start_time = Column(String(5), nullable=True)  # "HH:MM" in `timezone`
    duration_minutes = Column(Integer, nullable=True)
    days_of_week = Column(String(32), nullable=True)  # weekly: "mon,tue,..."

    # One-off (once): absolute bounds, naive UTC.
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)

    created_by = Column(GUID(), nullable=True)  # soft ref to user.id
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    def to_dict(self, scopes=None) -> dict:
        """Serialize to the wire/UI shape; ``scopes`` is an optional list of
        already-loaded MaintenanceWindowScope rows for this window."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "enabled": bool(self.enabled),
            "kind": self.kind,
            "recurrence": self.recurrence,
            "timezone": self.timezone,
            "start_time": self.start_time,
            "duration_minutes": self.duration_minutes,
            "days_of_week": ([d for d in (self.days_of_week or "").split(",") if d]),
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "scopes": [s.to_dict() for s in (scopes or [])],
        }

    def __repr__(self):
        return (
            f"<MaintenanceWindow(name='{self.name}', kind='{self.kind}', "
            f"recurrence='{self.recurrence}', enabled={self.enabled})>"
        )


class MaintenanceWindowScope(Base):
    """What a window applies to: all hosts, one host, or a tag."""

    __tablename__ = "maintenance_window_scope"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    window_id = Column(GUID(), nullable=False, index=True)  # soft ref (same partition)
    scope_type = Column(String(10), nullable=False)  # all | host | tag
    host_id = Column(GUID(), nullable=True, index=True)  # soft ref to host.id
    tag_id = Column(GUID(), nullable=True, index=True)  # soft ref to tags.id

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "scope_type": self.scope_type,
            "host_id": str(self.host_id) if self.host_id else None,
            "tag_id": str(self.tag_id) if self.tag_id else None,
        }

    def __repr__(self):
        return (
            f"<MaintenanceWindowScope(type='{self.scope_type}', "
            f"host_id={self.host_id}, tag_id={self.tag_id})>"
        )


class MaintenanceOverride(Base):
    """A time-boxed emergency override that bypasses gating for one host."""

    __tablename__ = "maintenance_override"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), nullable=False, index=True)  # soft ref to host.id
    reason = Column(Text, nullable=False)
    created_by = Column(GUID(), nullable=True)  # soft ref to user.id
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    expires_at = Column(DateTime, nullable=False)  # active until this instant (UTC)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "host_id": str(self.host_id) if self.host_id else None,
            "reason": self.reason,
            "username": self.username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    def __repr__(self):
        return (
            f"<MaintenanceOverride(host_id={self.host_id}, "
            f"expires_at={self.expires_at})>"
        )
