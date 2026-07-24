# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Image-capture tests for the repository-mirroring API (Phase 17.2, Slice 3).

Tracks container images against a mirror and dispatches an oci_proxy_engine
capture plan (skopeo copy into an OCI layout) into the mirror pipeline.  Covers:
the 402 license gate, track/list/untrack, the capture dispatch (rows flipped
DISPATCHED), and the result handler that flips the tracked rows CAPTURED/FAILED.
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


class _FakeOciEngine:
    class OciProxyError(Exception):
        pass

    def __init__(self):
        self.calls = []

    def build_image_capture_plan(self, mirror_root, mirror_name, images):
        self.calls.append((mirror_root, mirror_name, tuple(i["tag"] for i in images)))
        return {
            "engine": "oci_proxy_engine",
            "action": "image_capture",
            "files": [],
            "commands": [
                {"argv": ["sudo", "skopeo", "copy", i["repository"]]} for i in images
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
            models.MirrorImageContent.__table__,
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
        return "msg-img"

    def _fake_register(message_id, action, host_id, mirror_id=""):
        dispatched.update(action=action, ref=mirror_id)

    engine = _FakeOciEngine()
    modules = {"oci_proxy_engine": engine}

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


def _img(registry="docker.io", repository="library/nginx", tag="1.27"):
    return {"registry": registry, "repository": repository, "tag": tag}


# --------------------------------------------------------------------- gate


def test_gate_402_when_unlicensed(env):
    env.modules.clear()
    mid = _seed_mirror(env)
    r = env.client.get(f"{_MIRRORS}/{mid}/images")
    assert r.status_code == 402


# --------------------------------------------------------------------- track


def test_track_image_creates_row(env):
    mid = _seed_mirror(env)
    r = env.client.post(f"{_MIRRORS}/{mid}/images", json=_img())
    assert r.status_code == 200
    body = r.json()
    assert body["registry"] == "docker.io"
    assert body["repository"] == "library/nginx"
    assert body["tag"] == "1.27"
    assert body["capture_status"] == "TRACKED"
    assert body["digest"] is None


def test_track_image_default_tag(env):
    mid = _seed_mirror(env)
    r = env.client.post(
        f"{_MIRRORS}/{mid}/images",
        json={"registry": "quay.io", "repository": "org/app"},
    )
    assert r.status_code == 200
    assert r.json()["tag"] == "latest"


def test_track_image_idempotent(env):
    mid = _seed_mirror(env)
    env.client.post(f"{_MIRRORS}/{mid}/images", json=_img())
    r = env.client.post(f"{_MIRRORS}/{mid}/images", json=_img())
    assert r.status_code == 200
    listed = env.client.get(f"{_MIRRORS}/{mid}/images").json()
    assert len(listed) == 1  # not duplicated


def test_track_image_rejects_bad_repository(env):
    mid = _seed_mirror(env)
    r = env.client.post(f"{_MIRRORS}/{mid}/images", json=_img(repository="BAD/App"))
    assert r.status_code == 422  # pydantic pattern (uppercase)


def test_track_image_mirror_404(env):
    r = env.client.post(f"{_MIRRORS}/{uuid.uuid4()}/images", json=_img())
    assert r.status_code == 404


# ------------------------------------------------------------- list / untrack


def test_list_and_untrack(env):
    mid = _seed_mirror(env)
    env.client.post(f"{_MIRRORS}/{mid}/images", json=_img(repository="library/nginx"))
    env.client.post(f"{_MIRRORS}/{mid}/images", json=_img(repository="library/redis"))
    listed = env.client.get(f"{_MIRRORS}/{mid}/images").json()
    assert {i["repository"] for i in listed} == {"library/nginx", "library/redis"}

    r = env.client.delete(f"{_MIRRORS}/{mid}/images/{listed[0]['id']}")
    assert r.status_code == 200
    assert len(env.client.get(f"{_MIRRORS}/{mid}/images").json()) == 1


# --------------------------------------------------------------------- capture


def test_capture_dispatches_plan(env):
    mid = _seed_mirror(env)
    env.client.post(f"{_MIRRORS}/{mid}/images", json=_img(repository="library/nginx"))
    env.client.post(f"{_MIRRORS}/{mid}/images", json=_img(repository="library/redis"))
    r = env.client.post(f"{_MIRRORS}/{mid}/capture-images")
    assert r.status_code == 200
    body = r.json()
    assert body["image_count"] == 2
    assert body["message_id"] == "msg-img"
    assert len(env.engine.calls) == 1  # one plan with all tracked images
    assert env.dispatched["action"] == "image_capture"
    assert env.dispatched["ref"] == mid
    listed = env.client.get(f"{_MIRRORS}/{mid}/images").json()
    assert all(i["capture_status"] == "DISPATCHED" for i in listed)


def test_capture_400_when_no_images(env):
    mid = _seed_mirror(env)
    r = env.client.post(f"{_MIRRORS}/{mid}/capture-images")
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
        for repo in ("library/nginx", "library/redis"):
            tdb.add(
                models.MirrorImageContent(
                    repository_id=uuid.UUID(mid),
                    registry="docker.io",
                    repository=repo,
                    tag="1.0",
                    capture_status="DISPATCHED",
                    last_capture_message_id="msg-img",
                )
            )
        tdb.commit()
    finally:
        tdb.close()

    session = env.tenant_s()
    try:
        rmrh._apply_image_capture_result(session, mid, outcome)
        session.commit()
        rows = (
            session.query(models.MirrorImageContent)
            .filter(models.MirrorImageContent.repository_id == uuid.UUID(mid))
            .all()
        )
        assert {r.capture_status for r in rows} == {expected}
        assert all(r.last_capture_at is not None for r in rows)
        assert all(r.last_capture_message_id is None for r in rows)
        if expected == "FAILED":
            assert all(r.error_message for r in rows)
    finally:
        session.close()


def test_result_handler_records_digest_from_markers(env):
    mid = _seed_mirror(env)
    tdb = env.tenant_s()
    try:
        tdb.add(
            models.MirrorImageContent(
                repository_id=uuid.UUID(mid),
                registry="docker.io",
                repository="library/nginx",
                tag="1.27",
                capture_status="DISPATCHED",
            )
        )
        tdb.commit()
    finally:
        tdb.close()

    outcome = {
        "status": "succeeded",
        "commands": [
            {"stdout": "Copying blob done", "success": True},
            {
                "stdout": "IMGDIGEST docker.io|library/nginx|1.27|sha256:deadbeef",
                "success": True,
            },
        ],
    }
    session = env.tenant_s()
    try:
        rmrh._apply_image_capture_result(session, mid, outcome)
        session.commit()
        row = session.query(models.MirrorImageContent).first()
        assert row.capture_status == "CAPTURED"
        assert row.digest == "sha256:deadbeef"
    finally:
        session.close()
