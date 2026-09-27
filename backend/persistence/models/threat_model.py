# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The threat model and the posture punch list (ROADMAP 21.4 S2).

The questionnaire's answers derive a THREAT MODEL (a set of attributes); the
licensed ``advisor_engine`` judges the installation against it and produces
POSTURE ITEMS; an operator may WAIVE an open item, which is an audited
acceptance of a risk, never a green tick.

PARTITION SPLIT (the same rule as 14.1 / 14.3 / 21.2)
-----------------------------------------------------
* **shared** (``shared_*``, shared alembic chain)
  - ``SharedThreatQuestionnaire`` -- the curated questionnaire, one row per
    VERSION, synced from the engine. Every version is kept: a saved threat
    model names the version it was answered against.
* **tenant** (unprefixed, tenant alembic chain)
  - ``ThreatModel`` -- every saved derivation, versioned (``model_version``
    counts up per scope); exactly one is current. Re-running the wizard ADDS
    a version so "what changed" stays answerable.
  - ``PostureItem`` -- one row per (scope, rule): its latest state.
  - ``PostureItemEvent`` -- every state change of an item, for "what changed"
    and for regressions (21.4 S6).
  - ``PostureWaiver`` -- who accepted which risk, when, why, and the basis it
    was accepted on; revoked waivers are kept (they are audit history).

SCOPE (decided 2026-09-26): one threat model per TENANT in v1, but every row
carries ``scope_kind`` / ``scope_ref`` so per-site or per-tag models can come
later without reshaping data. ``scope_ref`` is "" (not NULL) for the tenant
scope, because unique constraints treat every NULL as distinct.

The questionnaire and the rules are referenced SOFTLY (slug + version, rule
key) -- the catalog is another partition.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

SCOPE_TENANT = "tenant"

POSTURE_SATISFIED = "satisfied"
POSTURE_OPEN = "open"
POSTURE_NOT_ASSESSABLE = "not_assessable"
# Waived is an OVERLAY on an open item (an active waiver), never a stored
# evaluation state: the evaluation keeps saying "open", so the risk it
# accepted stays visible underneath.
POSTURE_WAIVED = "waived"


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SharedThreatQuestionnaire(Base):
    """One version of a curated questionnaire, as the engine shipped it."""

    __tablename__ = "shared_threat_questionnaire"
    __table_args__ = (
        UniqueConstraint(
            "slug", "version", name="uq_shared_threat_questionnaire_version"
        ),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    slug = Column(String(128), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    contract_version = Column(Integer, nullable=False, default=1)
    definition = Column(JSON, nullable=False)
    source = Column(String(32), nullable=False, default="engine")
    synced_at = Column(DateTime, nullable=False, default=_utcnow)

    def __repr__(self):
        return f"<SharedThreatQuestionnaire({self.slug} v{self.version})>"


class ThreatModel(Base):
    """One saved derivation of the threat model for a scope."""

    __tablename__ = "threat_model"
    __table_args__ = (
        UniqueConstraint(
            "scope_kind", "scope_ref", "model_version", name="uq_threat_model_version"
        ),
        Index("ix_threat_model_current", "scope_kind", "scope_ref", "is_current"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scope_kind = Column(String(16), nullable=False, default=SCOPE_TENANT)
    scope_ref = Column(String(64), nullable=False, default="")
    model_version = Column(Integer, nullable=False)
    is_current = Column(Boolean, nullable=False, default=True)
    questionnaire_slug = Column(String(128), nullable=False)
    questionnaire_version = Column(Integer, nullable=False)
    # What was derived FROM (visible answers only) and what was derived.
    answers = Column(JSON, nullable=False)
    attributes = Column(JSON, nullable=False)
    digest = Column(String(64), nullable=False)
    complete = Column(Boolean, nullable=False, default=False)
    # Unanswered visible questions, and answers ignored because their
    # question is hidden -- shown to the operator, never silently dropped.
    missing = Column(JSON, nullable=True)
    ignored = Column(JSON, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    def __repr__(self):
        return (
            f"<ThreatModel({self.scope_kind}:{self.scope_ref} v{self.model_version})>"
        )


class PostureItem(Base):
    """The latest evaluation of one installation check for a scope."""

    __tablename__ = "posture_item"
    __table_args__ = (
        UniqueConstraint(
            "scope_kind", "scope_ref", "rule_key", name="uq_posture_item_rule"
        ),
        Index("ix_posture_item_state", "scope_kind", "scope_ref", "state"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scope_kind = Column(String(16), nullable=False, default=SCOPE_TENANT)
    scope_ref = Column(String(64), nullable=False, default="")
    rule_source = Column(String(16), nullable=False)
    rule_key = Column(String(64), nullable=False)
    rule_version = Column(Integer, nullable=True)
    # SOFT reference to the threat model this state was computed under.
    threat_model_id = Column(GUID(), nullable=True, index=True)
    # satisfied | open | not_assessable (waived is an overlay, see above).
    state = Column(String(16), nullable=False)
    outcome = Column(String(32), nullable=False)
    # server | tenant: who can change what the item reads.
    managed_by = Column(String(16), nullable=False)
    impact = Column(Integer, nullable=True)
    likelihood = Column(Integer, nullable=True)
    risk = Column(Integer, nullable=True)
    gaps = Column(JSON, nullable=True)
    coverage = Column(JSON, nullable=True)
    matches = Column(JSON, nullable=True)
    first_seen_at = Column(DateTime, nullable=False, default=_utcnow)
    state_changed_at = Column(DateTime, nullable=False, default=_utcnow)
    evaluated_at = Column(DateTime, nullable=False, default=_utcnow)

    def __repr__(self):
        return f"<PostureItem({self.rule_key}={self.state})>"


class PostureItemEvent(Base):
    """One change of an item's state -- including its first appearance and
    its removal (``to_state`` NULL) when the threat model stops applying it."""

    __tablename__ = "posture_item_event"
    __table_args__ = (
        Index(
            "ix_posture_item_event_rule", "scope_kind", "scope_ref", "rule_key", "at"
        ),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scope_kind = Column(String(16), nullable=False, default=SCOPE_TENANT)
    scope_ref = Column(String(64), nullable=False, default="")
    rule_key = Column(String(64), nullable=False)
    from_state = Column(String(16), nullable=True)
    to_state = Column(String(16), nullable=True)
    # Why it changed: "evaluation" (the fleet moved) or "threat_model" (the
    # model was re-derived), so a regression is not blamed on the wizard.
    cause = Column(String(32), nullable=False)
    threat_model_version = Column(Integer, nullable=True)
    at = Column(DateTime, nullable=False, default=_utcnow, index=True)


class PostureWaiver(Base):
    """An accepted risk: who, when, why, and the basis it was accepted on.

    The basis (rule version, risk, and the values of the attributes that made
    the rule apply) is what a waiver is SCOPED to (decided 2026-09-26): if the
    risk rises, the rule version changes, or those attributes change, the
    waiver is ``stale`` -- the item counts as open again until someone
    re-affirms (audited). A lower or unchanged risk keeps it.
    """

    __tablename__ = "posture_waiver"
    __table_args__ = (
        Index(
            "ix_posture_waiver_active",
            "scope_kind",
            "scope_ref",
            "rule_key",
            "revoked_at",
        ),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scope_kind = Column(String(16), nullable=False, default=SCOPE_TENANT)
    scope_ref = Column(String(64), nullable=False, default="")
    rule_key = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    rule_version = Column(Integer, nullable=True)
    risk = Column(Integer, nullable=True)
    basis_attributes = Column(JSON, nullable=True)
    threat_model_version = Column(Integer, nullable=True)
    granted_by = Column(String(255), nullable=False)
    granted_at = Column(DateTime, nullable=False, default=_utcnow)
    reaffirmed_by = Column(String(255), nullable=True)
    reaffirmed_at = Column(DateTime, nullable=True)
    stale_reason = Column(String(64), nullable=True)
    stale_since = Column(DateTime, nullable=True)
    revoked_by = Column(String(255), nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<PostureWaiver({self.rule_key} by {self.granted_by})>"
