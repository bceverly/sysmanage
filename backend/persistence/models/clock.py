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

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

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


class ClockResync(Base):
    """One spot resynchronization of one host's clock (Phase 23.3 S5).

    Queued by an operator (one host, or every host out of bounds at once) and
    released in waves by ``services/clock_resync.py``: never more than
    ``WAVE_SIZE`` in flight per database, so a fleet-wide resync does not hit
    the NTP servers all at once.  ``command_id`` is the envelope id the agent
    echoes back with its result.
    """

    __tablename__ = "clock_resync"
    __table_args__ = (Index("ix_clock_resync_status", "status", "requested_at"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), nullable=False, index=True)
    batch_id = Column(GUID(), nullable=True, index=True)
    # queued | sent | succeeded | failed | unsupported | timed_out | canceled
    status = Column(String(16), nullable=False)
    requested_by = Column(String(255), nullable=True)
    requested_at = Column(DateTime, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    command_id = Column(String(36), nullable=True, index=True)
    # The measured offset when it was asked for, and the service's own
    # estimate afterwards.
    offset_before_ms = Column(Float, nullable=True)
    reported_after_ms = Column(Float, nullable=True)
    service = Column(String(16), nullable=True)
    method = Column(String(64), nullable=True)
    # A code (not_privileged, command_failed, no_tool, agent_too_old, ...).
    error = Column(String(32), nullable=True)
    detail = Column(String(500), nullable=True)


class NtpPolicy(Base):
    """The NTP servers hosts should use (Phase 23.3 S5b, Pro+).

    One row for the whole fleet in this database (``scope_kind`` "fleet",
    ``scope_ref`` ""), and one per site or tag that needs other servers -- an
    air-gapped site's internal pair.  Most specific wins: tag, then site, then
    fleet.  A host matched by two TAG policies that disagree is a conflict,
    reported and not applied: there is no "tightest" NTP server.
    """

    __tablename__ = "ntp_policy"
    __table_args__ = (
        UniqueConstraint("scope_kind", "scope_ref", name="uq_ntp_policy_scope"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scope_kind = Column(String(16), nullable=False)  # fleet | site | tag
    scope_ref = Column(String(64), nullable=False, default="")
    servers = Column(Text, nullable=False)  # JSON list of host names / IPs
    # Apply it (write the configuration, enable the service) or only report
    # the difference.
    enforce = Column(Boolean, nullable=False, default=False)
    # Step a clock automatically when it breaches its bounds.
    auto_resync = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String(255), nullable=True)


class NtpPolicyState(Base):
    """Where applying the policy stands on one host (one row per host)."""

    __tablename__ = "ntp_policy_state"

    host_id = Column(GUID(), primary_key=True)
    # The policy content this host was last sent (a digest), so a changed
    # policy is sent again and an unchanged one is not.
    policy_digest = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False)  # queued | succeeded | failed
    command_id = Column(String(36), nullable=True, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    sent_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    last_error = Column(String(2000), nullable=True)
    # The last automatic resync this policy asked for, to rate-limit them.
    auto_resync_at = Column(DateTime, nullable=True)
