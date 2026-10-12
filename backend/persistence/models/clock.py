# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Clock-offset history per host (Phase 23.3).

One row per host per ``services.clock_tracking.HISTORY_SECONDS`` (15 min):
the median offset the SERVER measured, and the round trip it was measured
over.  Feeds the offset chart on the host page.  ``host_id`` is a soft
reference (tenant tables carry no foreign keys across partitions); rows older
than ``RETENTION_DAYS`` are pruned by the writer.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, Index, String

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
