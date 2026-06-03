"""Tests for the site-side federation policy-apply worker (Phase 12.2)."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models
from backend.services import federation_inbox_service as inbox_svc
from backend.services import federation_policy_apply_service as apply_svc


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine, checkfirst=True)
    testing_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sess = testing_local()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _receive_policy(session, *, policy_type, name, definition, version=1):
    policy = inbox_svc.receive_policy(
        session,
        policy_id=uuid.uuid4(),
        policy_type=policy_type,
        name=name,
        definition=definition,
        version=version,
    )
    # Commit: in production a received policy is persisted by the inbox
    # handler in a prior tick before the apply worker runs.
    session.commit()
    return policy


def _role(session, name):
    return (
        session.query(models.FirewallRole)
        .filter(models.FirewallRole.name == name)
        .first()
    )


def test_apply_firewall_role_creates_role_and_ports(session):
    _receive_policy(
        session,
        policy_type="firewall_role",
        name="web",
        definition={
            "name": "web",
            "open_ports": [
                {"port_number": 80, "tcp": True},
                {"port_number": 443, "tcp": True},
            ],
        },
    )

    summary = apply_svc.apply_pending_policies(session)

    assert summary == {"applied": 1, "failed": 0}
    role = _role(session, "web")
    assert role is not None
    assert sorted(p.port_number for p in role.open_ports) == [80, 443]


def test_apply_marks_inbox_applied(session):
    policy = _receive_policy(
        session,
        policy_type="firewall_role",
        name="ssh",
        definition={"name": "ssh", "open_ports": [22]},
    )

    apply_svc.apply_pending_policies(session)

    refreshed = inbox_svc.get_received_policy(session, policy.policy_id)
    assert refreshed.applied is True
    assert refreshed.apply_error is None
    # Bare-int port form is coerced to a tcp/both-family port.
    port = _role(session, "ssh").open_ports[0]
    assert (port.port_number, port.tcp, port.ipv4, port.ipv6) == (22, True, True, True)


def test_reapply_replaces_port_set(session):
    _receive_policy(
        session,
        policy_type="firewall_role",
        name="db",
        definition={"name": "db", "open_ports": [5432]},
    )
    apply_svc.apply_pending_policies(session)

    # A newer version arrives narrowing the port set; receive_policy
    # resets applied=False, so the next tick re-applies.
    _receive_policy(
        session,
        policy_type="firewall_role",
        name="db",
        definition={"name": "db", "open_ports": [5433]},
        version=2,
    )
    apply_svc.apply_pending_policies(session)

    role = _role(session, "db")
    assert [p.port_number for p in role.open_ports] == [5433]
    # No duplicate role rows.
    assert (
        session.query(models.FirewallRole)
        .filter(models.FirewallRole.name == "db")
        .count()
        == 1
    )


def test_unknown_policy_type_records_error_and_retries(session):
    policy = _receive_policy(
        session,
        policy_type="update_profile",
        name="nightly",
        definition={"schedule": "0 3 * * *"},
    )

    summary = apply_svc.apply_pending_policies(session)

    assert summary == {"applied": 0, "failed": 1}
    refreshed = inbox_svc.get_received_policy(session, policy.policy_id)
    assert refreshed.applied is False
    assert "no local applier" in refreshed.apply_error
    # Still unapplied → eligible for the next tick.
    assert refreshed in inbox_svc.list_unapplied_policies(session)


def test_bad_definition_is_failed_not_applied(session):
    policy = _receive_policy(
        session,
        policy_type="firewall_role",
        name="bad",
        definition={"open_ports": [80]},  # missing 'name'
    )

    summary = apply_svc.apply_pending_policies(session)

    assert summary == {"applied": 0, "failed": 1}
    refreshed = inbox_svc.get_received_policy(session, policy.policy_id)
    assert refreshed.applied is False
    assert "name" in refreshed.apply_error
    assert _role(session, "bad") is None


def test_invalid_port_range_fails(session):
    _receive_policy(
        session,
        policy_type="firewall_role",
        name="oob",
        definition={"name": "oob", "open_ports": [{"port_number": 99999}]},
    )

    summary = apply_svc.apply_pending_policies(session)
    assert summary["failed"] == 1
    assert _role(session, "oob") is None


def test_supported_policy_types_lists_firewall_role(session):  # noqa: ARG001
    assert "firewall_role" in apply_svc.supported_policy_types()
