# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the tenant migration-status detector (Pro+ relocation, Phase 2).

The detection logic moved into the licensed engine; the OSS module is a thin
shim.  No-engine returns the empty result (always run); behavioral tests run
against the real compiled engine (skip-tolerant), patching the engine's chain
head.
"""

from unittest.mock import patch

from backend.services import migration_status


def _tenant(db_session, slug):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    t = RegistryTenant(name=slug.title(), slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(t)
    db_session.commit()
    return t


def _set_version(db_session, tenant_id, revision):
    from backend.persistence.models import RegistryTenantDbVersion

    db_session.add(
        RegistryTenantDbVersion(tenant_id=tenant_id, chain="tenant", revision=revision)
    )
    db_session.commit()


# --- shim contract (no engine → empty) ---


def test_no_engine_returns_empty(db_session):
    res = migration_status.pending_tenant_migrations()
    assert res == {"tenants_pending": 0, "tenant_slugs": [], "tenant_head": None}


# --- behavioral against the real compiled engine ---


def test_flags_tenant_behind_head(real_engine, db_session):
    up = _tenant(db_session, "uptodate")
    behind = _tenant(db_session, "behind")
    _tenant(db_session, "never")  # no db_version row → also pending
    _set_version(db_session, up.id, "HEAD9")
    _set_version(db_session, behind.id, "OLD1")

    with patch.object(real_engine, "_tenant_chain_head", return_value="HEAD9"):
        res = migration_status.pending_tenant_migrations()

    assert res["tenant_head"] == "HEAD9"
    assert res["tenants_pending"] == 2
    assert set(res["tenant_slugs"]) == {"behind", "never"}


def test_no_false_alarm_when_head_unknown(real_engine, db_session):
    t = _tenant(db_session, "acme")
    _set_version(db_session, t.id, "OLD1")
    with patch.object(real_engine, "_tenant_chain_head", return_value=None):
        res = migration_status.pending_tenant_migrations()
    # Head couldn't be resolved → don't cry wolf.
    assert res["tenants_pending"] == 0
