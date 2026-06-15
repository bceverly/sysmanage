"""
Tests for the tenant enrollment-token service (Phase 13.1 data plane).
"""

from datetime import datetime, timedelta, timezone

from backend.services import enrollment_service


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tenant(db_session, slug="enroll-co"):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    tenant = RegistryTenant(name="Enroll Co", slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(tenant)
    db_session.commit()
    return tenant


def test_generate_stores_hash_not_plaintext(db_session):
    tenant = _tenant(db_session)
    plaintext, row = enrollment_service.generate_token(
        db_session, tenant.id, label="laptops"
    )
    assert plaintext.startswith("sme_")
    # Only the hash is stored — never the plaintext.
    assert row.token_hash == enrollment_service.hash_token(plaintext)
    assert plaintext not in (row.token_hash, row.label)
    assert row.label == "laptops"


def test_validate_and_consume_happy_path(db_session):
    tenant = _tenant(db_session)
    plaintext, _ = enrollment_service.generate_token(db_session, tenant.id)
    resolved = enrollment_service.validate_and_consume(db_session, plaintext)
    assert resolved == str(tenant.id)
    # use_count bumped.
    tokens = enrollment_service.list_tokens(db_session, tenant.id)
    assert tokens[0].use_count == 1
    assert tokens[0].last_used_at is not None


def test_validate_unknown_token_returns_none(db_session):
    _tenant(db_session)
    assert enrollment_service.validate_and_consume(db_session, "sme_nope") is None
    assert enrollment_service.validate_and_consume(db_session, "") is None


def test_revoked_token_is_rejected(db_session):
    tenant = _tenant(db_session)
    plaintext, row = enrollment_service.generate_token(db_session, tenant.id)
    assert enrollment_service.revoke_token(db_session, tenant.id, row.id) is True
    assert enrollment_service.validate_and_consume(db_session, plaintext) is None


def test_expired_token_is_rejected(db_session):
    tenant = _tenant(db_session)
    plaintext, _ = enrollment_service.generate_token(
        db_session, tenant.id, expires_at=_utcnow() - timedelta(minutes=1)
    )
    assert enrollment_service.validate_and_consume(db_session, plaintext) is None


def test_max_uses_enforced(db_session):
    tenant = _tenant(db_session)
    plaintext, _ = enrollment_service.generate_token(db_session, tenant.id, max_uses=1)
    assert enrollment_service.validate_and_consume(db_session, plaintext) == str(
        tenant.id
    )
    # Second use exceeds the cap.
    assert enrollment_service.validate_and_consume(db_session, plaintext) is None


def test_revoke_unknown_returns_false(db_session):
    tenant = _tenant(db_session)
    assert enrollment_service.revoke_token(db_session, tenant.id, "no-such-id") is False
