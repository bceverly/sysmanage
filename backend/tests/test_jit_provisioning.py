# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 13.1.E — JIT provisioning helpers in ``registry_service``.

The security-critical property is **fail-closed**: an SSO identity may only
auto-provision into a tenant when that tenant has an EXPLICIT email-domain
allowlist the address matches.  With no allowlist, JIT must refuse (unlike the
admin-facing ``is_email_domain_allowed``, which treats an empty list as open).
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.tenancy import (
    RegistryTenant,
    RegistryTenantEmailDomain,
    RegistryUser,
    RegistryUserTenantGrant,
)
from backend.services import registry_service

TENANT = uuid.uuid4()


@pytest.fixture
def session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    with sessionmaker(bind=eng)() as s:
        s.add(RegistryTenant(id=TENANT, name="Acme", slug="acme"))
        s.commit()
        yield s
    eng.dispose()


def _add_domain(session, domain):
    session.add(RegistryTenantEmailDomain(tenant_id=TENANT, domain=domain))
    session.commit()


def test_jit_fails_closed_without_allowlist(session):
    # No allowlist rows → JIT refuses (the safe default).
    assert registry_service.jit_domain_permitted(session, TENANT, "x@acme.com") is False


def test_jit_allows_matching_domain(session):
    _add_domain(session, "acme.com")
    assert (
        registry_service.jit_domain_permitted(session, TENANT, "joe@acme.com") is True
    )


def test_jit_rejects_non_matching_domain(session):
    _add_domain(session, "acme.com")
    assert (
        registry_service.jit_domain_permitted(session, TENANT, "joe@evil.com") is False
    )


def test_jit_rejects_blank_email(session):
    _add_domain(session, "acme.com")
    assert registry_service.jit_domain_permitted(session, TENANT, "") is False


def test_ensure_registry_user_is_find_or_create(session):
    u1 = registry_service.ensure_registry_user(session, "Joe@Acme.com")
    session.commit()
    u2 = registry_service.ensure_registry_user(
        session, "joe@acme.com"
    )  # case-insensitive
    assert u1.id == u2.id
    assert u1.email == "joe@acme.com"
    assert session.query(RegistryUser).count() == 1


def test_ensure_grant_is_idempotent(session):
    user = registry_service.ensure_registry_user(session, "joe@acme.com")
    session.commit()
    g1 = registry_service.ensure_grant(session, user.id, TENANT, "member")
    g2 = registry_service.ensure_grant(
        session, user.id, TENANT, "admin"
    )  # already exists
    assert g1.id == g2.id
    assert session.query(RegistryUserTenantGrant).count() == 1
    # The first grant's role is retained (not overwritten) — admin escalation
    # must go through the explicit control-plane path, not a re-login.
    assert g1.role == "member"
