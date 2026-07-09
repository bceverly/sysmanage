"""
Custom Metrics & Graphs models (Custom Metrics — Slice 1).

Landscape "Custom Graphs" parity: an operator defines a named custom metric = a
small script that outputs ONE numeric value.  The metric is targeted by HOST
TAG (assign the metric to tag(s) → it deploys to every host carrying those
tags); the agent runs it on a cadence and returns the number; samples are stored
as a time-series for graphing + alerting.

This is a Pro+ capability whose LOGIC lives in the ``observability_engine``.
Per the moat model, only the SCHEMA (these models) + the role belong in OSS.

Tenant-partition tables: table names are UNPREFIXED (no ``registry_``/
``shared_`` prefix), consistent with the prefix guard for the tenant chain.

Targeting FK note: the host tag table (``tags``) lives in the tenant partition
(same partition as ``host``), so ``custom_metric_tag.tag_id`` is a REAL FK to
``tags.id`` — not a soft reference.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import backref, relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

HOST_ID_FK = "host.id"
TAG_ID_FK = "tags.id"
CUSTOM_METRIC_ID_FK = "custom_metric.id"

# sample status values
SAMPLE_STATUS_OK = "ok"
SAMPLE_STATUS_ERROR = "error"
SAMPLE_STATUSES = (SAMPLE_STATUS_OK, SAMPLE_STATUS_ERROR)


def _utcnow():
    """Timezone-aware UTC now (matches tenant models that use
    ``datetime.now(timezone.utc)`` defaults)."""
    return datetime.now(timezone.utc)


class CustomMetric(Base):
    """A named custom metric definition: a script emitting ONE numeric value."""

    __tablename__ = "custom_metric"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    # The script body that outputs a single numeric value.
    script = Column(Text, nullable=False)
    # Interpreter used to run the script (e.g. sh/bash/python3).
    interpreter = Column(String(50), nullable=False, default="sh")
    # Optional unit of the emitted value (e.g. "%", "MB").
    unit = Column(String(50), nullable=True)
    # How often the agent runs the metric, in seconds.
    cadence_seconds = Column(Integer, nullable=False, default=300)
    enabled = Column(Boolean, nullable=False, default=True)
    # Soft reference to the creating user.  NO FK: users may live in the
    # registry partition, so a cross-partition FK is not permitted.
    created_by = Column(GUID(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    tags = relationship(
        "CustomMetricTag",
        back_populates="custom_metric",
        passive_deletes=True,
    )
    samples = relationship(
        "CustomMetricSample",
        back_populates="custom_metric",
        passive_deletes=True,
    )

    def __repr__(self):
        return (
            f"<CustomMetric(id={self.id}, name='{self.name}', "
            f"interpreter='{self.interpreter}', enabled={self.enabled})>"
        )


class CustomMetricTag(Base):
    """Targeting association: assign a custom metric to a host tag.

    Same-partition FK: ``tags`` lives in the tenant partition alongside
    ``host``, so a real FK to ``tags.id`` is permitted.
    """

    __tablename__ = "custom_metric_tag"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    custom_metric_id = Column(
        GUID(),
        ForeignKey(CUSTOM_METRIC_ID_FK, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id = Column(
        GUID(),
        ForeignKey(TAG_ID_FK, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    custom_metric = relationship("CustomMetric", back_populates="tags")
    tag = relationship(
        "Tag",
        backref=backref("custom_metric_tags", passive_deletes=True),
    )

    def __repr__(self):
        return (
            f"<CustomMetricTag(id={self.id}, "
            f"custom_metric_id={self.custom_metric_id}, tag_id={self.tag_id})>"
        )


class CustomMetricSample(Base):
    """A single time-series sample of a custom metric collected from a host."""

    __tablename__ = "custom_metric_sample"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    custom_metric_id = Column(
        GUID(),
        ForeignKey(CUSTOM_METRIC_ID_FK, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID_FK, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NULL when the sample errored (see ``status``/``error_detail``).
    value = Column(Float, nullable=True)
    # ok | error
    status = Column(String(20), nullable=False, default=SAMPLE_STATUS_OK)
    error_detail = Column(Text, nullable=True)
    collected_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    custom_metric = relationship("CustomMetric", back_populates="samples")
    host = relationship(
        "Host",
        backref=backref("custom_metric_samples", passive_deletes=True),
    )

    __table_args__ = (
        Index(
            "ix_custom_metric_sample_metric_host_collected",
            "custom_metric_id",
            "host_id",
            "collected_at",
        ),
    )

    def __repr__(self):
        return (
            f"<CustomMetricSample(id={self.id}, "
            f"custom_metric_id={self.custom_metric_id}, host_id={self.host_id}, "
            f"value={self.value}, status='{self.status}')>"
        )
