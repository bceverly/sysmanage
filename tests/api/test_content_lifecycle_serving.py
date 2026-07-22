# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Serving + client-repoint tests for the content-lifecycle API (Phase 16, Slice 5).

Covers: the ``serve`` endpoint (dispatch an nginx-provisioning plan to the mirror
host), the ``repoint`` endpoint (point a consuming host's package manager at the
env URL, reusing the repository-mirroring builders), and the env-symlink repoint
that publish/promote/rollback dispatch so a DB rebind becomes physically served.
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
_FQDN = "mirror.local"


class _FakeClmEngine:
    def build_serve_content_plan(self, mirror_root, package_manager, server_name=None):
        return {
            "action": "serve_content",
            "package_manager": package_manager,
            "mirror_root": mirror_root,
            "server_name": server_name,
            "commands": [],
        }

    def build_set_env_symlink_plan(self, mirror_root, cv_id, env_name, version):
        return {
            "action": "set_env_symlink",
            "cv_id": str(cv_id),
            "env_name": env_name,
            "version": version,
            "mirror_root": mirror_root,
            "commands": [],
        }

    def resolve_content_view_url(self, fqdn, cv_id, env_name):
        return "http://%s/content-views/%s/%s" % (fqdn, cv_id, env_name)


class _FakeRepoEngine:
    def build_apt_apply_default_mirror_plan(self, url, suite, components="main"):
        return {
            "action": "default_apply",
            "files": [{"path": "/etc/apt/sources.list.d/z.list", "content": url}],
            "commands": [{"argv": ["echo", suite, components]}],
        }

    def build_dnf_apply_default_mirror_plan(self, repoid, url, gpgkey=""):
        return {
            "files": [{"path": "/etc/yum.repos.d/z.repo", "content": url}],
            "commands": [],
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
            models.MirrorRepository.__table__,
            models.MirrorSettings.__table__,
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

    dispatched = {"plans": [], "correlations": []}

    def _fake_enqueue(host_id, plan, timeout=300):
        dispatched["plans"].append({"host_id": str(host_id), "plan": plan})
        return "msg-%d" % len(dispatched["plans"])

    def _fake_register(message_id, action, host_id, cv_version_id=""):
        dispatched["correlations"].append({"action": action, "ref": cv_version_id})

    fake_clm, fake_repo = _FakeClmEngine(), _FakeRepoEngine()

    def _get_module(name):
        return {
            "content_lifecycle_engine": fake_clm,
            "repository_mirroring_engine": fake_repo,
        }.get(name)

    try:
        with patch.object(
            content_lifecycle.module_loader, "get_module", side_effect=_get_module
        ), patch.object(JWTBearer, "__call__", _bypass_auth), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan", _fake_enqueue
        ), patch(
            "backend.services.proplus_dispatch.register_content_lifecycle_correlation",
            _fake_register,
        ), patch.object(
            content_lifecycle_promotion, "_host_fqdn", lambda db, host_id: _FQDN
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


def _make_envs(env, names=("Library", "Dev", "Test")):
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


def _seed_version(env, cv_id, version, *, status=clm.CVV_PUBLISHED):
    db = env.shared_s()
    try:
        cvv = models.SharedContentViewVersion(
            content_view_id=uuid.UUID(cv_id),
            version=version,
            status=status,
            store_path=f"/var/mirror/.content-views/{cv_id}/v{version}",
        )
        db.add(cvv)
        db.commit()
        return str(cvv.id)
    finally:
        db.close()


def _seed_serving(env, cv_id, *, host, name="rhel9", pm="dnf"):
    """Attach a mirror (tenant) + a CV repo member (shared) + mirror settings."""
    tdb = env.tenant_s()
    try:
        if tdb.query(models.MirrorSettings).first() is None:
            tdb.add(models.MirrorSettings(mirror_root_path="/var/mirror"))
        mirror = models.MirrorRepository(
            name=name,
            package_manager=pm,
            upstream_url="http://u/",
            host_id=host,
            suite="noble",
            components="main",
            repoid="rhel9",
        )
        tdb.add(mirror)
        tdb.flush()
        mid = str(mirror.id)
        tdb.commit()
    finally:
        tdb.close()
    sdb = env.shared_s()
    try:
        sdb.add(
            models.SharedContentViewRepo(
                content_view_id=uuid.UUID(cv_id), mirror_id=uuid.UUID(mid), position=0
            )
        )
        sdb.commit()
    finally:
        sdb.close()
    return mid


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


def _last_plan(env):
    return env.dispatched["plans"][-1]


# --- serve ------------------------------------------------------------------


class TestServe:
    def test_dispatches_nginx_plan_to_mirror_host(self, env):
        host = str(uuid.uuid4())
        _make_envs(env)
        cv = _seed_cv(env)
        _seed_serving(env, cv, host=host, pm="apt")

        r = env.client.post(f"{_CV}/{cv}/serve")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["server_name"] == _FQDN
        assert body["host_id"] == host
        plan = _last_plan(env)
        assert plan["host_id"] == host
        assert plan["plan"]["action"] == "serve_content"
        assert plan["plan"]["package_manager"] == "apt"
        assert env.dispatched["correlations"][-1]["action"] == "serve_content"

    def test_no_mirror_is_400(self, env):
        _make_envs(env)
        cv = _seed_cv(env)
        assert env.client.post(f"{_CV}/{cv}/serve").status_code == 400


# --- repoint ----------------------------------------------------------------


class TestRepoint:
    def test_points_consumer_at_env_url(self, env):
        host = str(uuid.uuid4())
        consumer = str(uuid.uuid4())
        envs = _make_envs(env)
        cv = _seed_cv(env)
        _seed_serving(env, cv, host=host, pm="apt")
        v1 = _seed_version(env, cv, 1)
        _bind(env, envs["Library"], cv, v1)

        r = env.client.post(
            f"{_CV}/{cv}/repoint",
            json={"environment_id": envs["Library"], "host_id": consumer},
        )
        assert r.status_code == 200, r.text
        plan = _last_plan(env)
        # Dispatched to the CONSUMING host, not the mirror host.
        assert plan["host_id"] == consumer
        assert plan["plan"]["action"] == "repoint"
        # The apt override points at {env_url}/{mirror_name}.
        expected = f"http://{_FQDN}/content-views/{cv}/Library/rhel9"
        assert plan["plan"]["files"][0]["content"] == expected

    def test_unbound_env_rejected(self, env):
        host = str(uuid.uuid4())
        envs = _make_envs(env)
        cv = _seed_cv(env)
        _seed_serving(env, cv, host=host)
        r = env.client.post(
            f"{_CV}/{cv}/repoint",
            json={"environment_id": envs["Dev"], "host_id": str(uuid.uuid4())},
        )
        assert r.status_code == 400
        assert "no content" in r.json()["detail"].lower()


# --- env symlink repoint on promote / rollback ------------------------------


class TestPromotionRepoints:
    def _setup(self, env):
        host = str(uuid.uuid4())
        envs = _make_envs(env)
        cv = _seed_cv(env)
        _seed_serving(env, cv, host=host)
        return host, envs, cv

    def test_promote_dispatches_env_symlink(self, env):
        host, envs, cv = self._setup(env)
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
        plan = _last_plan(env)
        assert plan["host_id"] == host
        assert plan["plan"]["action"] == "set_env_symlink"
        assert plan["plan"]["env_name"] == "Dev"
        assert plan["plan"]["version"] == 1

    def test_rollback_dispatches_env_symlink(self, env):
        host, envs, cv = self._setup(env)
        v1, v2 = _seed_version(env, cv, 1), _seed_version(env, cv, 2)
        _bind(env, envs["Dev"], cv, v2, previous_id=v1)

        r = env.client.post(
            f"{_CV}/{cv}/rollback", json={"environment_id": envs["Dev"]}
        )
        assert r.status_code == 200, r.text
        plan = _last_plan(env)
        assert plan["plan"]["action"] == "set_env_symlink"
        assert plan["plan"]["env_name"] == "Dev"
        assert plan["plan"]["version"] == 1  # rolled back to v1


# --- env symlink repoint on publish success (result handler) ----------------


class TestPublishRepoints:
    def test_publish_success_dispatches_library_symlink(self, env):
        envs = _make_envs(env)
        cv = _seed_cv(env)
        v1 = _seed_version(env, cv, 1, status=clm.CVV_PUBLISHING)

        with patch.object(
            clrh, "shared_sessionmaker", return_value=env.shared_s
        ), patch.object(clrh, "_tenant_session_for_host", return_value=env.tenant_s()):
            clrh._apply_content_lifecycle_op_result(
                f"publish_materialize:{v1}",
                "host-1",
                {"status": "succeeded", "commands": []},
            )

        # After binding Library -> v1, the result handler repoints Library's
        # serving symlink at v1.
        symlinks = [
            p
            for p in env.dispatched["plans"]
            if p["plan"].get("action") == "set_env_symlink"
        ]
        assert symlinks, "expected a Library env-symlink dispatch on publish success"
        assert (
            symlinks[-1]["plan"]["env_name"] == envs["Library"]
            or symlinks[-1]["plan"]["env_name"] == "Library"
        )
        assert symlinks[-1]["plan"]["version"] == 1
