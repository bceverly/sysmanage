"""
End-to-end integration tests for the Phase 12.10 Slice 3 coordinator
→ site push worker.

The worker lives in the Pro+ ``federation_controller_engine`` Cython
module; these tests import the compiled ``.so`` directly from the
Pro+ repo's ``storage/modules/`` tree, drive its ``_push_once``
coroutine against a real in-memory SQLite + a mocked
``httpx.AsyncClient``, and verify policy + command push routing,
auth header, failure handling, and FSM transitions.

Skipped automatically when the engine ``.so`` isn't on disk.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access,redefined-outer-name

import importlib.util
import json
import logging
import sys
import sysconfig
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import (
    FederationDispatchedCommand,
    FederationPolicy,
    FederationPolicyAssignment,
    FederationSite,
)
from backend.services import federation_dispatch_service as dispatch_svc
from backend.services import federation_policy_service as policy_svc
from backend.services import federation_site_service as site_svc


def _candidate_so_paths():
    """Mirror of ``test_federation_sync_worker._candidate_so_paths``
    for the controller engine."""
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    home = Path.home()
    candidates = []
    proplus = home / "dev" / "sysmanage-professional-plus" / "storage" / "modules"
    if proplus.exists():
        version_dir = proplus / "federation_controller_engine"
        if version_dir.exists():
            for version in sorted(version_dir.iterdir(), reverse=True):
                py_dir = version / "linux" / "x86_64" / py
                if py_dir.exists():
                    # ONLY match the .so built for THIS interpreter's ABI
                    # (e.g. ``.cpython-314-...so``).  A bare ``*.so`` glob
                    # would sort a stale ``cpython-313`` build ahead of the
                    # correct one and load it, segfaulting on the
                    # compile-time/runtime Python version mismatch.
                    ext = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
                    candidates.extend(sorted(py_dir.glob(f"*{ext}")))
    candidates.append(
        Path("/var/lib/sysmanage/modules") / f"federation_controller_engine_{py}.so"
    )
    return candidates


def _load_engine():
    for path in _candidate_so_paths():
        if path.exists():
            spec = importlib.util.spec_from_file_location(
                "federation_controller_engine", path
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


@pytest.fixture(scope="module")
def engine():
    mod = _load_engine()
    if mod is None:
        pytest.skip(
            "federation_controller_engine .so not available — "
            "build the Pro+ engine first"
        )
    return mod


_FEDERATION_TABLE_NAMES = [
    "federation_sites",
    "federation_host_directory",
    "federation_host_rollup",
    "federation_compliance_rollup",
    "federation_vulnerability_rollup",
    "federation_policies",
    "federation_policy_assignments",
    "federation_dispatched_commands",
    "federation_audit_log",
    "federation_coordinator",
    "federation_sync_queue",
    "federation_received_policies",
    "federation_received_commands",
]


@pytest.fixture
def fed_db():
    sa_engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        sa_engine,
        tables=[Base.metadata.tables[t] for t in _FEDERATION_TABLE_NAMES],
    )
    try:
        yield sa_engine
    finally:
        # ``engine.dispose()`` closes the underlying sqlite3
        # connections so they don't linger in pytest's
        # unraisable-exception handler as ResourceWarnings.
        sa_engine.dispose()


@pytest.fixture
def db_maker(fed_db):
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)

    def factory():
        sess = Session()
        try:
            yield sess
        finally:
            sess.close()

    return factory


def _make_response(status_code, text=""):
    resp = AsyncMock()
    resp.status_code = status_code
    resp.text = text
    return resp


def _seed_enrolled_site(fed_db, name="alpha", url="https://site-alpha.example.com"):
    """Create + enrol a single site row.  Returns ``(site_id, outbound_bearer)``."""
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        site, token = site_svc.create_site(sess, name=name, url=url)
        sess.commit()
        site_obj, _sync_bearer, coord_outbound = site_svc.complete_enrollment(
            sess, plaintext_token=token, tls_cert_pem="cert"
        )
        sess.commit()
        return site_obj.id, coord_outbound


def _assign_policy(fed_db, policy_name, definition, site_ids):
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        policy = policy_svc.create_policy(
            sess,
            policy_type="update_profile",
            name=policy_name,
            definition=definition,
        )
        sess.commit()
        policy_svc.assign_policy_to_sites(sess, policy.id, site_ids, assigned_by="test")
        sess.commit()
        return policy.id


def _dispatch_command(fed_db, site_id, command_type="reboot", parameters=None):
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        cmd = dispatch_svc.dispatch_command(
            sess,
            command_type=command_type,
            target_site_id=site_id,
            parameters=parameters or {},
            target_host_ids=[],
            dispatched_by="test",
        )
        sess.commit()
        return cmd.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_once_idle_when_nothing_pending(engine, db_maker):
    client = AsyncMock()
    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts == {
        "policies_pushed": 0,
        "policies_failed": 0,
        "commands_pushed": 0,
        "commands_failed": 0,
    }
    assert client.post.call_count == 0


@pytest.mark.asyncio
async def test_push_once_delivers_policy_with_bearer(engine, fed_db, db_maker):
    site_id, bearer = _seed_enrolled_site(fed_db)
    _assign_policy(fed_db, "default-update", {"channel": "stable"}, [site_id])

    client = AsyncMock()
    client.post.return_value = _make_response(200)

    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["policies_pushed"] == 1
    assert counts["policies_failed"] == 0
    assert client.post.call_count == 1

    call = client.post.call_args
    assert call.args[0] == (
        "https://site-alpha.example.com/api/v1/federation/site/policies"
    )
    assert call.kwargs["headers"]["Authorization"] == f"Bearer {bearer}"
    # The worker now POSTs the exact JSON bytes via ``content=`` (so it can
    # attach an X-Federation-Signature over those bytes) instead of ``json=``.
    body = json.loads(call.kwargs["content"])
    assert body["policy_type"] == "update_profile"
    assert body["name"] == "default-update"
    assert body["definition"] == {"channel": "stable"}
    assert body["version"] == 1

    # Assignment should now record the push.
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        assignment = sess.query(FederationPolicyAssignment).first()
        assert assignment.push_status == policy_svc.PUSH_STATUS_PUSHED
        assert assignment.pushed_version == 1
        assert assignment.last_push_error is None


@pytest.mark.asyncio
async def test_push_once_records_policy_failure_on_4xx(engine, fed_db, db_maker):
    site_id, _ = _seed_enrolled_site(fed_db)
    _assign_policy(fed_db, "policy-x", {"x": True}, [site_id])

    client = AsyncMock()
    client.post.return_value = _make_response(401, "bearer mismatch")

    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["policies_failed"] == 1
    assert counts["policies_pushed"] == 0

    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        assignment = sess.query(FederationPolicyAssignment).first()
        assert assignment.push_status == policy_svc.PUSH_STATUS_ERROR
        assert "HTTP 401" in (assignment.last_push_error or "")


@pytest.mark.asyncio
async def test_push_once_records_policy_failure_on_network_error(
    engine, fed_db, db_maker
):
    site_id, _ = _seed_enrolled_site(fed_db)
    _assign_policy(fed_db, "policy-net", {}, [site_id])

    client = AsyncMock()
    client.post.side_effect = ConnectionError("site unreachable")

    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["policies_failed"] == 1

    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        assignment = sess.query(FederationPolicyAssignment).first()
        assert assignment.push_status == policy_svc.PUSH_STATUS_ERROR
        assert "http error" in (assignment.last_push_error or "")
        assert "site unreachable" in (assignment.last_push_error or "")


@pytest.mark.asyncio
async def test_push_once_skips_already_pushed_at_current_version(
    engine, fed_db, db_maker
):
    """Once a policy is pushed at its current version, subsequent ticks
    don't re-deliver — that's the whole point of ``pushed_version``."""
    site_id, _ = _seed_enrolled_site(fed_db)
    _assign_policy(fed_db, "stable-policy", {"v": 1}, [site_id])

    client = AsyncMock()
    client.post.return_value = _make_response(200)

    # First tick: pushes.
    counts1 = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts1["policies_pushed"] == 1

    # Second tick: nothing to do.
    client.post.reset_mock()
    counts2 = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts2["policies_pushed"] == 0
    assert client.post.call_count == 0


@pytest.mark.asyncio
async def test_push_once_re_pushes_after_policy_version_bump(engine, fed_db, db_maker):
    """Editing a policy bumps its version; assignments whose
    ``pushed_version`` is now behind get re-pushed."""
    site_id, _ = _seed_enrolled_site(fed_db)
    policy_id = _assign_policy(fed_db, "evolving-policy", {"v": 1}, [site_id])

    client = AsyncMock()
    client.post.return_value = _make_response(200)

    # Initial push at version 1.
    await engine._push_once(db_maker, client, logging.getLogger("test"))

    # Bump the policy.
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        policy_svc.update_policy(
            sess, policy_id, definition={"v": 2}, actor_userid="test"
        )
        sess.commit()

    client.post.reset_mock()
    client.post.return_value = _make_response(200)
    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["policies_pushed"] == 1
    # Payload reflects the new version.
    assert json.loads(client.post.call_args.kwargs["content"])["version"] == 2


@pytest.mark.asyncio
async def test_push_once_skips_inactive_policies(engine, fed_db, db_maker):
    site_id, _ = _seed_enrolled_site(fed_db)
    policy_id = _assign_policy(fed_db, "dead-policy", {}, [site_id])

    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        policy_svc.deactivate_policy(sess, policy_id, actor_userid="test")
        sess.commit()

    client = AsyncMock()
    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["policies_pushed"] == 0
    assert client.post.call_count == 0


@pytest.mark.asyncio
async def test_push_once_skips_sites_without_outbound_bearer(engine, fed_db, db_maker):
    """Sites whose ``coordinator_outbound_bearer_token`` is NULL
    (legacy enrollment that pre-dates Slice 3) are skipped silently
    rather than 500'd on with a missing-creds error."""
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        site, token = site_svc.create_site(
            sess, name="legacy", url="https://legacy.example.com"
        )
        sess.commit()
        site_obj, _b, _c = site_svc.complete_enrollment(
            sess, plaintext_token=token, tls_cert_pem="cert"
        )
        # Simulate a legacy row by NULLing the outbound bearer.
        site_obj.coordinator_outbound_bearer_token = None
        sess.commit()
        site_id = site_obj.id

    _assign_policy(fed_db, "any-policy", {}, [site_id])

    client = AsyncMock()
    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["policies_pushed"] == 0
    assert counts["policies_failed"] == 0  # silent skip, not failure
    assert client.post.call_count == 0


@pytest.mark.asyncio
async def test_push_once_skips_suspended_sites(engine, fed_db, db_maker):
    """``status='suspended'`` sites stop receiving pushes immediately —
    operator must explicitly resume them."""
    site_id, _ = _seed_enrolled_site(fed_db)
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        site_svc.suspend_site(sess, site_id, actor_userid="test")
        sess.commit()

    _assign_policy(fed_db, "policy-suspend-test", {}, [site_id])

    client = AsyncMock()
    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["policies_pushed"] == 0
    assert client.post.call_count == 0


@pytest.mark.asyncio
async def test_push_once_delivers_command_and_advances_to_in_progress(
    engine, fed_db, db_maker
):
    site_id, bearer = _seed_enrolled_site(fed_db)
    cmd_id = _dispatch_command(fed_db, site_id, "run_script", {"script": "df -h"})

    client = AsyncMock()
    client.post.return_value = _make_response(200)

    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["commands_pushed"] == 1
    assert counts["commands_failed"] == 0

    call = client.post.call_args
    assert call.args[0] == (
        "https://site-alpha.example.com/api/v1/federation/site/commands"
    )
    assert call.kwargs["headers"]["Authorization"] == f"Bearer {bearer}"
    body = json.loads(call.kwargs["content"])
    assert body["command_id"] == str(cmd_id)
    assert body["command_type"] == "run_script"
    assert body["parameters"] == {"script": "df -h"}

    # FSM advanced queued_at_site → in_progress on success.
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        cmd = sess.query(FederationDispatchedCommand).first()
        assert cmd.status == dispatch_svc.STATUS_IN_PROGRESS


@pytest.mark.asyncio
async def test_push_once_leaves_command_queued_on_failure(engine, fed_db, db_maker):
    """Push failure → FSM stays at queued_at_site so the next tick
    retries.  No transition to ``failed`` purely on transport — that
    would require operator-visible intervention."""
    site_id, _ = _seed_enrolled_site(fed_db)
    _dispatch_command(fed_db, site_id)

    client = AsyncMock()
    client.post.return_value = _make_response(502, "gateway timeout")

    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["commands_pushed"] == 0
    assert counts["commands_failed"] == 1

    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        cmd = sess.query(FederationDispatchedCommand).first()
        assert cmd.status == dispatch_svc.STATUS_QUEUED_AT_SITE


@pytest.mark.asyncio
async def test_push_once_routes_to_correct_site_per_assignment(
    engine, fed_db, db_maker
):
    """Two sites with different policy assignments → two distinct
    POSTs, each to the correct site URL with that site's bearer."""
    site_a, bearer_a = _seed_enrolled_site(
        fed_db, name="alpha", url="https://site-a.example.com"
    )
    site_b, bearer_b = _seed_enrolled_site(
        fed_db, name="bravo", url="https://site-b.example.com"
    )
    _assign_policy(fed_db, "policy-a-only", {"a": 1}, [site_a])
    _assign_policy(fed_db, "policy-b-only", {"b": 1}, [site_b])

    client = AsyncMock()
    client.post.return_value = _make_response(200)

    counts = await engine._push_once(db_maker, client, logging.getLogger("test"))
    assert counts["policies_pushed"] == 2

    url_to_bearer = {}
    for call in client.post.call_args_list:
        url_to_bearer[call.args[0]] = call.kwargs["headers"]["Authorization"]
    assert (
        url_to_bearer["https://site-a.example.com/api/v1/federation/site/policies"]
        == f"Bearer {bearer_a}"
    )
    assert (
        url_to_bearer["https://site-b.example.com/api/v1/federation/site/policies"]
        == f"Bearer {bearer_b}"
    )
