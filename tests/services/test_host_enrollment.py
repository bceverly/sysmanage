"""
Tests for tenant enrollment-token consumption at host registration (Phase 13.1).

The enrollment logic moved into the licensed engine (Pro+ relocation, Phase 2);
the OSS-side wiring (``host._resolve_enrollment_tenant``) is tested here.  The
no-engine paths (no token / MT off / invalid → None or 403) run always; the
valid-token path exercises the real compiled engine via the shim and skips when
the ``.so`` isn't importable.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api import host as host_api
from backend.multitenancy import seam
from backend.services import enrollment_service


def _tenant(db_session, slug="enroll-reg"):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    t = RegistryTenant(name="Enroll Reg", slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(t)
    db_session.commit()
    return t


@pytest.fixture
def real_engine():
    from tests._engine_loader import require_engine

    mod = require_engine("multitenancy_engine")
    seam.register_engine(MagicMock(), module=mod)
    yield mod
    seam.unregister_engine()


@pytest.fixture(autouse=True)
def _clean_seam():
    # Default to no engine; ``real_engine`` registers one where needed.
    seam.unregister_engine()
    yield
    seam.unregister_engine()


def test_resolve_returns_none_without_token(db_session):
    assert host_api._resolve_enrollment_tenant(None) is None
    assert host_api._resolve_enrollment_tenant("") is None


def test_resolve_ignored_when_multitenancy_disabled(db_session):
    with patch("backend.config.config.is_multitenancy_enabled", return_value=False):
        # When MT is off, any token is ignored (returns None) — the engine is
        # never consulted.
        assert host_api._resolve_enrollment_tenant("sme_anything") is None


def test_resolve_valid_token_returns_tenant_and_consumes(real_engine, db_session):
    tenant = _tenant(db_session)
    plaintext, _row = enrollment_service.generate_token(db_session, tenant.id)
    with patch("backend.config.config.is_multitenancy_enabled", return_value=True):
        resolved = host_api._resolve_enrollment_tenant(plaintext)
    assert resolved == str(tenant.id)
    # One use was consumed (committed by the helper's own registry session;
    # expire our session's identity map so we re-read the fresh value).
    db_session.expire_all()
    assert enrollment_service.list_tokens(db_session, tenant.id)[0].use_count == 1


def test_resolve_invalid_token_rejects(db_session):
    # Invalid token + MT on → the shim returns None (no engine needed) and the
    # registration path rejects with 403.
    with patch("backend.config.config.is_multitenancy_enabled", return_value=True):
        with pytest.raises(HTTPException) as exc:
            host_api._resolve_enrollment_tenant("sme_bogus")
    assert exc.value.status_code == 403
