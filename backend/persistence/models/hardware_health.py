# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Hardware health (Phase 23.1 S2): each host's drives, arrays, pools, sensors
and memory as its agent last judged them, and the history of their states.

``hardware_component`` is the CURRENT picture, one row per component (the
agent's ``kind`` + ``ident`` within the host).  ``hardware_event`` is a row
per state CHANGE -- a drive turning warning, a pool degrading, a sensor
recovering -- which is what the fleet page, the host tab and (S5) the alerts
work from; an unchanged report adds nothing.  ``reasons`` are codes with
parameters (``[{"code": "media_errors", "count": 19}]``), worded by the UI in
the reader's language.
"""

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class HardwareComponent(Base):
    """A host's drive, array, pool, sensor or memory controller, now."""

    __tablename__ = "hardware_component"
    __table_args__ = (
        UniqueConstraint("host_id", "kind", "ident", name="uq_hardware_component"),
        Index("ix_hardware_component_state", "state"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String(16), nullable=False)  # drive|array|pool|sensor|memory
    ident = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    state = Column(String(16), nullable=False)  # ok|warning|failed|unknown
    reasons = Column(Text, nullable=True)  # JSON list of {code, ...params}
    metrics = Column(Text, nullable=True)  # JSON object; absent = not measured
    source = Column(String(64), nullable=True)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    state_since = Column(DateTime, nullable=False)


class HardwareEvent(Base):
    """A component's state changed (or it appeared, or it was last seen)."""

    __tablename__ = "hardware_event"
    __table_args__ = (
        Index("ix_hardware_event_host_time", "host_id", "occurred_at"),
        Index("ix_hardware_event_open", "acknowledged_at", "resolved_at"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String(16), nullable=False)
    ident = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    from_state = Column(String(16), nullable=True)  # None: first seen
    to_state = Column(String(16), nullable=False)  # "gone": no longer reported
    reasons = Column(Text, nullable=True)
    occurred_at = Column(DateTime, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(255), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(255), nullable=True)
    note = Column(String(500), nullable=True)


class HardwareToolInstall(Base):
    """The last smartmontools install the server asked a host for (23.1 S6).

    A host whose drives cannot be read (``smartctl_absent``) is RECOMMENDED
    smartmontools; an operator installs it from the host or the fleet page,
    or -- Enterprise, and only once an administrator has turned it on --
    the server does.  One row per host: ``status`` is what the agent answered
    (matched by ``command_id``), ``attempts`` counts automatic pushes, and
    ``requested_by`` is the operator or ``system:smartmontools-auto-install``.
    """

    __tablename__ = "hardware_tool_install"

    host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="CASCADE"), primary_key=True
    )
    package = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False)  # queued|succeeded|failed
    attempts = Column(Integer, nullable=False, default=0)
    command_id = Column(String(36), nullable=True, index=True)
    requested_by = Column(String(255), nullable=True)
    requested_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
