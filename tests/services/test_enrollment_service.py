# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the tenant enrollment-token OSS shim + the relocated engine logic.

The token logic moved into the licensed engine (Pro+ relocation, Phase 2).  The
OSS module is now a thin shim, so:
  * shim-contract tests (always run) assert the no-engine behavior — CRUD raises,
    the registration read degrades to None;
  * behavioral tests run against the REAL compiled engine via the shim, exercising
    generate/validate/list/revoke against an in-memory registry DB.  They skip
    when the ``.so`` isn't importable (pure OSS CI), so they never couple the OSS
    suite to the Pro+ build.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from backend.multitenancy import seam
from backend.services import enrollment_service


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tenant(db_session, slug="enroll-co"):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    tenant = RegistryTenant(name="Enroll Co", slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(tenant)
    db_session.commit()
    return tenant


# ---------------------------------------------------------------------------
# Shim contract (always runs — no engine)
# ---------------------------------------------------------------------------


@pytest.fixture
def _no_engine():
    seam.unregister_engine()
    yield
    seam.unregister_engine()


def test_crud_requires_engine(_no_engine):
    with pytest.raises(RuntimeError, match="licensed multi-tenancy engine"):
        enrollment_service.generate_token(MagicMock(), "t-1")
    with pytest.raises(RuntimeError, match="licensed multi-tenancy engine"):
        enrollment_service.list_tokens(MagicMock(), "t-1")
    with pytest.raises(RuntimeError, match="licensed multi-tenancy engine"):
        enrollment_service.revoke_token(MagicMock(), "t-1", "tok")


def test_validate_without_engine_returns_none(_no_engine):
    assert enrollment_service.validate_and_consume(MagicMock(), "sme_x") is None
    assert enrollment_service.validate_and_consume(MagicMock(), "") is None


# ---------------------------------------------------------------------------
# Behavioral against the real compiled engine (skips if the .so is absent)
# ---------------------------------------------------------------------------


@pytest.fixture
def real_engine():
    from tests._engine_loader import require_engine

    mod = require_engine("multitenancy_engine")
    seam.register_engine(MagicMock(), module=mod)
    yield mod
    seam.unregister_engine()


def test_generate_stores_hash_not_plaintext(real_engine, db_session):
    tenant = _tenant(db_session)
    plaintext, row = enrollment_service.generate_token(
        db_session, tenant.id, label="laptops"
    )
    assert plaintext.startswith("sme_")
    assert row.token_hash == real_engine.hash_token(plaintext)
    assert plaintext not in (row.token_hash, row.label)
    assert row.label == "laptops"


def test_validate_and_consume_happy_path(real_engine, db_session):
    tenant = _tenant(db_session)
    plaintext, _ = enrollment_service.generate_token(db_session, tenant.id)
    resolved = enrollment_service.validate_and_consume(db_session, plaintext)
    assert resolved == str(tenant.id)
    tokens = enrollment_service.list_tokens(db_session, tenant.id)
    assert tokens[0].use_count == 1
    assert tokens[0].last_used_at is not None


def test_validate_unknown_token_returns_none(real_engine, db_session):
    _tenant(db_session)
    assert enrollment_service.validate_and_consume(db_session, "sme_nope") is None
    assert enrollment_service.validate_and_consume(db_session, "") is None


def test_revoked_token_is_rejected(real_engine, db_session):
    tenant = _tenant(db_session)
    plaintext, row = enrollment_service.generate_token(db_session, tenant.id)
    assert enrollment_service.revoke_token(db_session, tenant.id, row.id) is True
    assert enrollment_service.validate_and_consume(db_session, plaintext) is None


def test_expired_token_is_rejected(real_engine, db_session):
    tenant = _tenant(db_session)
    plaintext, _ = enrollment_service.generate_token(
        db_session, tenant.id, expires_at=_utcnow() - timedelta(minutes=1)
    )
    assert enrollment_service.validate_and_consume(db_session, plaintext) is None


def test_max_uses_enforced(real_engine, db_session):
    tenant = _tenant(db_session)
    plaintext, _ = enrollment_service.generate_token(db_session, tenant.id, max_uses=1)
    assert enrollment_service.validate_and_consume(db_session, plaintext) == str(
        tenant.id
    )
    assert enrollment_service.validate_and_consume(db_session, plaintext) is None


def test_revoke_unknown_returns_false(real_engine, db_session):
    tenant = _tenant(db_session)
    assert enrollment_service.revoke_token(db_session, tenant.id, "no-such-id") is False
