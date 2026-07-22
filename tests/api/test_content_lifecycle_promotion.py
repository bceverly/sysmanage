# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Promotion + rollback tests for the content-lifecycle API (Phase 16, Slice 4).

Exercises the real router across a SHARED db (content views / versions /
environments) and a TENANT db (bindings / audit): the promote + rollback state
machine, the pin-aware retention GC, the Library-binding-on-publish that the
result handler writes, and the lane/audit read models.
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

from backend.api import content_lifecycle, content_lifecycle_promotion
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.persistence import models
from backend.persistence.db import Base
from backend.persistence.models import content_lifecycle as clm
from backend.persistence.partitions import get_shared_db, get_tenant_db
from backend.services import content_lifecycle_result_handlers as clrh

_CV = "/api/v1/content-lifecycle/content-views"
_ENV = "/api/v1/content-lifecycle/environments"
_ACTOR = str(uuid.uuid4())


class _FakeEngine:
    """Only the reclaim builder is needed by the promotion/GC path."""

    def build_reclaim_version_plan(self, store_path):
        return {"action": "reclaim", "store_path": store_path, "commands": []}


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
            models.SharedLifecycleEnvironment.__table__,
            models.SharedContentView.__table__,
            models.SharedContentViewRepo.__table__,
            models.SharedContentViewFilter.__table__,
            models.SharedContentViewVersion.__table__,
        ],
    )
    Base.metadata.create_all(
        tenant_engine,
        tables=[
            models.EnvironmentContentBinding.__table__,
            models.ContentPromotionAudit.__table__,
        ],
    )
    shared_s = sessionmaker(bind=shared_engine)
    tenant_s = sessionmaker(bind=tenant_engine)

    app = FastAPI()
    app.include_router(content_lifecycle.router, prefix="/api/v1")
    app.include_router(content_lifecycle_promotion.router, prefix="/api/v1")

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
        dispatched.update(host_id=host_id, plan=plan, timeout=timeout)
        return "msg-123"

    def _fake_register(message_id, action, host_id, cv_version_id=""):
        dispatched.update(msg_id=message_id, action=action, cvv_id=cv_version_id)

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


# --- seed helpers -----------------------------------------------------------


def _make_envs(env, names=("Library", "Dev", "Test", "Prod")):
    """Create the ordered path via the API (the first becomes the Library)."""
    ids = {}
    for name in names:
        r = env.client.post(_ENV, json={"name": name})
        assert r.status_code == 200, r.text
        ids[name] = r.json()["id"]
    return ids


def _seed_cv(env, name="CV", keep_versions=5):
    db = env.shared_s()
    try:
        cv = models.SharedContentView(name=name, keep_versions=keep_versions)
        db.add(cv)
        db.commit()
        return str(cv.id)
    finally:
        db.close()


def _seed_version(env, cv_id, version, *, status=clm.CVV_PUBLISHED, store=True):
    db = env.shared_s()
    try:
        cvv = models.SharedContentViewVersion(
            content_view_id=uuid.UUID(cv_id),
            version=version,
            status=status,
            store_path=(
                f"/var/mirror/.content-views/{cv_id}/v{version}" if store else None
            ),
        )
        db.add(cvv)
        db.commit()
        return str(cvv.id)
    finally:
        db.close()


def _bind(env, env_id, cv_id, cvv_id, previous_id=None):
    db = env.tenant_s()
    try:
        db.add(
            models.EnvironmentContentBinding(
                environment_id=uuid.UUID(env_id),
                content_view_id=uuid.UUID(cv_id),
                content_view_version_id=uuid.UUID(cvv_id),
                previous_version_id=uuid.UUID(previous_id) if previous_id else None,
            )
        )
        db.commit()
    finally:
        db.close()


def _binding_row(env, env_id, cv_id):
    db = env.tenant_s()
    try:
        return (
            db.query(models.EnvironmentContentBinding)
            .filter(models.EnvironmentContentBinding.environment_id == env_id)
            .filter(models.EnvironmentContentBinding.content_view_id == cv_id)
            .first()
        )
    finally:
        db.close()


def _cvv_row(env, cvv_id):
    db = env.shared_s()
    try:
        return db.get(models.SharedContentViewVersion, uuid.UUID(cvv_id))
    finally:
        db.close()


# --- promotion --------------------------------------------------------------


class TestPromote:
    def test_forward_promotion_rebinds_target(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1 = _seed_version(env, cv, 1)
        _bind(env, envs["Library"], cv, v1)

        r = env.client.post(
            f"{_CV}/{cv}/promote",
            json={
                "from_environment_id": envs["Library"],
                "to_environment_id": envs["Dev"],
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["content_view_version_id"] == v1
        dev = _binding_row(env, envs["Dev"], cv)
        assert str(dev.content_view_version_id) == v1
        assert str(dev.promoted_by) == _ACTOR

    def test_promote_over_existing_records_previous(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1, v2 = _seed_version(env, cv, 1), _seed_version(env, cv, 2)
        _bind(env, envs["Library"], cv, v2)
        _bind(env, envs["Dev"], cv, v1)  # Dev already has the older version

        r = env.client.post(
            f"{_CV}/{cv}/promote",
            json={
                "from_environment_id": envs["Library"],
                "to_environment_id": envs["Dev"],
            },
        )
        assert r.status_code == 200, r.text
        dev = _binding_row(env, envs["Dev"], cv)
        assert str(dev.content_view_version_id) == v2
        assert str(dev.previous_version_id) == v1  # rollback target preserved

    def test_backward_promotion_rejected(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1 = _seed_version(env, cv, 1)
        _bind(env, envs["Dev"], cv, v1)
        r = env.client.post(
            f"{_CV}/{cv}/promote",
            json={
                "from_environment_id": envs["Dev"],
                "to_environment_id": envs["Library"],
            },
        )
        assert r.status_code == 400
        assert "forward" in r.json()["detail"].lower()

    def test_same_env_rejected(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        r = env.client.post(
            f"{_CV}/{cv}/promote",
            json={
                "from_environment_id": envs["Dev"],
                "to_environment_id": envs["Dev"],
            },
        )
        assert r.status_code == 400

    def test_source_without_content_rejected(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        r = env.client.post(
            f"{_CV}/{cv}/promote",
            json={
                "from_environment_id": envs["Dev"],
                "to_environment_id": envs["Test"],
            },
        )
        assert r.status_code == 400
        assert "source" in r.json()["detail"].lower()

    def test_unpublished_source_rejected(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1 = _seed_version(env, cv, 1, status=clm.CVV_PUBLISHING)
        _bind(env, envs["Library"], cv, v1)
        r = env.client.post(
            f"{_CV}/{cv}/promote",
            json={
                "from_environment_id": envs["Library"],
                "to_environment_id": envs["Dev"],
            },
        )
        assert r.status_code == 400
        assert "published" in r.json()["detail"].lower()


# --- rollback ---------------------------------------------------------------


class TestRollback:
    def test_rollback_swaps_to_previous(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1, v2 = _seed_version(env, cv, 1), _seed_version(env, cv, 2)
        _bind(env, envs["Dev"], cv, v2, previous_id=v1)

        r = env.client.post(
            f"{_CV}/{cv}/rollback", json={"environment_id": envs["Dev"]}
        )
        assert r.status_code == 200, r.text
        dev = _binding_row(env, envs["Dev"], cv)
        assert str(dev.content_view_version_id) == v1
        assert str(dev.previous_version_id) == v2  # reversible (redo)

    def test_rollback_without_previous_rejected(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1 = _seed_version(env, cv, 1)
        _bind(env, envs["Dev"], cv, v1)
        r = env.client.post(
            f"{_CV}/{cv}/rollback", json={"environment_id": envs["Dev"]}
        )
        assert r.status_code == 400
        assert "previous" in r.json()["detail"].lower()

    def test_rollback_to_reclaimed_version_conflicts(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        # previous version was GC'd: deprecated + store cleared.
        v1 = _seed_version(env, cv, 1, status=clm.CVV_DEPRECATED, store=False)
        v2 = _seed_version(env, cv, 2)
        _bind(env, envs["Dev"], cv, v2, previous_id=v1)
        r = env.client.post(
            f"{_CV}/{cv}/rollback", json={"environment_id": envs["Dev"]}
        )
        assert r.status_code == 409
        assert "reclaimed" in r.json()["detail"].lower()


# --- lane + audit read models ----------------------------------------------


class TestLaneAndAudit:
    def test_bindings_lane_lists_every_env(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1 = _seed_version(env, cv, 1)
        _bind(env, envs["Library"], cv, v1)

        rows = env.client.get(f"{_CV}/{cv}/bindings").json()
        assert [r["environment_name"] for r in rows] == [
            "Library",
            "Dev",
            "Test",
            "Prod",
        ]
        lib = next(r for r in rows if r["is_library"])
        assert lib["binding"]["version"] == 1
        assert lib["binding"]["status"] == clm.CVV_PUBLISHED
        assert rows[1]["binding"] is None  # Dev empty

    def test_audit_trail_records_promote(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1 = _seed_version(env, cv, 1)
        _bind(env, envs["Library"], cv, v1)
        env.client.post(
            f"{_CV}/{cv}/promote",
            json={
                "from_environment_id": envs["Library"],
                "to_environment_id": envs["Dev"],
                "note": "ship it",
            },
        )
        audit = env.client.get(f"{_CV}/{cv}/audit").json()
        assert len(audit) == 1
        assert audit[0]["action"] == clm.PROMOTION_PROMOTE
        assert audit[0]["note"] == "ship it"
        assert audit[0]["to_environment_id"] == envs["Dev"]


# --- publish finalize: Library binding + pin-aware GC -----------------------


class TestPublishFinalize:
    def _finalize(self, env, cvv_id, host="host-1"):
        with patch.object(
            clrh, "shared_sessionmaker", return_value=env.shared_s
        ), patch.object(clrh, "_tenant_session_for_host", return_value=env.tenant_s()):
            clrh._apply_content_lifecycle_op_result(
                f"publish_materialize:{cvv_id}",
                host,
                {"status": "succeeded", "commands": [{"argv": ["echo"]}]},
            )

    def test_publish_success_binds_library(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1 = _seed_version(env, cv, 1, status=clm.CVV_PUBLISHING)
        self._finalize(env, v1)

        assert _cvv_row(env, v1).status == clm.CVV_PUBLISHED
        lib = _binding_row(env, envs["Library"], cv)
        assert lib is not None and str(lib.content_view_version_id) == v1

    def test_pin_aware_gc_reaps_unpinned_only(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env, keep_versions=1)
        v1 = _seed_version(env, cv, 1)  # will be pinned by Dev
        v2 = _seed_version(env, cv, 2)  # unpinned -> reclaimed
        v3 = _seed_version(env, cv, 3, status=clm.CVV_PUBLISHING)  # the new publish
        _bind(env, envs["Dev"], cv, v1)  # pins v1

        self._finalize(env, v3)

        # v3 published + bound to Library (pinned); v1 pinned by Dev -> retained.
        assert _cvv_row(env, v3).status == clm.CVV_PUBLISHED
        assert _cvv_row(env, v1).status == clm.CVV_PUBLISHED
        # v2 is beyond keep_versions=1 and unpinned -> deprecated + reclaim sent.
        reaped = _cvv_row(env, v2)
        assert reaped.status == clm.CVV_DEPRECATED
        assert reaped.store_path is None
        assert env.dispatched.get("action") == "reclaim"
        assert env.dispatched.get("cvv_id") == v2
