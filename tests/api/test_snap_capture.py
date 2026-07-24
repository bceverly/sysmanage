# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Snap-capture tests for the repository-mirroring API (Phase 17.1, Slice 3).

Tracks snaps against a mirror and dispatches a snap_proxy_engine capture plan
(blob + assertion) into the mirror pipeline.  Covers: the 402 license gate,
track/list/untrack, the capture dispatch (per-channel grouping merged into one
plan + rows flipped DISPATCHED), and the result handler that flips the tracked
rows CAPTURED / FAILED.
"""

# pylint: disable=missing-function-docstring,redefined-outer-name,protected-access

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import repository_mirroring
from backend.api import repository_mirroring_helpers as helpers
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.persistence import models
from backend.persistence.db import Base
from backend.persistence.partitions import get_tenant_db
from backend.services import repo_mirror_result_handlers as rmrh

_MIRRORS = "/api/v1/mirror-repositories"


class _FakeSnapEngine:
    class SnapProxyError(Exception):
        pass

    def __init__(self):
        self.calls = []

    def build_snap_capture_plan(self, mirror_root, mirror_name, snaps, channel):
        self.calls.append((mirror_root, mirror_name, tuple(snaps), channel))
        return {
            "engine": "snap_proxy_engine",
            "action": "snap_capture",
            "files": [],
            "commands": [
                {"argv": ["sudo", "snap", "download", s, f"--channel={channel}"]}
                for s in snaps
            ],
        }


@pytest.fixture
def env():
    tenant_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        tenant_engine,
        tables=[
            models.MirrorRepository.__table__,
            models.MirrorSettings.__table__,
            models.MirrorSnapContent.__table__,
        ],
    )
    tenant_s = sessionmaker(bind=tenant_engine)

    app = FastAPI()
    app.include_router(repository_mirroring.router, prefix="/api/v1")

    def _tenant():
        db = tenant_s()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_tenant_db] = _tenant
    app.dependency_overrides[get_current_user] = lambda: "test-user"

    async def _bypass_auth(self, request: Request):
        return "test-user"

    dispatched = {}

    def _fake_enqueue(host_id, plan, timeout=300):
        dispatched.update(host_id=str(host_id), plan=plan)
        return "msg-snap"

    def _fake_register(message_id, action, host_id, mirror_id=""):
        dispatched.update(action=action, ref=mirror_id)

    engine = _FakeSnapEngine()
    modules = {"snap_proxy_engine": engine}

    with patch.object(
        helpers.module_loader, "get_module", side_effect=modules.get
    ), patch.object(JWTBearer, "__call__", _bypass_auth), patch(
        "backend.services.proplus_dispatch.enqueue_apply_plan", _fake_enqueue
    ), patch(
        "backend.services.proplus_dispatch.register_repo_mirror_correlation",
        _fake_register,
    ):
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                tenant_s=tenant_s,
                dispatched=dispatched,
                engine=engine,
                modules=modules,
            )
    tenant_engine.dispose()


def _seed_mirror(env, host=None):
    host = host or str(uuid.uuid4())
    tdb = env.tenant_s()
    try:
        tdb.add(models.MirrorSettings(mirror_root_path="/var/mirror"))
        mirror = models.MirrorRepository(
            name="ubuntu-noble",
            package_manager="apt",
            upstream_url="http://u/",
            host_id=host,
        )
        tdb.add(mirror)
        tdb.flush()
        mid = str(mirror.id)
        tdb.commit()
        return mid
    finally:
        tdb.close()


# --------------------------------------------------------------------- gate


def test_gate_402_when_unlicensed(env):
    env.modules.clear()  # snap_proxy_engine not loaded
    mid = _seed_mirror(env)
    r = env.client.get(f"{_MIRRORS}/{mid}/snaps")
    assert r.status_code == 402


# --------------------------------------------------------------------- track


def test_track_snap_creates_row(env):
    mid = _seed_mirror(env)
    r = env.client.post(
        f"{_MIRRORS}/{mid}/snaps", json={"snap_name": "hello", "channel": "latest/edge"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["snap_name"] == "hello"
    assert body["channel"] == "latest/edge"
    assert body["capture_status"] == "TRACKED"


def test_track_snap_default_channel(env):
    mid = _seed_mirror(env)
    r = env.client.post(f"{_MIRRORS}/{mid}/snaps", json={"snap_name": "core20"})
    assert r.status_code == 200
    assert r.json()["channel"] == "latest/stable"


def test_track_snap_idempotent_updates_channel(env):
    mid = _seed_mirror(env)
    env.client.post(f"{_MIRRORS}/{mid}/snaps", json={"snap_name": "hello"})
    r = env.client.post(
        f"{_MIRRORS}/{mid}/snaps",
        json={"snap_name": "hello", "channel": "18/stable"},
    )
    assert r.status_code == 200
    assert r.json()["channel"] == "18/stable"
    listed = env.client.get(f"{_MIRRORS}/{mid}/snaps").json()
    assert len(listed) == 1  # not duplicated


def test_track_snap_rejects_bad_name(env):
    mid = _seed_mirror(env)
    r = env.client.post(f"{_MIRRORS}/{mid}/snaps", json={"snap_name": "Bad;Name"})
    assert r.status_code == 422  # pydantic pattern


def test_track_snap_mirror_404(env):
    r = env.client.post(f"{_MIRRORS}/{uuid.uuid4()}/snaps", json={"snap_name": "hello"})
    assert r.status_code == 404


# ------------------------------------------------------------- list / untrack


def test_list_and_untrack(env):
    mid = _seed_mirror(env)
    env.client.post(f"{_MIRRORS}/{mid}/snaps", json={"snap_name": "hello"})
    env.client.post(f"{_MIRRORS}/{mid}/snaps", json={"snap_name": "core20"})
    listed = env.client.get(f"{_MIRRORS}/{mid}/snaps").json()
    assert {s["snap_name"] for s in listed} == {"hello", "core20"}

    snap_id = listed[0]["id"]
    r = env.client.delete(f"{_MIRRORS}/{mid}/snaps/{snap_id}")
    assert r.status_code == 200
    remaining = env.client.get(f"{_MIRRORS}/{mid}/snaps").json()
    assert len(remaining) == 1


# --------------------------------------------------------------------- capture


def test_capture_dispatches_merged_plan(env):
    mid = _seed_mirror(env)
    # Two channels -> two engine calls -> merged into one dispatched plan.
    env.client.post(
        f"{_MIRRORS}/{mid}/snaps",
        json={"snap_name": "hello", "channel": "latest/stable"},
    )
    env.client.post(
        f"{_MIRRORS}/{mid}/snaps",
        json={"snap_name": "core20", "channel": "latest/edge"},
    )
    r = env.client.post(f"{_MIRRORS}/{mid}/capture-snaps")
    assert r.status_code == 200
    body = r.json()
    assert body["snap_count"] == 2
    assert body["message_id"] == "msg-snap"

    # engine called once per distinct channel; commands merged into one plan.
    assert len(env.engine.calls) == 2
    assert env.dispatched["action"] == "snap_capture"
    assert env.dispatched["ref"] == mid
    assert len(env.dispatched["plan"]["commands"]) == 2

    # rows flipped to DISPATCHED with the in-flight message id.
    listed = env.client.get(f"{_MIRRORS}/{mid}/snaps").json()
    assert all(s["capture_status"] == "DISPATCHED" for s in listed)


def test_capture_400_when_no_snaps(env):
    mid = _seed_mirror(env)
    r = env.client.post(f"{_MIRRORS}/{mid}/capture-snaps")
    assert r.status_code == 400


# --------------------------------------------------------------- result handler


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ({"status": "succeeded"}, "CAPTURED"),
        (
            {"status": "failed", "error": "boom", "stderr": "boom", "stdout": ""},
            "FAILED",
        ),
    ],
)
def test_result_handler_flips_rows(env, outcome, expected):
    mid = _seed_mirror(env)
    tdb = env.tenant_s()
    try:
        for name in ("hello", "core20"):
            tdb.add(
                models.MirrorSnapContent(
                    repository_id=uuid.UUID(mid),
                    snap_name=name,
                    channel="latest/stable",
                    capture_status="DISPATCHED",
                    last_capture_message_id="msg-snap",
                )
            )
        tdb.commit()
    finally:
        tdb.close()

    session = env.tenant_s()
    try:
        rmrh._apply_snap_capture_result(session, mid, outcome)
        session.commit()
        rows = (
            session.query(models.MirrorSnapContent)
            .filter(models.MirrorSnapContent.repository_id == uuid.UUID(mid))
            .all()
        )
        assert {r.capture_status for r in rows} == {expected}
        assert all(r.last_capture_at is not None for r in rows)
        assert all(r.last_capture_message_id is None for r in rows)
        if expected == "FAILED":
            assert all(r.error_message for r in rows)
    finally:
        session.close()
