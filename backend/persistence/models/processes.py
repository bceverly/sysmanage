# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Running-process snapshot model (Phase 13.3 — Process Management).

Each row is one process from the most recent snapshot an agent reported for a
host.  The ingest handler replaces the whole set per host on each update, so
this table always reflects the latest snapshot rather than a time series.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import backref, relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

HOST_ID_FK = "host.id"


class HostProcess(Base):
    """A single process from a host's latest process snapshot."""

    __tablename__ = "host_process"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(), ForeignKey(HOST_ID_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    pid = Column(Integer, nullable=False, index=True)
    parent_pid = Column(Integer, nullable=True)
    process_name = Column(String(255), nullable=False, index=True)
    username = Column(String(255), nullable=True)
    status = Column(String(50), nullable=True)  # running, sleeping, zombie, ...
    cpu_percent = Column(Float, nullable=True)
    memory_percent = Column(Float, nullable=True)
    memory_rss_bytes = Column(BigInteger, nullable=True)
    command_line = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)  # process create time (UTC naive)
    collected_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )  # snapshot time (UTC, stored naive)

    host = relationship(
        "Host",
        backref=backref("processes", passive_deletes=True),
    )

    def __repr__(self):
        return (
            f"<HostProcess(host_id={self.host_id}, pid={self.pid}, "
            f"name='{self.process_name}')>"
        )
