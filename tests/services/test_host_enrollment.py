"""
Tests for tenant enrollment-token consumption at host registration (Phase 13.1).
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import host as host_api
from backend.services import enrollment_service


def _tenant(db_session, slug="enroll-reg"):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    t = RegistryTenant(name="Enroll Reg", slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(t)
    db_session.commit()
    return t


def test_resolve_returns_none_without_token(db_session):
    assert host_api._resolve_enrollment_tenant(None) is None
    assert host_api._resolve_enrollment_tenant("") is None


def test_resolve_ignored_when_multitenancy_disabled(db_session):
    tenant = _tenant(db_session)
    plaintext, _row = enrollment_service.generate_token(db_session, tenant.id)
    with patch("backend.config.config.is_multitenancy_enabled", return_value=False):
        # Even a valid token is ignored when MT is off.
        assert host_api._resolve_enrollment_tenant(plaintext) is None


def test_resolve_valid_token_returns_tenant_and_consumes(db_session):
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
    with patch("backend.config.config.is_multitenancy_enabled", return_value=True):
        with pytest.raises(HTTPException) as exc:
            host_api._resolve_enrollment_tenant("sme_bogus")
    assert exc.value.status_code == 403
