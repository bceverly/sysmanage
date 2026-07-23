# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Version-diff tests for the content-lifecycle API (Phase 16, Slice 8).

Covers: dispatching a package diff of a version against the previous published
version, the no-earlier-version rejection, the empty GET before compute, and the
result handler that compares the two stores' package listings and stores the
added/removed sets on the newer version's manifest.
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

from backend.api import content_lifecycle, content_lifecycle_diff
from backend.auth.auth_bearer import JWTBearer
from backend.persistence import models
from backend.persistence.db import Base
from backend.persistence.models import content_lifecycle as clm
from backend.persistence.partitions import get_shared_db, get_tenant_db
from backend.services import content_lifecycle_result_handlers as clrh

_CV = "/api/v1/content-lifecycle/content-views"


class _FakeEngine:
    def build_version_diff_plan(self, store_prev, store_cur):
        return {
            "action": "version_diff",
            "store_prev": store_prev,
            "store_cur": store_cur,
            "commands": [{"argv": ["echo", "prev"]}, {"argv": ["echo", "cur"]}],
        }


@pytest.fixture
def env():
    shared_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    tenant_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        shared_engine,
        tables=[
            models.SharedContentView.__table__,
            models.SharedContentViewRepo.__table__,
            models.SharedContentViewVersion.__table__,
        ],
    )
    Base.metadata.create_all(
        tenant_engine,
        tables=[models.MirrorRepository.__table__, models.MirrorSettings.__table__],
    )
    shared_s = sessionmaker(bind=shared_engine)
    tenant_s = sessionmaker(bind=tenant_engine)

    app = FastAPI()
    app.include_router(content_lifecycle.router, prefix="/api/v1")
    app.include_router(content_lifecycle_diff.router, prefix="/api/v1")

    def _shared():
        db = shared_s()
        try:
            yield db
        finally:
            db.close()

    def _tenant():
        db = tenant_s()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_shared_db] = _shared
    app.dependency_overrides[get_tenant_db] = _tenant

    async def _bypass_auth(self, request: Request):
        return "test-user"

    dispatched = {}

    def _fake_enqueue(host_id, plan, timeout=300):
        dispatched.update(host_id=str(host_id), plan=plan)
        return "m-diff"

    def _fake_register(message_id, action, host_id, cv_version_id=""):
        dispatched.update(action=action, ref=cv_version_id)

    try:
        with patch.object(
            content_lifecycle.module_loader, "get_module", return_value=_FakeEngine()
        ), patch.object(JWTBearer, "__call__", _bypass_auth), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan", _fake_enqueue
        ), patch(
            "backend.services.proplus_dispatch.register_content_lifecycle_correlation",
            _fake_register,
        ):
            with TestClient(app) as client:
                yield SimpleNamespace(
                    client=client,
                    shared_s=shared_s,
                    tenant_s=tenant_s,
                    dispatched=dispatched,
                )
    finally:
        shared_engine.dispose()
        tenant_engine.dispose()


def _seed(env, *, versions=(1, 2), host=None):
    host = host or str(uuid.uuid4())
    tdb = env.tenant_s()
    try:
        tdb.add(models.MirrorSettings(mirror_root_path="/var/mirror"))
        mirror = models.MirrorRepository(
            name="os", package_manager="dnf", upstream_url="http://u/", host_id=host
        )
        tdb.add(mirror)
        tdb.flush()
        mid = mirror.id
        tdb.commit()
    finally:
        tdb.close()
    sdb = env.shared_s()
    try:
        cv = models.SharedContentView(name="CV")
        sdb.add(cv)
        sdb.flush()
        sdb.add(models.SharedContentViewRepo(content_view_id=cv.id, mirror_id=mid))
        ids = {}
        for v in versions:
            cvv = models.SharedContentViewVersion(
                content_view_id=cv.id,
                version=v,
                status=clm.CVV_PUBLISHED,
                store_path=f"/var/mirror/.content-views/{cv.id}/v{v}",
            )
            sdb.add(cvv)
            sdb.flush()
            ids[v] = str(cvv.id)
        sdb.commit()
        return str(cv.id), ids, host
    finally:
        sdb.close()


class TestDiff:
    def test_dispatches_diff_of_prev_and_current(self, env):
        cv, ids, host = _seed(env, versions=(1, 2))
        r = env.client.post(f"{_CV}/{cv}/versions/2/diff")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"status": "computing", "from_version": 1, "to_version": 2}
        assert env.dispatched["host_id"] == host
        plan = env.dispatched["plan"]
        assert plan["action"] == "version_diff"
        assert plan["store_prev"].endswith("/v1")
        assert plan["store_cur"].endswith("/v2")
        assert env.dispatched["action"] == "cv_diff"
        assert env.dispatched["ref"] == ids[2]

    def test_first_version_has_no_baseline(self, env):
        cv, _ids, _host = _seed(env, versions=(1,))
        r = env.client.post(f"{_CV}/{cv}/versions/1/diff")
        assert r.status_code == 400
        assert "earlier" in r.json()["detail"].lower()

    def test_get_before_compute_is_none(self, env):
        cv, _ids, _host = _seed(env, versions=(1, 2))
        assert env.client.get(f"{_CV}/{cv}/versions/2/diff").json() == {
            "status": "none"
        }


class TestDiffResult:
    def test_stores_added_removed_on_manifest(self, env):
        cv, ids, _host = _seed(env, versions=(1, 2))
        outcome = {
            "commands": [
                {"stdout": "bash-1.rpm\ncoreutils-2.rpm\ntelnet-1.rpm\n"},  # prev
                {"stdout": "bash-1.rpm\ncoreutils-2.rpm\nnano-3.rpm\n"},  # cur
            ]
        }
        with patch.object(clrh, "shared_sessionmaker", return_value=env.shared_s):
            clrh._apply_content_lifecycle_op_result(
                f"cv_diff:{ids[2]}", "host-1", outcome
            )
        diff = env.client.get(f"{_CV}/{cv}/versions/2/diff").json()
        assert diff["added"] == ["nano-3.rpm"]
        assert diff["removed"] == ["telnet-1.rpm"]
        assert diff["added_count"] == 1 and diff["removed_count"] == 1
