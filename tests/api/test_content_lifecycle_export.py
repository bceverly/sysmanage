# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Air-gap export tests for the content-lifecycle API (Phase 16, Slice 7a).

Exports a published content-view version to a signed ISO by reusing the air-gap
collector engine's ``build_iso_plan``.  Covers: the export dispatch (a run at
BUILDING_ISO + a build_iso plan staged over the CVV store), the licensing gates,
the not-published rejection, and the result handler that flips the run
COMPLETE / FAILED.
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

from backend.api import content_lifecycle, content_lifecycle_export
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.persistence import models
from backend.persistence.db import Base
from backend.persistence.models import content_lifecycle as clm
from backend.persistence.partitions import get_shared_db, get_tenant_db
from backend.services import content_lifecycle_result_handlers as clrh

_CV = "/api/v1/content-lifecycle/content-views"
_ACTOR = str(uuid.uuid4())


class _FakeCollector:
    def build_iso_plan(self, staging_dir, output_iso, manifest_dict, iso_label="x"):
        return {
            "action": "build_iso",
            "staging_dir": staging_dir,
            "output_iso": output_iso,
            "manifest": manifest_dict,
            "iso_label": iso_label,
            "commands": [{"argv": ["echo", "iso"]}],
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
        tables=[
            models.MirrorRepository.__table__,
            models.MirrorSettings.__table__,
            models.ContentViewExportRun.__table__,
        ],
    )
    shared_s = sessionmaker(bind=shared_engine)
    tenant_s = sessionmaker(bind=tenant_engine)

    app = FastAPI()
    app.include_router(content_lifecycle.router, prefix="/api/v1")
    app.include_router(content_lifecycle_export.router, prefix="/api/v1")

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
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        id=_ACTOR
    )

    async def _bypass_auth(self, request: Request):
        return "test-user"

    dispatched = {}

    def _fake_enqueue(host_id, plan, timeout=300):
        dispatched.update(host_id=str(host_id), plan=plan)
        return "msg-export"

    def _fake_register(message_id, action, host_id, cv_version_id=""):
        dispatched.update(action=action, ref=cv_version_id)

    modules = {
        "content_lifecycle_engine": object(),
        "airgap_collector_engine": _FakeCollector(),
    }

    try:
        with patch.object(
            content_lifecycle.module_loader,
            "get_module",
            side_effect=modules.get,
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
                    modules=modules,
                )
    finally:
        shared_engine.dispose()
        tenant_engine.dispose()


def _seed_cv_with_version(env, *, host, version=1, published=True):
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
        cv = models.SharedContentView(name="RHEL9 Base")
        sdb.add(cv)
        sdb.flush()
        sdb.add(
            models.SharedContentViewRepo(
                content_view_id=cv.id, mirror_id=mid, position=0
            )
        )
        sdb.add(
            models.SharedContentViewVersion(
                content_view_id=cv.id,
                version=version,
                status=clm.CVV_PUBLISHED if published else clm.CVV_PUBLISHING,
                store_path=f"/var/mirror/.content-views/{cv.id}/v{version}",
            )
        )
        sdb.commit()
        return str(cv.id)
    finally:
        sdb.close()


class TestExport:
    def test_dispatches_iso_build_over_the_store(self, env):
        host = str(uuid.uuid4())
        cv = _seed_cv_with_version(env, host=host, version=2)

        r = env.client.post(f"{_CV}/{cv}/versions/2/export")
        assert r.status_code == 200, r.text
        run = r.json()
        assert run["status"] == clm.EXPORT_BUILDING_ISO
        assert run["iso_path"].endswith(".iso")
        assert run["version"] == 2
        # Dispatched to the mirror host; the ISO is built over the CVV store.
        assert env.dispatched["host_id"] == host
        plan = env.dispatched["plan"]
        assert plan["staging_dir"] == f"/var/mirror/.content-views/{cv}/v2"
        # mkdir of the output dir is prepended before the build.
        assert plan["commands"][0]["argv"][:2] == ["sudo", "mkdir"]
        assert env.dispatched["ref"] == run["id"]

    def test_lists_export_runs(self, env):
        host = str(uuid.uuid4())
        cv = _seed_cv_with_version(env, host=host)
        env.client.post(f"{_CV}/{cv}/versions/1/export")
        rows = env.client.get(f"{_CV}/{cv}/exports").json()
        assert len(rows) == 1 and rows[0]["iso_label"].startswith("clm-")

    def test_unpublished_version_rejected(self, env):
        host = str(uuid.uuid4())
        cv = _seed_cv_with_version(env, host=host, version=1, published=False)
        r = env.client.post(f"{_CV}/{cv}/versions/1/export")
        assert r.status_code == 400
        assert "published" in r.json()["detail"].lower()

    def test_collector_engine_required(self, env):
        host = str(uuid.uuid4())
        cv = _seed_cv_with_version(env, host=host)
        # Collector engine absent -> 402 (CLM engine still present).
        env.modules.pop("airgap_collector_engine")
        r = env.client.post(f"{_CV}/{cv}/versions/1/export")
        assert r.status_code == 402


class TestExportResult:
    def _seed_run(self, env, host):
        cv = _seed_cv_with_version(env, host=host)
        env.client.post(f"{_CV}/{cv}/versions/1/export")
        db = env.tenant_s()
        try:
            return str(db.query(models.ContentViewExportRun).first().id)
        finally:
            db.close()

    def _reload(self, env, run_id):
        db = env.tenant_s()
        try:
            return db.get(models.ContentViewExportRun, uuid.UUID(run_id))
        finally:
            db.close()

    def test_marks_complete(self, env):
        run_id = self._seed_run(env, str(uuid.uuid4()))
        with patch.object(
            clrh, "_tenant_session_for_host", return_value=env.tenant_s()
        ):
            clrh._apply_content_lifecycle_op_result(
                f"cv_export:{run_id}", "host-1", {"status": "succeeded"}
            )
        row = self._reload(env, run_id)
        assert row.status == clm.EXPORT_COMPLETE
        assert row.worker_message_id is None

    def test_marks_failed(self, env):
        run_id = self._seed_run(env, str(uuid.uuid4()))
        with patch.object(
            clrh, "_tenant_session_for_host", return_value=env.tenant_s()
        ):
            clrh._apply_content_lifecycle_op_result(
                f"cv_export:{run_id}",
                "host-1",
                {"status": "failed", "error": "xorriso boom"},
            )
        row = self._reload(env, run_id)
        assert row.status == clm.EXPORT_FAILED
        assert "xorriso" in (row.error_message or "")
