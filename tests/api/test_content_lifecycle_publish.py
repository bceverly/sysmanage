# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Publish-flow tests for the content-view API (Phase 16, Slice 2).

Exercises the real router + resolver logic across a SHARED db (content views /
versions) and a TENANT db (mirrors / snapshots / settings), with the Enterprise
engine faked (returns a materialize plan) and the agent dispatch mocked.  Also
covers the result handler that stamps a version published / failed.
"""

# pylint: disable=missing-function-docstring,redefined-outer-name

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import content_lifecycle
from backend.auth.auth_bearer import JWTBearer
from backend.persistence import models
from backend.persistence.db import Base
from backend.persistence.models import content_lifecycle as clm
from backend.persistence.partitions import get_shared_db, get_tenant_db
from backend.services import content_lifecycle_result_handlers as clrh

_CV = "/api/v1/content-lifecycle/content-views"


class _FakeEngine:
    """Stands in for content_lifecycle_engine: returns a materialize plan and
    records the ``filters`` it was handed (into a shared capture dict)."""

    def __init__(self, capture):
        self._capture = capture

    def build_publish_materialize_plan(
        self, mirror_config, mirror_root, snapshot_id, cv_id, version, filters=None
    ):
        self._capture["filters"] = filters
        name = mirror_config["name"]
        store = f"{mirror_root}/.content-views/{cv_id}/v{version}/{name}"
        return {
            "engine": "content_lifecycle_engine",
            "action": "publish_materialize",
            "name": name,
            "version": version,
            "store_path": store,
            "commands": [{"argv": ["echo", name, snapshot_id]}],
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
            models.SharedContentViewFilter.__table__,
            models.SharedContentViewVersion.__table__,
            models.SharedAdvisory.__table__,
            models.SharedAdvisoryPackage.__table__,
        ],
    )
    Base.metadata.create_all(
        tenant_engine,
        tables=[
            models.MirrorRepository.__table__,
            models.MirrorSnapshot.__table__,
            models.MirrorSettings.__table__,
        ],
    )
    shared_s = sessionmaker(bind=shared_engine)
    tenant_s = sessionmaker(bind=tenant_engine)

    app = FastAPI()
    app.include_router(content_lifecycle.router, prefix="/api/v1")

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
        dispatched.update(host_id=host_id, plan=plan, timeout=timeout)
        return "msg-123"

    def _fake_register(message_id, action, host_id, cv_version_id=""):
        dispatched.update(msg_id=message_id, action=action, cvv_id=cv_version_id)

    fake_engine = _FakeEngine(dispatched)

    try:
        with patch.object(
            content_lifecycle.module_loader, "get_module", return_value=fake_engine
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


def _seed_mirror(env, *, host_id, name="rhel9", pm="dnf", snapshot="20260101T000000"):
    db = env.tenant_s()
    try:
        if db.query(models.MirrorSettings).first() is None:
            db.add(models.MirrorSettings(mirror_root_path="/var/mirror"))
        mirror = models.MirrorRepository(
            name=name, package_manager=pm, upstream_url="http://u/", host_id=host_id
        )
        db.add(mirror)
        db.flush()
        if snapshot:
            db.add(models.MirrorSnapshot(repository_id=mirror.id, snapshot_id=snapshot))
        db.commit()
        return str(mirror.id)
    finally:
        db.close()


def _make_cv(env, name, mirror_ids, composite=False, filters=None):
    repos = [{"mirror_id": m} for m in mirror_ids]
    body = {"name": name, "composite": composite, "repos": repos}
    if filters is not None:
        body["filters"] = filters
    r = env.client.post(_CV, json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _seed_advisory(
    env,
    *,
    package_name,
    package_manager="dnf",
    advisory_type="security",
    published="2026-06-01",
):
    db = env.shared_s()
    try:
        adv = models.SharedAdvisory(
            advisory_id=f"ADV-{package_name}-{advisory_type}",
            source="test",
            advisory_type=advisory_type,
            published_date=datetime.strptime(published, "%Y-%m-%d"),
        )
        db.add(adv)
        db.flush()
        db.add(
            models.SharedAdvisoryPackage(
                advisory_row_id=adv.id,
                package_name=package_name,
                package_manager=package_manager,
            )
        )
        db.commit()
    finally:
        db.close()


class TestPublish:
    def test_happy_path(self, env):
        host = str(uuid.uuid4())
        mirror = _seed_mirror(env, host_id=host)
        cv_id = _make_cv(env, "RHEL9", [mirror])

        r = env.client.post(f"{_CV}/{cv_id}/publish")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["version"] == 1
        assert body["status"] == clm.CVV_PUBLISHING
        assert body["store_path"].endswith(f"/.content-views/{cv_id}/v1")
        # Dispatched to the mirror's host with the merged command list.
        assert env.dispatched["host_id"] == host
        assert env.dispatched["plan"]["commands"] == [
            {"argv": ["echo", "rhel9", "20260101T000000"]}
        ]
        assert env.dispatched["action"] == "publish_materialize"
        assert env.dispatched["cvv_id"] == body["id"]

    def test_version_increments(self, env):
        host = str(uuid.uuid4())
        cv_id = _make_cv(env, "CV", [_seed_mirror(env, host_id=host)])
        assert env.client.post(f"{_CV}/{cv_id}/publish").json()["version"] == 1
        assert env.client.post(f"{_CV}/{cv_id}/publish").json()["version"] == 2

    def test_merges_multiple_mirrors_same_host(self, env):
        host = str(uuid.uuid4())
        m1 = _seed_mirror(env, host_id=host, name="base")
        m2 = _seed_mirror(env, host_id=host, name="appstream")
        cv_id = _make_cv(env, "Multi", [m1, m2])
        r = env.client.post(f"{_CV}/{cv_id}/publish")
        assert r.status_code == 200
        assert len(env.dispatched["plan"]["commands"]) == 2

    def test_multi_host_rejected(self, env):
        m1 = _seed_mirror(env, host_id=str(uuid.uuid4()), name="a")
        m2 = _seed_mirror(env, host_id=str(uuid.uuid4()), name="b")
        cv_id = _make_cv(env, "Split", [m1, m2])
        r = env.client.post(f"{_CV}/{cv_id}/publish")
        assert r.status_code == 400
        assert "one host" in r.json()["detail"]

    def test_missing_snapshot_rejected(self, env):
        mirror = _seed_mirror(env, host_id=str(uuid.uuid4()), snapshot=None)
        cv_id = _make_cv(env, "NoSnap", [mirror])
        r = env.client.post(f"{_CV}/{cv_id}/publish")
        assert r.status_code == 400
        assert "snapshot" in r.json()["detail"].lower()

    def test_empty_cv_rejected(self, env):
        cv_id = _make_cv(env, "Empty", [])
        assert env.client.post(f"{_CV}/{cv_id}/publish").status_code == 400

    def test_composite_rejected(self, env):
        cv_id = _make_cv(env, "Comp", [], composite=True)
        r = env.client.post(f"{_CV}/{cv_id}/publish")
        assert r.status_code == 400
        assert "omposite" in r.json()["detail"]

    def test_versions_listed_newest_first(self, env):
        host = str(uuid.uuid4())
        cv_id = _make_cv(env, "Hist", [_seed_mirror(env, host_id=host)])
        env.client.post(f"{_CV}/{cv_id}/publish")
        env.client.post(f"{_CV}/{cv_id}/publish")
        versions = env.client.get(f"{_CV}/{cv_id}/versions").json()
        assert [v["version"] for v in versions] == [2, 1]


class TestResultHandler:
    def _insert_cvv(self, shared_s, status=clm.CVV_PUBLISHING):
        db = shared_s()
        try:
            cv = models.SharedContentView(name="cv")
            db.add(cv)
            db.flush()
            cvv = models.SharedContentViewVersion(
                content_view_id=cv.id, version=1, status=status
            )
            db.add(cvv)
            db.commit()
            return str(cvv.id)
        finally:
            db.close()

    def _reload(self, shared_s, cvv_id):
        db = shared_s()
        try:
            return db.get(models.SharedContentViewVersion, uuid.UUID(cvv_id))
        finally:
            db.close()

    def test_marks_published(self, env):
        cvv_id = self._insert_cvv(env.shared_s)
        with patch.object(clrh, "shared_sessionmaker", return_value=env.shared_s):
            clrh._apply_content_lifecycle_op_result(
                f"publish_materialize:{cvv_id}",
                "host-1",
                {"status": "succeeded", "commands": [{"argv": ["echo"]}]},
            )
        row = self._reload(env.shared_s, cvv_id)
        assert row.status == clm.CVV_PUBLISHED
        assert row.published_at is not None
        assert row.manifest["command_count"] == 1

    def test_marks_failed(self, env):
        cvv_id = self._insert_cvv(env.shared_s)
        with patch.object(clrh, "shared_sessionmaker", return_value=env.shared_s):
            clrh._apply_content_lifecycle_op_result(
                f"publish_materialize:{cvv_id}",
                "host-1",
                {"status": "failed", "error": "rsync blew up"},
            )
        row = self._reload(env.shared_s, cvv_id)
        assert row.status == clm.CVV_FAILED
        assert "rsync" in (row.publish_error or "")

    def test_unknown_version_is_dropped(self, env):
        # No row exists; handler must no-op without raising.
        with patch.object(clrh, "shared_sessionmaker", return_value=env.shared_s):
            clrh._apply_content_lifecycle_op_result(
                f"publish_materialize:{uuid.uuid4()}",
                "host-1",
                {"status": "succeeded"},
            )


class TestPublishFilters:
    def test_passes_allow_deny_bydate_primitives(self, env):
        mirror = _seed_mirror(env, host_id=str(uuid.uuid4()))
        cv_id = _make_cv(
            env,
            "Filtered",
            [mirror],
            filters=[
                {
                    "filter_type": "allow",
                    "rule_json": {"packages": ["bash", "coreutils"]},
                },
                {"filter_type": "deny", "rule_json": {"packages": ["telnet"]}},
                {"filter_type": "by_date", "rule_json": {"date": "2026-01-01"}},
            ],
        )
        assert env.client.post(f"{_CV}/{cv_id}/publish").status_code == 200
        prims = env.dispatched["filters"]
        assert [p["type"] for p in prims] == ["allow", "deny", "by_date"]
        assert prims[0]["packages"] == ["bash", "coreutils"]
        assert prims[2]["date"] == "2026-01-01"

    def test_security_only_resolves_to_allow(self, env):
        mirror = _seed_mirror(env, host_id=str(uuid.uuid4()), pm="dnf")
        _seed_advisory(env, package_name="openssl")
        _seed_advisory(env, package_name="kernel")
        _seed_advisory(env, package_name="nano", advisory_type="bugfix")  # not security
        cv_id = _make_cv(
            env, "SecOnly", [mirror], filters=[{"filter_type": "security_only"}]
        )
        env.client.post(f"{_CV}/{cv_id}/publish")
        prims = env.dispatched["filters"]
        assert len(prims) == 1 and prims[0]["type"] == "allow"
        assert prims[0]["packages"] == ["kernel", "openssl"]  # security only, sorted

    def test_security_only_empty_is_skipped(self, env):
        mirror = _seed_mirror(env, host_id=str(uuid.uuid4()), pm="dnf")
        cv_id = _make_cv(
            env, "SecEmpty", [mirror], filters=[{"filter_type": "security_only"}]
        )
        env.client.post(f"{_CV}/{cv_id}/publish")
        # No security advisories -> skip, never emit an empty allow-list.
        assert env.dispatched["filters"] == []

    def test_advisory_cutoff_denies_newer(self, env):
        mirror = _seed_mirror(env, host_id=str(uuid.uuid4()), pm="dnf")
        _seed_advisory(env, package_name="newpkg", published="2026-09-01")  # after
        _seed_advisory(env, package_name="oldpkg", published="2026-01-01")  # before
        cv_id = _make_cv(
            env,
            "Cutoff",
            [mirror],
            filters=[
                {"filter_type": "advisory_cutoff", "rule_json": {"date": "2026-06-01"}}
            ],
        )
        env.client.post(f"{_CV}/{cv_id}/publish")
        prims = env.dispatched["filters"]
        assert len(prims) == 1 and prims[0]["type"] == "deny"
        assert prims[0]["packages"] == ["newpkg"]
