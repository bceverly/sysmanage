# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
API-test ORM schema mirror, part B (FederationSite .. ExternalIdpSettings).

SQLite-compatible, hand-written mirrors of the production models.  See
``tests/api/conftest.py`` for the full rationale and the maintenance warning.
All classes register on the shared ``TestBase`` from ``_orm_mirror_base`` so
that string-based relationships resolve across the mirror modules.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.persistence.models.core import GUID
from tests.api._orm_mirror_base import TestBase


# Phase 12.6 — federation_sites mirror.  Tests that exercise
# registration-key ``site_id`` validation (Phase 12.4) INSERT
# rows directly via the production SQLAlchemy class, so the
# test schema must include every column the production INSERT
# emits — not just the ones the tests read.  Columns kept in
# lockstep with ``backend/persistence/models/federation.py``.
class FederationSite(TestBase):
    __tablename__ = "federation_sites"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    location_label = Column(String(255), nullable=True)
    url = Column(String(512), nullable=False)
    tls_cert_pem = Column(Text, nullable=True)
    # Phase 12 strict trust — out-of-band identity-key pinning.
    site_identity_public_key_pem = Column(Text, nullable=True)
    enrollment_token_hash = Column(String(128), nullable=True)
    enrollment_token_expires_at = Column(DateTime, nullable=True)
    enrolled_at = Column(DateTime, nullable=True)
    sync_bearer_token_hash = Column(String(128), nullable=True)
    coordinator_outbound_bearer_token = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="enrolled")
    host_count = Column(Integer, nullable=False, default=0)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(32), nullable=True)
    sync_interval_seconds = Column(Integer, nullable=False, default=300)
    # Phase 12.2 — site-reported metadata (lockstep with the real model).
    sysmanage_version = Column(String(32), nullable=True)
    connection_state = Column(String(16), nullable=True)
    capabilities_json = Column(Text, nullable=True)
    last_metadata_at = Column(DateTime, nullable=True)
    agent_version_min = Column(String(32), nullable=True)
    geo_latitude = Column(Float, nullable=True)
    geo_longitude = Column(Float, nullable=True)
    geo_country_code = Column(String(2), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


# Phase 8.1 — access groups + registration keys (test-side mirrors).
class AccessGroup(TestBase):
    __tablename__ = "access_groups"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(
        GUID(),
        ForeignKey("access_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class RegistrationKey(TestBase):
    __tablename__ = "registration_keys"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    key = Column(String(128), nullable=False, unique=True)
    access_group_id = Column(
        GUID(),
        ForeignKey("access_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Phase 12.4: federation-site scope.  No FK constraint here
    # because the test TestBase metadata doesn't include the
    # ``federation_sites`` table — referential integrity is
    # enforced in production via the m1fedschema FK; tests just
    # need the column to exist for SELECT/INSERT.
    site_id = Column(GUID(), nullable=True)
    auto_approve = Column(Boolean, nullable=False, default=False)
    revoked = Column(Boolean, nullable=False, default=False)
    max_uses = Column(Integer, nullable=True)
    use_count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=True)
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)


class HostAccessGroup(TestBase):
    __tablename__ = "host_access_groups"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    access_group_id = Column(
        GUID(),
        ForeignKey("access_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime, nullable=True)


class UserAccessGroup(TestBase):
    __tablename__ = "user_access_groups"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    access_group_id = Column(
        GUID(),
        ForeignKey("access_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    granted_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, nullable=True)


# Phase 8.2 — upgrade profiles (test-side mirror).
class UpgradeProfile(TestBase):
    __tablename__ = "upgrade_profiles"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    cron = Column(String(200), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    last_run = Column(DateTime, nullable=True)
    last_status = Column(String(40), nullable=True)
    next_run = Column(DateTime, nullable=True)
    security_only = Column(Boolean, nullable=False, default=False)
    package_managers = Column(Text, nullable=True)
    staggered_window_min = Column(Integer, nullable=False, default=0)
    tag_id = Column(GUID(), ForeignKey("tags.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


# Phase 11 — air-gap tables (test-side mirrors).  These mirror the
# production models in ``backend/persistence/models/airgap.py`` —
# the api conftest uses its own TestBase metadata so we have to
# redeclare the schema for SQLite parity.
class AirgapCollectionRun(TestBase):
    __tablename__ = "airgap_collection_run"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    iso_label = Column(String(80), nullable=False)
    media_size_bytes = Column(BigInteger, nullable=False, default=4_700_000_000)
    include_cve = Column(Boolean, nullable=False, default=True)
    include_compliance = Column(Boolean, nullable=False, default=True)
    status = Column(String(40), nullable=False, default="QUEUED")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    # Phase 11.1 follow-up — cron_schedule for re-firing runs via tick.
    cron_schedule = Column(String(200), nullable=True)
    # Phase 11 B3 — delta runs reference their parent.  Self-FK
    # mirrors the real schema; included so the API's ORDER BY
    # SELECT doesn't crash against the SQLite test database.
    parent_run_id = Column(
        GUID(),
        ForeignKey("airgap_collection_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, nullable=True)
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    # Phase 12 — orchestrator + optical burn opt-in.  Mirror the real
    # schema or every ``SELECT * FROM airgap_collection_run`` blows
    # up on the test SQLite session with "no such column".
    worker_message_id = Column(String(80), nullable=True)
    burn_device = Column(String(200), nullable=True)


class AirgapCollectionSchedule(TestBase):
    __tablename__ = "airgap_collection_schedule"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, unique=True)
    cron = Column(String(200), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    target_request_json = Column(Text, nullable=False)
    last_run = Column(DateTime, nullable=True)
    last_status = Column(String(40), nullable=True)
    last_run_id = Column(
        GUID(),
        ForeignKey("airgap_collection_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


# Phase 11 — per-distro target rows owned by a collection run.
# The runs cascade-deletes them via the relationship; the table
# must exist or DELETE on the parent row crashes the test session.
class AirgapCollectionTarget(TestBase):
    __tablename__ = "airgap_collection_target"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        GUID(),
        ForeignKey("airgap_collection_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    distro = Column(String(40), nullable=False)
    version = Column(String(40), nullable=False)
    repos = Column(Text, nullable=True)
    byte_count = Column(BigInteger, nullable=True)
    file_count = Column(Integer, nullable=True)
    status = Column(String(40), nullable=True)
    # Phase 12 Option-B — each target binds to a specific mirror
    # and the snapshot of that mirror the orchestrator pinned.
    mirror_id = Column(
        GUID(),
        ForeignKey("mirror_repository.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_snapshot_id = Column(
        GUID(),
        ForeignKey("mirror_snapshot.id", ondelete="SET NULL"),
        nullable=True,
    )


# Phase 11 — produced-media manifests (test-side mirror for the
# collector runs API).  Mirrors backend/persistence/models/airgap.py
# ``AirgapMediaManifest``; columns are kept minimal for SQLite parity.
class AirgapMediaManifest(TestBase):
    __tablename__ = "airgap_media_manifest"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        GUID(),
        ForeignKey("airgap_collection_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    disc_index = Column(Integer, nullable=False, default=1)
    disc_count = Column(Integer, nullable=False, default=1)
    iso_path = Column(String(500), nullable=False)
    iso_sha256 = Column(String(64), nullable=False)
    iso_size_bytes = Column(BigInteger, nullable=False)
    manifest_json = Column(Text, nullable=False)
    signature = Column(Text, nullable=False)
    signer_fingerprint = Column(String(128), nullable=False)
    signature_algorithm = Column(String(40), nullable=False, default="ed25519")
    format_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=True)


# Phase 8.3 — package compliance (test-side mirrors).
from sqlalchemy import (  # pylint: disable=ungrouped-imports
    JSON as _JSON,
)  # local import — only needed here


class PackageProfile(TestBase):
    __tablename__ = "package_profiles"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    constraints = relationship(
        "PackageProfileConstraint",
        cascade="all, delete-orphan",
    )


class PackageProfileConstraint(TestBase):
    __tablename__ = "package_profile_constraints"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        GUID(),
        ForeignKey("package_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    package_name = Column(String(255), nullable=False)
    package_manager = Column(String(60), nullable=True)
    constraint_type = Column(String(20), nullable=False, default="REQUIRED")
    version_op = Column(String(4), nullable=True)
    version = Column(String(120), nullable=True)
    created_at = Column(DateTime, nullable=True)


class HostPackageComplianceStatus(TestBase):
    __tablename__ = "host_package_compliance_status"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    profile_id = Column(
        GUID(),
        ForeignKey("package_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default="PENDING")
    violations = Column(_JSON, nullable=True)
    last_scan_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


# Phase 8.7 — report branding singleton, custom report templates,
# and dynamic-secret leases.
class ReportBranding(TestBase):
    __tablename__ = "report_branding"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    company_name = Column(String(255), nullable=True)
    header_text = Column(String(500), nullable=True)
    logo_data = Column(LargeBinary, nullable=True)
    logo_mime_type = Column(String(80), nullable=True)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )


class ReportTemplate(TestBase):
    __tablename__ = "report_template"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    base_report_type = Column(String(50), nullable=False)
    selected_fields = Column(_JSON, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class AirGapBundle(TestBase):
    __tablename__ = "airgap_bundle"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    product = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="queued")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    file_path = Column(Text, nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    log_path = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    version = Column(String(64), nullable=True)
    created_by_user_id = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )


class DynamicSecretLease(TestBase):
    __tablename__ = "dynamic_secret_lease"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    kind = Column(String(40), nullable=False)
    backend_role = Column(String(255), nullable=False)
    vault_lease_id = Column(String(500), nullable=True)
    ttl_seconds = Column(Integer, nullable=True)
    issued_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")
    secret_metadata = Column(_JSON, nullable=True)
    issued_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    note = Column(Text, nullable=True)


# Phase 10.3: MFA tables.  The login flow queries
# ``user_mfa_enrollment`` on every successful password verify, so
# the table has to exist in the test fixture even for tests that
# don't exercise MFA themselves.
class UserMfaEnrollment(TestBase):
    __tablename__ = "user_mfa_enrollment"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    totp_secret_encrypted = Column(Text, nullable=False)
    backup_codes_hashed = Column(_JSON, nullable=False, default=list)
    enrolled_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    last_used_method = Column(String(20), nullable=True)


class MfaSettings(TestBase):
    __tablename__ = "mfa_settings"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    issuer_name = Column(String(120), nullable=False, default="SysManage")
    totp_digits = Column(Integer, nullable=False, default=6)
    totp_period_seconds = Column(Integer, nullable=False, default=30)
    backup_code_count = Column(Integer, nullable=False, default=10)
    admin_required = Column(Boolean, nullable=False, default=False)
    grace_period_days = Column(Integer, nullable=False, default=14)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(
        GUID(),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )


# Phase 10.4 — repository-mirroring tables.
class MirrorRepository(TestBase):
    __tablename__ = "mirror_repository"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), unique=True, nullable=False)
    package_manager = Column(String(20), nullable=False)
    upstream_url = Column(String(500), nullable=False)
    suite = Column(String(80), nullable=True)
    components = Column(String(200), nullable=True)
    architectures = Column(String(120), nullable=True)
    repoid = Column(String(120), nullable=True)
    gpgkey_url = Column(String(500), nullable=True)
    repo_alias = Column(String(120), nullable=True)
    release = Column(String(80), nullable=True)
    signing_key_url = Column(String(500), nullable=True)
    bandwidth_cap_kbps = Column(Integer, nullable=False, default=0)
    sync_cron = Column(String(120), nullable=False, default="0 4 * * *")
    network_tier = Column(String(40), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform_config_id = Column(
        GUID(),
        ForeignKey("mirror_platform_config.id", ondelete="SET NULL"),
        nullable=True,
    )
    known_version_id = Column(
        GUID(),
        ForeignKey("mirror_known_version.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(40), nullable=True)
    last_sync_error = Column(Text, nullable=True)
    next_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class MirrorKnownVersion(TestBase):
    __tablename__ = "mirror_known_version"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    platform = Column(String(20), nullable=False)
    version_key = Column(String(80), nullable=False)
    label = Column(String(200), nullable=False)
    os_family = Column(String(40), nullable=False)
    match_regex = Column(String(400), nullable=False)
    default_upstream_url = Column(String(500), nullable=False)
    default_suite = Column(String(80), nullable=True)
    default_repoid = Column(String(120), nullable=True)
    default_repo_alias = Column(String(120), nullable=True)
    default_release = Column(String(80), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=True)


class HostDefaultMirror(TestBase):
    __tablename__ = "host_default_mirror"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    platform = Column(String(20), nullable=False)
    version_key = Column(String(80), nullable=False)
    os_family = Column(String(40), nullable=False)
    mirror_id = Column(
        GUID(),
        ForeignKey("mirror_repository.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at = Column(DateTime, nullable=True)


class MirrorPlatformConfig(TestBase):
    __tablename__ = "mirror_platform_config"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    platform = Column(String(20), nullable=False)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    mirror_root_path = Column(String(500), nullable=False, default="/var/mirror")
    integrity_check_cadence_hours = Column(Integer, nullable=False, default=24)
    retention_window_days = Column(Integer, nullable=False, default=30)
    default_bandwidth_cap_kbps = Column(Integer, nullable=False, default=0)
    snapshot_count_to_keep = Column(Integer, nullable=False, default=10)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class MirrorSnapshot(TestBase):
    __tablename__ = "mirror_snapshot"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    repository_id = Column(
        GUID(),
        ForeignKey("mirror_repository.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_id = Column(String(80), nullable=False)
    taken_at = Column(DateTime, nullable=False)
    size_bytes = Column(Integer, nullable=True)
    file_count = Column(Integer, nullable=True)
    manifest = Column(_JSON, nullable=True)
    retention_until = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)


class MirrorSettings(TestBase):
    __tablename__ = "mirror_settings"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    mirror_root_path = Column(String(500), nullable=False, default="/var/mirror")
    integrity_check_cadence_hours = Column(Integer, nullable=False, default=24)
    retention_window_days = Column(Integer, nullable=False, default=30)
    default_bandwidth_cap_kbps = Column(Integer, nullable=False, default=0)
    snapshot_count_to_keep = Column(Integer, nullable=False, default=10)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(
        GUID(),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )


# Phase 10.4.1 — mirror setup status (one row per host).
class MirrorSetupStatus(TestBase):
    __tablename__ = "mirror_setup_status"
    host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="CASCADE"), primary_key=True
    )
    tools = Column(_JSON, nullable=False, default=dict)
    platform = Column(String(40), nullable=True)
    distro = Column(String(40), nullable=True)
    last_check_at = Column(DateTime, nullable=True)
    last_check_message_id = Column(String(36), nullable=True)
    last_check_error = Column(Text, nullable=True)
    install_status = Column(String(20), nullable=False, default="idle")
    last_install_at = Column(DateTime, nullable=True)
    last_install_message_id = Column(String(36), nullable=True)
    last_install_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


# Phase 10.5 — external IdP tables.
class ExternalIdpProvider(TestBase):
    __tablename__ = "external_idp_provider"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), unique=True, nullable=False)
    type = Column(String(20), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    ldap_server_url = Column(String(500), nullable=True)
    ldap_bind_dn = Column(String(500), nullable=True)
    ldap_bind_password_secret_id = Column(String(255), nullable=True)
    ldap_user_search_base = Column(String(500), nullable=True)
    ldap_user_search_filter = Column(String(500), nullable=True)
    ldap_group_search_base = Column(String(500), nullable=True)
    ldap_group_search_filter = Column(String(500), nullable=True)
    ldap_tls_ca_bundle_path = Column(String(500), nullable=True)
    ldap_connection_timeout = Column(Integer, nullable=False, default=10)
    oidc_issuer_url = Column(String(500), nullable=True)
    oidc_client_id = Column(String(255), nullable=True)
    oidc_client_secret_secret_id = Column(String(255), nullable=True)
    oidc_redirect_uri = Column(String(500), nullable=True)
    oidc_scopes = Column(String(500), nullable=False, default="openid profile email")
    oidc_discovery_url = Column(String(500), nullable=True)
    oidc_group_claim = Column(String(120), nullable=False, default="groups")
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class IdpRoleMapping(TestBase):
    __tablename__ = "idp_role_mapping"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    provider_id = Column(
        GUID(),
        ForeignKey("external_idp_provider.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_group = Column(String(500), nullable=False)
    role_name = Column(String(120), nullable=False)
    default_for_unmapped = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=True)


class ExternalIdpSettings(TestBase):
    __tablename__ = "external_idp_settings"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    local_account_fallback = Column(Boolean, nullable=False, default=True)
    max_failed_attempts = Column(Integer, nullable=False, default=5)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(
        GUID(),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
