# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The advisor's rules and what they concluded, per host (ROADMAP 21.2 S2).

A rule (see ``advisor_engine``'s rule contract) is DATA: a ``requires`` block
naming the fact columns and evidence domains it reads, plus a SQLite ``when``
query.  This module stores rules and their outcomes; the licensed engine
decides the outcomes.

PARTITION SPLIT -- the same one as query packs and advisories
--------------------------------------------------------------
* **shared partition** (``shared_*``, shared alembic chain)
  - ``SharedAdvisorRulePack`` / ``SharedAdvisorRule`` -- curated rules. Global
    reference data, ONE copy, offline-updatable; never per tenant.
* **tenant partition** (unprefixed, tenant alembic chain)
  - ``AdvisorRule`` -- rules a customer wrote.
  - ``AdvisorResult`` -- one row per (host, rule): the outcome. A curated rule
    is referenced SOFTLY (``shared_rule_id``, no ForeignKey): under scale-out
    the catalog is another database and the constraint could not be enforced.

FOUR OUTCOMES, AND THE ONE THAT MUST NEVER GO MISSING
-----------------------------------------------------
``fires`` / ``does_not_fire`` / ``not_assessable`` / ``not_applicable``.
An advisor's output is a list, and an empty list reads as "your fleet is in
good shape". So a host the engine could not evaluate gets a ROW, with the
specific gaps -- it is never simply absent. A missing row means "not
evaluated yet", which the evaluation tick exists to make rare; it must never
mean "fine".

RESULTS ARE ROWS, LATEST ONLY
-----------------------------
One row per (host, rule), replaced on each evaluation. Every consumer (the S4
feed, the S7 host tab) asks "which hosts match this rule" or "what does this
host match" -- queries over rows. History is not kept here: the evidence it
was computed from is not kept either, so an old outcome could not be
re-examined anyway.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

CASCADE_DELETE = "CASCADE"

ADVISOR_RULE_SOURCE_SHARED = "shared"
ADVISOR_RULE_SOURCE_TENANT = "tenant"
ADVISOR_RULE_SOURCES = (ADVISOR_RULE_SOURCE_SHARED, ADVISOR_RULE_SOURCE_TENANT)

# Mirrors the engine's contract. Stored as plain strings so the UI (S7) can
# render a code, never a sentence the server composed.
ADVISOR_OUTCOME_FIRES = "fires"
ADVISOR_OUTCOME_DOES_NOT_FIRE = "does_not_fire"
ADVISOR_OUTCOME_NOT_ASSESSABLE = "not_assessable"
ADVISOR_OUTCOME_NOT_APPLICABLE = "not_applicable"
ADVISOR_OUTCOMES = (
    ADVISOR_OUTCOME_FIRES,
    ADVISOR_OUTCOME_DOES_NOT_FIRE,
    ADVISOR_OUTCOME_NOT_ASSESSABLE,
    ADVISOR_OUTCOME_NOT_APPLICABLE,
)


def _utcnow() -> datetime:
    """Naive-UTC now, matching the shared/tenant timestamp convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# shared partition -- the curated catalog
# ---------------------------------------------------------------------------


class SharedAdvisorRulePack(Base):
    """A curated rule pack. Global reference data, never per tenant."""

    __tablename__ = "shared_advisor_rule_pack"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_shared_advisor_rule_pack_slug"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    # Stable identity across catalog refreshes -- a re-ingest mints a new id.
    slug = Column(String(128), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    # Retired rather than deleted: its rules stop being evaluated, and the
    # results they left are cleared by the next tick.
    deprecated = Column(Boolean, nullable=False, default=False)
    source = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    rules = relationship(
        "SharedAdvisorRule", back_populates="pack", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<SharedAdvisorRulePack(slug={self.slug}, version={self.version})>"


class SharedAdvisorRule(Base):
    """One curated rule. ``definition`` is the whole rule, as the engine's
    contract describes it; the other columns are copies kept for querying."""

    __tablename__ = "shared_advisor_rule"
    __table_args__ = (
        UniqueConstraint(
            "shared_pack_id", "rule_key", name="uq_shared_advisor_rule_key"
        ),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    shared_pack_id = Column(
        GUID(),
        ForeignKey("shared_advisor_rule_pack.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    # The rule's own ``id`` ("SEC-001"): stable across versions of the rule.
    rule_key = Column(String(64), nullable=False, index=True)
    contract_version = Column(Integer, nullable=False, default=1)
    rule_version = Column(Integer, nullable=False, default=1)
    lens = Column(String(32), nullable=False)
    scope = Column(String(16), nullable=False, default="host")
    title = Column(String(255), nullable=False)
    definition = Column(JSON, nullable=False)

    pack = relationship("SharedAdvisorRulePack", back_populates="rules")

    def __repr__(self):
        return f"<SharedAdvisorRule(key={self.rule_key}, v={self.rule_version})>"


# ---------------------------------------------------------------------------
# tenant partition -- a customer's own rules, and every outcome
# ---------------------------------------------------------------------------


class AdvisorRule(Base):
    """A rule a customer wrote. Tenant data, never shared."""

    __tablename__ = "advisor_rule"
    __table_args__ = (UniqueConstraint("rule_key", name="uq_advisor_rule_key"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    rule_key = Column(String(64), nullable=False)
    contract_version = Column(Integer, nullable=False, default=1)
    rule_version = Column(Integer, nullable=False, default=1)
    lens = Column(String(32), nullable=False)
    scope = Column(String(16), nullable=False, default="host")
    title = Column(String(255), nullable=False)
    definition = Column(JSON, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    def __repr__(self):
        return f"<AdvisorRule(key={self.rule_key}, enabled={self.enabled})>"


class AdvisorResult(Base):
    """What one rule concluded about one host, as of ``evaluated_at``."""

    __tablename__ = "advisor_result"
    __table_args__ = (
        UniqueConstraint(
            "host_id", "rule_source", "rule_key", name="uq_advisor_result_host_rule"
        ),
        # The feed's two questions: "which hosts does rule X fire on" and
        # "what is not assessable, and why" -- both filter on outcome.
        Index("ix_advisor_result_rule_outcome", "rule_source", "rule_key", "outcome"),
        Index("ix_advisor_result_outcome", "outcome"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    rule_source = Column(String(16), nullable=False)
    rule_key = Column(String(64), nullable=False)
    # SOFT reference to shared_advisor_rule.id -- see the module docstring.
    shared_rule_id = Column(GUID(), nullable=True, index=True)
    # Same partition, so a real FK: a deleted tenant rule takes its results.
    rule_id = Column(
        GUID(),
        ForeignKey("advisor_rule.id", ondelete=CASCADE_DELETE),
        nullable=True,
        index=True,
    )
    rule_version = Column(Integer, nullable=True)
    lens = Column(String(32), nullable=True)
    outcome = Column(String(32), nullable=False)
    # For not_assessable / not_applicable: EVERY gap, each
    # ``{evidence, reason[, columns, age_days, max_age_days, detail]}``.
    gaps = Column(JSON, nullable=True)
    # For fires: how many rows matched (exact) and a bounded sample of them.
    match_count = Column(Integer, nullable=False, default=0)
    matches = Column(JSON, nullable=True)
    evaluated_at = Column(DateTime, nullable=False, default=_utcnow)

    def __repr__(self):
        return (
            f"<AdvisorResult(host_id={self.host_id}, rule={self.rule_key}, "
            f"outcome={self.outcome})>"
        )
