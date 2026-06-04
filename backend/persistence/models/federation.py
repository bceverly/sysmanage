"""
Multi-site federation schema (Phase 12.6).

This module defines the SQLAlchemy ORM classes for the federation
data model.  The 13 tables here fall into two role groups:

  * **Coordinator-side** (9 tables): site registry + the three
    architectural tiers from the ROADMAP — host directory, aggregate
    rollups (host / compliance / vulnerability), policy push tracking,
    dispatched command tracking, federation audit log.

  * **Site-side** (4 tables): coordinator enrollment singleton,
    upstream sync queue (with dedup keys for offline-replay), and the
    received-policy + received-command inboxes.

Both sets are defined in a single OSS file because the SQLAlchemy
model definitions need to be importable before the Cython
``federation_controller_engine`` / ``federation_site_engine`` modules
exist.  API-layer gating (402 stub when the appropriate engine isn't
loaded) happens in 12.1 / 12.2 in the routers, NOT here.

A given SysManage deployment plays exactly one role — coordinator OR
site — but both sets of tables get created on every instance.  The
unused half is dead weight in row count (always zero rows) and well
under a kilobyte of schema; conditional migrations would cost more
in operator confusion than they'd save.

Architectural notes (see ROADMAP Phase 12 "Data Architecture"):

  * The host-directory tier is sized to ~1 KB per host × 1M-host
    target ≈ 1 GB, holding ONLY the columns operators filter and
    search on.  Detail-tier data (full software inventory, audit
    log bodies, OS-specific facts) stays at the originating site
    and is proxied on drill-down.
  * The dedup key on ``federation_sync_queue`` is the
    ``(host_id, field, mtime)`` triple from the ROADMAP — this is
    what makes offline-replay safe when a site reconnects and
    re-sends its queued deltas.
  * Geo columns mirror the Phase 12.7 ``host`` columns 1:1 so the
    coordinator-side map can render without a re-resolve.
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
    UniqueConstraint,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# ---------------------------------------------------------------------
# Singleton row id for the site-side ``federation_coordinator`` table.
# Single-row tables use a fixed UUID so application code can upsert by
# primary key without first SELECTing.  Same pattern as MfaSettings /
# MirrorSettings.
# ---------------------------------------------------------------------

SINGLETON_FEDERATION_COORDINATOR_ID = uuid.UUID("00000000-0000-0000-0000-00000000fed0")
SINGLETON_FEDERATION_ALERT_CONFIG_ID = uuid.UUID("00000000-0000-0000-0000-00000000fed1")


# FK targets pulled into constants so a future rename is a one-line
# change.  Matches the convention used by access_groups.py.
_FK_FEDERATION_SITES_ID = "federation_sites.id"
_FK_FEDERATION_POLICIES_ID = "federation_policies.id"


def _utcnow_naive() -> datetime:
    """UTC ``now()`` with the tzinfo stripped.

    SQLAlchemy's ``DateTime`` (without ``timezone=True``) on SQLite
    drops the tzinfo silently and on PostgreSQL emits a warning when
    binding tz-aware values.  Every other model in this codebase
    stores naive UTC; we match that to keep query semantics uniform.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# =====================================================================
# Coordinator-side tables
# =====================================================================


class FederationSite(Base):
    """Registered subordinate site server in the coordinator's registry.

    One row per enrolled site.  Created via the enrollment flow
    (Phase 12.1) and never deleted on disenrollment — the row stays
    with ``status='removed'`` so the federation audit log can still
    resolve historical references by ``site_id``.

    Geo fields are operator-supplied at enrollment (or filled by a
    future "resolve coordinates from address" helper); they drive the
    coordinator's geographic map placement.  Distinct from the
    host-level geo columns, which are auto-resolved from public IP.
    """

    __tablename__ = "federation_sites"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    location_label = Column(String(255), nullable=True)
    url = Column(String(512), nullable=False)
    # The site's pinned TLS leaf certificate (PEM).  The coordinator
    # uses this to validate the site during mutual-TLS handshake.
    tls_cert_pem = Column(Text, nullable=True)
    # SHA-256 of the enrollment token, scrubbed after successful
    # enrollment.  NULL once the site is fully enrolled.
    enrollment_token_hash = Column(String(128), nullable=True)
    # Phase 12.1.C: when the token in ``enrollment_token_hash``
    # stops being acceptable to ``complete_enrollment``.  NULL means
    # "no token outstanding" (already-enrolled or cancelled).
    enrollment_token_expires_at = Column(DateTime, nullable=True)
    # Phase 12.1.C: most recent time the site flipped to ``enrolled``.
    # Survives suspend/resume cycles — only ``complete_enrollment``
    # writes this column.  NULL until first enrollment completes.
    enrolled_at = Column(DateTime, nullable=True)
    # Phase 12.6: SHA-256 of the long-lived bearer token the site
    # presents on every inbound sync POST (host rollup, host directory,
    # command results, etc.).  Minted at ``complete_enrollment`` time,
    # returned to the site server once as plaintext, then never stored
    # in plaintext on the coordinator.  NULL until enrollment completes;
    # also NULL after ``remove_site`` scrubs credentials.
    sync_bearer_token_hash = Column(String(128), nullable=True)
    # Phase 12.10 Slice 3: plaintext bearer the COORDINATOR presents on
    # every outbound push to this subordinate site (policy push, command
    # dispatch).  Stored as plaintext on this row because the coordinator
    # is the SENDER for this direction — it needs the literal value to
    # set the ``Authorization`` header.  The site stores the SHA-256
    # equivalent in ``federation_coordinator.coordinator_inbound_bearer_token_hash``
    # so a leak on the verifier side never exposes a usable secret.
    coordinator_outbound_bearer_token = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="enrolled")
    # Cached from the latest host rollup so the Sites page doesn't
    # have to JOIN through ``federation_host_rollup`` to render.
    host_count = Column(Integer, nullable=False, default=0)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(32), nullable=True)
    sync_interval_seconds = Column(Integer, nullable=False, default=300)
    # Phase 12.2: latest site-reported metadata (from the site's
    # ``site_metadata`` sync payload).  ``sysmanage_version`` lets the
    # coordinator flag version-skewed sites; ``connection_state`` is the
    # site's OWN view of its uplink (online/degraded/offline — i.e. whether
    # it is currently in local autonomy mode); ``capabilities_json`` is the
    # JSON list of loaded engine modules the site advertises.
    # ``last_metadata_at`` is when that report last landed.
    sysmanage_version = Column(String(32), nullable=True)
    connection_state = Column(String(16), nullable=True)
    capabilities_json = Column(Text, nullable=True)
    last_metadata_at = Column(DateTime, nullable=True)
    # Minimum acceptable agent version on the site — used to gate
    # command dispatch (coordinator refuses to send a command that
    # the site is too old to handle).
    agent_version_min = Column(String(32), nullable=True)
    geo_latitude = Column(Float, nullable=True)
    geo_longitude = Column(Float, nullable=True)
    geo_country_code = Column(String(2), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    updated_at = Column(
        DateTime, nullable=False, default=_utcnow_naive, onupdate=_utcnow_naive
    )

    __table_args__ = (
        Index("ix_federation_sites_status", "status"),
        Index("ix_federation_sites_last_sync_at", "last_sync_at"),
    )


class FederationHostDirectory(Base):
    """Coordinator-side per-host index — the "host directory tier".

    One row per host across the entire fleet, holding only the columns
    operators filter and search on.  Sized for ~1 KB × 1M hosts ≈ 1 GB
    in PostgreSQL.  Detail-tier data (software inventory, full audit
    log, OS-specific facts) stays at the originating site and is
    proxied on drill-down — DO NOT add columns to this table without
    a fleet-scale storage review.

    ``host_id`` is the host's primary-key UUID at its originating
    site, replicated here.  Combined with ``site_id`` this uniquely
    identifies a host across the federation.
    """

    __tablename__ = "federation_host_directory"

    host_id = Column(GUID(), primary_key=True)
    site_id = Column(
        GUID(),
        ForeignKey(_FK_FEDERATION_SITES_ID, ondelete="CASCADE"),
        nullable=False,
    )
    fqdn = Column(String(255), nullable=False)
    ipv4 = Column(String(45), nullable=True)
    ipv6 = Column(String(45), nullable=True)
    public_ip = Column(String(45), nullable=True)
    os_family = Column(String(64), nullable=True)
    os_version = Column(String(64), nullable=True)
    platform = Column(String(64), nullable=True)
    status = Column(String(32), nullable=True)
    last_seen = Column(DateTime, nullable=True)
    # JSON-encoded list of tag names — denormalized vs ``host_tags``
    # at the site so cross-site filter queries don't have to join
    # over a separate table at 1M-host scale.  Maintained by the
    # site's upstream sync.
    tags_json = Column(Text, nullable=True)
    geo_country_code = Column(String(2), nullable=True)
    geo_subdivision_code = Column(String(10), nullable=True)
    geo_city = Column(String(200), nullable=True)
    geo_latitude = Column(Float, nullable=True)
    geo_longitude = Column(Float, nullable=True)
    # Last time the SITE updated this row — used by delta-sync
    # dedup-on-replay.  Distinct from ``last_seen`` (the agent's
    # heartbeat at the site).
    mtime = Column(DateTime, nullable=False, default=_utcnow_naive)

    __table_args__ = (
        Index("ix_federation_host_directory_site_fqdn", "site_id", "fqdn"),
        Index("ix_federation_host_directory_site_status", "site_id", "status"),
        Index(
            "ix_federation_host_directory_geo_country",
            "geo_country_code",
            "geo_subdivision_code",
        ),
        Index("ix_federation_host_directory_last_seen", "last_seen"),
    )


class FederationHostRollup(Base):
    """Aggregate host counts per site, sampled at ``snapshot_at``.

    Append-only.  Older snapshots are pruned by a retention sweeper
    (Phase 12.1) — the Sites page reads only the latest row per
    ``site_id``.
    """

    __tablename__ = "federation_host_rollup"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    site_id = Column(
        GUID(),
        ForeignKey(_FK_FEDERATION_SITES_ID, ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    host_count = Column(Integer, nullable=False, default=0)
    active_count = Column(Integer, nullable=False, default=0)
    # JSON: {"ubuntu": 12, "debian": 5, "rhel": 3, ...}
    os_breakdown_json = Column(Text, nullable=True)
    # JSON: {"online": 18, "offline": 2}
    status_breakdown_json = Column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_federation_host_rollup_site_snapshot",
            "site_id",
            "snapshot_at",
        ),
    )


class FederationComplianceRollup(Base):
    """Aggregate compliance scores per site per baseline.

    A site can be evaluated against multiple compliance baselines
    (CIS, STIG, vendor-specific) — one row per (site, baseline,
    snapshot).
    """

    __tablename__ = "federation_compliance_rollup"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    site_id = Column(
        GUID(),
        ForeignKey(_FK_FEDERATION_SITES_ID, ondelete="CASCADE"),
        nullable=False,
    )
    baseline = Column(String(64), nullable=False)
    snapshot_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    # Aggregate compliance score, 0.0-100.0.  NULL when the baseline
    # produced no hosts in scope.
    score_percent = Column(Float, nullable=True)
    hosts_in_scope = Column(Integer, nullable=False, default=0)
    hosts_compliant = Column(Integer, nullable=False, default=0)
    hosts_noncompliant = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "ix_federation_compliance_rollup_site_baseline_snapshot",
            "site_id",
            "baseline",
            "snapshot_at",
        ),
    )


class FederationVulnerabilityRollup(Base):
    """Aggregate CVE exposure per site, sampled at ``snapshot_at``.

    Buckets by CVSSv3 severity (or v2 fallback).  ``top_cve_ids_json``
    is a small denormalized list of the highest-impact open CVEs at
    the site, used by the Sites page card to show "biggest current
    fire" without joining across detail tables.
    """

    __tablename__ = "federation_vulnerability_rollup"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    site_id = Column(
        GUID(),
        ForeignKey(_FK_FEDERATION_SITES_ID, ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    critical_count = Column(Integer, nullable=False, default=0)
    high_count = Column(Integer, nullable=False, default=0)
    medium_count = Column(Integer, nullable=False, default=0)
    low_count = Column(Integer, nullable=False, default=0)
    affected_host_count = Column(Integer, nullable=False, default=0)
    # JSON: ["CVE-2026-1234", ...] (typically 5-10 entries)
    top_cve_ids_json = Column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_federation_vulnerability_rollup_site_snapshot",
            "site_id",
            "snapshot_at",
        ),
    )


class FederationPolicy(Base):
    """Centrally defined policy that the coordinator pushes to sites.

    Polymorphic by ``policy_type`` (update_profile, firewall_role,
    compliance_baseline, ...) with the type-specific body serialised
    into ``definition_json``.  Sites apply policies in version order
    (the highest ``version`` they've received for a given
    ``policy_id`` wins).
    """

    __tablename__ = "federation_policies"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    policy_type = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # JSON body — shape depends on ``policy_type``.
    definition_json = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    updated_at = Column(
        DateTime, nullable=False, default=_utcnow_naive, onupdate=_utcnow_naive
    )
    # ``True`` once an admin disables the policy — sites are notified
    # on next sync to stop applying it, but the row stays for audit.
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_federation_policies_type_active", "policy_type", "is_active"),
        UniqueConstraint(
            "policy_type", "name", name="uq_federation_policies_type_name"
        ),
    )


class FederationPolicyAssignment(Base):
    """Which sites a given policy is assigned to, plus push status.

    Composite-PK (policy_id, site_id) so re-assigning the same policy
    to a site is an UPSERT on push status rather than an INSERT
    explosion.
    """

    __tablename__ = "federation_policy_assignments"

    policy_id = Column(
        GUID(),
        ForeignKey(_FK_FEDERATION_POLICIES_ID, ondelete="CASCADE"),
        primary_key=True,
    )
    site_id = Column(
        GUID(),
        ForeignKey(_FK_FEDERATION_SITES_ID, ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    assigned_by = Column(String(255), nullable=True)
    # pending / pushed / acknowledged / error / dead
    # ``dead`` = exceeded ``MAX_ATTEMPTS``; the push worker skips it
    # until operator intervention resets ``push_status='pending'``
    # via a re-assignment.
    push_status = Column(String(32), nullable=False, default="pending")
    last_push_attempt_at = Column(DateTime, nullable=True)
    last_push_error = Column(Text, nullable=True)
    # Phase 12.10 hardening: push attempt counter for backoff +
    # dead-letter.  Bumps on every transport attempt regardless of
    # outcome; reset to 0 only by explicit operator action
    # (re-assignment).
    push_attempts = Column(Integer, nullable=False, default=0)
    # The version of ``federation_policies.version`` that was last
    # successfully pushed to this site — lets the coordinator detect
    # when a policy edit needs to be re-pushed.
    pushed_version = Column(Integer, nullable=True)

    __table_args__ = (Index("ix_federation_policy_assignments_status", "push_status"),)


class FederationDispatchedCommand(Base):
    """Tracks a command the coordinator dispatched to one or more sites.

    The coordinator never talks to agents directly; it dispatches
    a command to the site, which queues it for the target agent(s)
    and reports back as agents complete.

    ``target_host_ids_json`` is a JSON list of host UUIDs at the
    site; an empty list means "all hosts at this site".
    """

    __tablename__ = "federation_dispatched_commands"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    command_type = Column(String(64), nullable=False)
    # JSON serialized command parameters — shape depends on
    # ``command_type``.
    parameters_json = Column(Text, nullable=True)
    target_site_id = Column(
        GUID(),
        ForeignKey(_FK_FEDERATION_SITES_ID, ondelete="CASCADE"),
        nullable=False,
    )
    # JSON list of host UUIDs at the site, or empty for "all hosts".
    target_host_ids_json = Column(Text, nullable=True)
    dispatched_by = Column(String(255), nullable=True)
    dispatched_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    # queued_at_site / in_progress / partial / completed / failed
    status = Column(String(32), nullable=False, default="queued_at_site")
    result_summary = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    # Phase 12.10 hardening: push retry tracking.  ``push_attempts``
    # increments on every coordinator push attempt regardless of
    # outcome; the backoff filter on ``list_dispatched_commands(..., ready_only=True)``
    # checks ``last_push_attempt_at + compute_backoff(push_attempts) <= now``
    # so failures naturally back off rather than hammering every tick.
    push_attempts = Column(Integer, nullable=False, default=0)
    last_push_attempt_at = Column(DateTime, nullable=True)
    last_push_error = Column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_federation_dispatched_commands_site_status",
            "target_site_id",
            "status",
        ),
        Index(
            "ix_federation_dispatched_commands_dispatched_at",
            "dispatched_at",
        ),
    )


class FederationAuditLog(Base):
    """Every cross-site operation logged centrally.

    Distinct from the per-site audit log (which stays at the site).
    Federation events include enrollment, site removal/suspension,
    policy push, command dispatch, and policy edits.
    """

    __tablename__ = "federation_audit_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    operation = Column(String(64), nullable=False)
    actor_userid = Column(String(255), nullable=True)
    target_site_id = Column(GUID(), nullable=True)
    target_host_id = Column(GUID(), nullable=True)
    # JSON object — operation-specific structured details.
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow_naive)

    __table_args__ = (
        Index("ix_federation_audit_log_created_at", "created_at"),
        Index(
            "ix_federation_audit_log_operation_created",
            "operation",
            "created_at",
        ),
        Index(
            "ix_federation_audit_log_target_site",
            "target_site_id",
            "created_at",
        ),
    )


class FederationAlert(Base):
    """A SITE-scoped alert fired on a cross-site rollup condition.

    Distinct from the host-scoped ``alert`` table (which requires a
    ``host_id``) — these have only a ``site_id``.  An alert stays OPEN
    (``resolved=False``) while its condition holds and auto-resolves
    when the condition clears; the operator can also acknowledge it.
    There is at most one open alert per (site, condition).
    """

    __tablename__ = "federation_alert"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    site_id = Column(
        GUID(),
        ForeignKey("federation_sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # site_offline | compliance_below | vulnerabilities_high
    condition = Column(String(64), nullable=False)
    severity = Column(String(20), nullable=False)  # warning | critical
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    details_json = Column(Text, nullable=True)
    triggered_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime, nullable=True)
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_federation_alert_resolved", "resolved"),)


class FederationAlertConfig(Base):
    """Singleton row: operator-configured thresholds for the three built-in
    rollup-alert conditions (Phase 12.1 follow-up).

    Fixed PK (``SINGLETON_FEDERATION_ALERT_CONFIG_ID``) so the coordinator
    upserts by PK.  All columns are nullable — a NULL means "use the
    built-in default" so an operator can override just the one threshold
    they care about and leave the rest on defaults.
    """

    __tablename__ = "federation_alert_config"

    id = Column(
        GUID(),
        primary_key=True,
        default=lambda: SINGLETON_FEDERATION_ALERT_CONFIG_ID,
    )
    # site_offline: fire when last_sync age exceeds
    # max(sync_interval × multiplier, min_offline_seconds).
    offline_multiplier = Column(Integer, nullable=True)
    min_offline_seconds = Column(Integer, nullable=True)
    # compliance_below: fire when a baseline score drops under this percent.
    compliance_threshold = Column(Float, nullable=True)
    # vulnerabilities_high: fire when critical_count strictly exceeds this.
    critical_cve_threshold = Column(Integer, nullable=True)
    updated_at = Column(
        DateTime, nullable=False, default=_utcnow_naive, onupdate=_utcnow_naive
    )


class FederationSiteSyncEvent(Base):
    """Coordinator-side time-series of a subordinate site's sync attempts.

    One row per upstream sync the coordinator receives from a site (plus
    the metadata report that rides along).  Powers the per-site
    "sync status timeline" (latency / queue-depth / host-count over time)
    on SiteDetail.  Pruned like the rollup series — capped per site and by
    age — so the table can't grow without bound on a busy fleet.
    """

    __tablename__ = "federation_site_sync_event"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    site_id = Column(
        GUID(),
        ForeignKey("federation_sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recorded_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    # success | error — mirrors ``federation_sites.last_sync_status``.
    sync_status = Column(String(32), nullable=False)
    # Round-trip latency the site reported for this sync, if known.
    latency_ms = Column(Integer, nullable=True)
    # Site-side outbound queue depth at sync time (backlog indicator).
    queue_depth = Column(Integer, nullable=True)
    # Host count the site advertised in this sync's metadata.
    host_count = Column(Integer, nullable=True)

    __table_args__ = (
        Index(
            "ix_federation_site_sync_event_site_recorded",
            "site_id",
            "recorded_at",
        ),
    )


# =====================================================================
# Site-side tables
# =====================================================================


class FederationCoordinator(Base):
    """Singleton row: this site's connection to its coordinator.

    A site connects to exactly one coordinator at a time.  The row
    has a fixed UUID (``SINGLETON_FEDERATION_COORDINATOR_ID``) so
    site code can upsert by PK rather than SELECT-then-INSERT.
    """

    __tablename__ = "federation_coordinator"

    id = Column(
        GUID(),
        primary_key=True,
        default=lambda: SINGLETON_FEDERATION_COORDINATOR_ID,
    )
    coordinator_url = Column(String(512), nullable=True)
    coordinator_tls_cert_pem = Column(Text, nullable=True)
    # The site_id the coordinator assigned us at enrollment time.
    site_id = Column(GUID(), nullable=True)
    # Our own TLS leaf cert that the coordinator pinned at enrollment.
    site_tls_cert_pem = Column(Text, nullable=True)
    # Phase 12.10 Slice 2: plaintext bearer this site presents on every
    # outbound sync POST.  Distinct from the coordinator's per-site
    # ``federation_sites.sync_bearer_token_hash`` (which only keeps the
    # SHA-256) — the site MUST hold the literal value because every
    # outbound HTTP request needs the original ``Authorization: Bearer
    # <token>`` header.  Rotation replaces this value via the
    # enrollment refresh flow.
    sync_bearer_token = Column(Text, nullable=True)
    # Phase 12.10 Slice 3: SHA-256 of the bearer the COORDINATOR
    # presents when it pushes policy versions / dispatched commands
    # INTO this site (the reverse direction of ``sync_bearer_token``).
    # The site uses this hash to verify incoming ``/site/policies`` and
    # ``/site/commands`` POSTs.  The plaintext lives on the coordinator
    # in ``federation_sites.coordinator_outbound_bearer_token``.
    coordinator_inbound_bearer_token_hash = Column(String(128), nullable=True)
    # pending / enrolled / suspended / removed
    enrollment_status = Column(String(32), nullable=False, default="pending")
    enrolled_at = Column(DateTime, nullable=True)
    sync_interval_seconds = Column(Integer, nullable=False, default=300)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(32), nullable=True)
    last_sync_error = Column(Text, nullable=True)
    # Phase 12.2: coordinator-connection health.  ``last_sync_at`` records
    # the most recent *attempt* (success or failure); this records the most
    # recent *success* so "how long have we been cut off" survives a run of
    # failures.  ``consecutive_sync_failures`` drives the connection-state
    # classifier and the reconnect backoff.  ``connection_state`` is the
    # derived label the site engine + UI read:
    #   online    — last attempt succeeded
    #   degraded  — 1..(OFFLINE_AFTER_FAILURES-1) consecutive failures
    #   offline   — >= OFFLINE_AFTER_FAILURES failures; site runs in local
    #               autonomy mode (agents keep reporting, upgrades keep
    #               running, deltas keep queuing for replay on reconnect)
    #   unknown   — never attempted a sync yet
    # ``next_reconnect_at`` is the backoff gate: the outbound tick skips
    # contacting the coordinator until this time passes, so a hard-down
    # coordinator isn't hammered every interval.
    last_successful_sync_at = Column(DateTime, nullable=True)
    consecutive_sync_failures = Column(Integer, nullable=False, default=0)
    connection_state = Column(String(16), nullable=False, default="unknown")
    next_reconnect_at = Column(DateTime, nullable=True)


class FederationSyncQueue(Base):
    """Site-side outbox: pending deltas to push to the coordinator.

    The site appends to this queue as local state changes (host
    registered, deactivated, IP changed, OS upgraded, tags edited,
    geo recomputed).  A background worker drains it on
    ``sync_interval_seconds`` cadence.

    ``dedup_key`` is the ``host_id:field:mtime`` triple from the
    ROADMAP.  On reconnect after an outage the site may re-enqueue
    deltas that were already pushed; the coordinator dedup-keys on
    upsert.  A unique partial index (where supported) makes the
    dedup an O(1) check.
    """

    __tablename__ = "federation_sync_queue"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    # host_delta / compliance_rollup / vulnerability_rollup /
    # audit_entry / heartbeat
    payload_type = Column(String(64), nullable=False)
    # JSON serialized payload — shape depends on ``payload_type``.
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    attempts = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    # Optional dedup key — host-delta entries set this, rollups don't.
    dedup_key = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_federation_sync_queue_created_at", "created_at"),
        Index("ix_federation_sync_queue_payload_type", "payload_type"),
        Index("ix_federation_sync_queue_dedup_key", "dedup_key"),
    )


class FederationReceivedPolicy(Base):
    """Site-side inbox: policies the coordinator has pushed to this site.

    The site applies these to its local state (update profiles
    table, firewall roles table, etc.) and acks back to the
    coordinator.  Rows are retained for audit even after the policy
    is applied.
    """

    __tablename__ = "federation_received_policies"

    # Same UUID as ``federation_policies.id`` at the coordinator — the
    # site identifies a policy by its coordinator-assigned UUID.
    policy_id = Column(GUID(), primary_key=True)
    policy_type = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    definition_json = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    received_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    applied = Column(Boolean, nullable=False, default=False)
    applied_at = Column(DateTime, nullable=True)
    apply_error = Column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_federation_received_policies_type_applied",
            "policy_type",
            "applied",
        ),
    )


class FederationReceivedCommand(Base):
    """Site-side inbox: commands the coordinator dispatched to this site.

    The site queues these for local agents through the existing
    ``MessageQueue`` infrastructure.  Status flows: ``queued`` ->
    ``in_progress`` -> ``completed`` / ``failed``.  Result bodies
    are reported back to the coordinator as deltas in
    ``federation_sync_queue`` with ``payload_type='command_result'``.
    """

    __tablename__ = "federation_received_commands"

    # Same UUID as ``federation_dispatched_commands.id`` at the
    # coordinator.
    id = Column(GUID(), primary_key=True)
    command_type = Column(String(64), nullable=False)
    parameters_json = Column(Text, nullable=True)
    target_host_ids_json = Column(Text, nullable=True)
    received_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    # queued / in_progress / completed / failed
    status = Column(String(32), nullable=False, default="queued")
    result_json = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index(
            "ix_federation_received_commands_status",
            "status",
            "received_at",
        ),
    )
