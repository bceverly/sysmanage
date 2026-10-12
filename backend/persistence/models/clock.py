# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Clock-offset history per host, and the offset bounds (Phase 23.3).

One row per host per ``services.clock_tracking.HISTORY_SECONDS`` (15 min):
the median offset the SERVER measured, and the round trip it was measured
over.  Feeds the offset chart on the host page.  ``host_id`` is a soft
reference (tenant tables carry no foreign keys across partitions); rows older
than ``RETENTION_DAYS`` are pruned by the writer.

``clock_bound`` holds the OVERRIDES of the server-wide bounds (a server
setting, ``services/clock_status.py``): one row for the tenant, and one per
site or tag that needs tighter or looser bounds.  ``scope_ref`` is a soft
reference (a site or tag id; "" for the tenant row).
"""

import uuid

from sqlalchemy import Column, DateTime, Float, Index, String, UniqueConstraint

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class HostClockSample(Base):
    """One point of a host's measured clock offset."""

    __tablename__ = "host_clock_sample"
    __table_args__ = (
        Index("ix_host_clock_sample_host_time", "host_id", "measured_at"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), nullable=False)
    measured_at = Column(DateTime, nullable=False)
    # Host minus server, ms: positive means the host's clock is ahead.
    offset_ms = Column(Float, nullable=False)
    rtt_ms = Column(Float, nullable=True)
    # "exchange" (NTP-style, ~ms) or "timestamp" (a refused message; coarse).
    method = Column(String(16), nullable=False)


class ClockBound(Base):
    """A warning and a critical offset bound for one tenant, site or tag."""

    __tablename__ = "clock_bound"
    __table_args__ = (
        UniqueConstraint("scope_kind", "scope_ref", name="uq_clock_bound_scope"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scope_kind = Column(String(16), nullable=False)  # tenant | site | tag
    scope_ref = Column(String(64), nullable=False, default="")
    # Absolute offset, ms, at or beyond which a host is warning / critical.
    warning_ms = Column(Float, nullable=False)
    critical_ms = Column(Float, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String(255), nullable=True)
