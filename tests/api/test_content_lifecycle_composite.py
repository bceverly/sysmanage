# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Composite content-view tests (Phase 16, Slice 6).

A composite CV composes its component CVs' newest PUBLISHED versions into one
immutable version at publish time.  Covers: the compose publish path (dispatch a
combined materialize plan + record the resolved component versions in the
manifest), the no-published-component rejection, and that serving resolves a
composite through its components' mirrors.
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

_CV = "/api/v1/content-lifecycle/content-views"
_ACTOR = str(uuid.uuid4())


class _FakeEngine:
    def __init__(self, capture):
        self._c = capture

    def build_compose_materialize_plan(
        self, mirror_root, cv_id, version, components, filters=None
    ):
        self._c["components"] = components
        self._c["compose_filters"] = filters
        return {
            "action": "publish_materialize",
            "cv_id": str(cv_id),
            "version": version,
            "store_path": f"{mirror_root}/.content-views/{cv_id}/v{version}",
            "commands": [{"argv": ["echo", "compose"]}],
        }

    def build_serve_content_plan(self, mirror_root, package_manager, server_name=None):
        return {
            "action": "serve_content",
            "package_manager": package_manager,
            "commands": [],
        }

    def resolve_content_view_url(self, fqdn, cv_id, env_name):
        return f"http://{fqdn}/content-views/{cv_id}/{env_name}"


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

    dispatched = {}

    def _fake_enqueue(host_id, plan, timeout=300):
        dispatched.update(host_id=str(host_id), plan=plan)
        return "msg-1"

    def _fake_register(message_id, action, host_id, cv_version_id=""):
        dispatched.update(action=action, cvv_id=cv_version_id)

    fake_engine = _FakeEngine(dispatched)

    try:
        with patch.object(
            content_lifecycle.module_loader, "get_module", return_value=fake_engine
        ), patch.object(JWTBearer, "__call__", _bypass_auth), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan", _fake_enqueue
        ), patch(
            "backend.services.proplus_dispatch.register_content_lifecycle_correlation",
            _fake_register,
        ), patch.object(
            content_lifecycle_promotion,
            "_host_fqdn",
            lambda db, host_id: "mirror.local",
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


def _seed_mirror(env, *, host, name, pm="dnf"):
    db = env.tenant_s()
    try:
        if db.query(models.MirrorSettings).first() is None:
            db.add(models.MirrorSettings(mirror_root_path="/var/mirror"))
        mirror = models.MirrorRepository(
            name=name, package_manager=pm, upstream_url="http://u/", host_id=host
        )
        db.add(mirror)
        db.flush()
        mid = str(mirror.id)
        db.commit()
        return mid
    finally:
        db.close()


def _make_component(env, name, mirror_id):
    r = env.client.post(_CV, json={"name": name, "repos": [{"mirror_id": mirror_id}]})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _make_composite(env, name, component_ids):
    r = env.client.post(
        _CV,
        json={
            "name": name,
            "composite": True,
            "repos": [{"component_content_view_id": c} for c in component_ids],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _seed_published(env, cv_id, version):
    db = env.shared_s()
    try:
        db.add(
            models.SharedContentViewVersion(
                content_view_id=uuid.UUID(cv_id),
                version=version,
                status=clm.CVV_PUBLISHED,
                store_path=f"/var/mirror/.content-views/{cv_id}/v{version}",
            )
        )
        db.commit()
    finally:
        db.close()


def _composite_manifest(env, cv_id):
    db = env.shared_s()
    try:
        row = (
            db.query(models.SharedContentViewVersion)
            .filter(models.SharedContentViewVersion.content_view_id == uuid.UUID(cv_id))
            .order_by(models.SharedContentViewVersion.version.desc())
            .first()
        )
        return row.manifest if row else None
    finally:
        db.close()


class TestCompositePublish:
    def test_composes_component_latest_published(self, env):
        host = str(uuid.uuid4())
        c1 = _make_component(env, "Base", _seed_mirror(env, host=host, name="os"))
        c2 = _make_component(env, "Apps", _seed_mirror(env, host=host, name="epel"))
        _seed_published(env, c1, 1)
        _seed_published(env, c1, 2)  # newest for c1
        _seed_published(env, c2, 5)  # newest for c2
        comp = _make_composite(env, "Full", [c1, c2])

        r = env.client.post(f"{_CV}/{comp}/publish")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == clm.CVV_PUBLISHING
        assert body["version"] == 1
        assert body["store_path"].endswith(f"/.content-views/{comp}/v1")
        assert env.dispatched["host_id"] == host

        # The engine received each component's NEWEST published version.
        picked = {c["cv_id"]: c["version"] for c in env.dispatched["components"]}
        assert picked == {c1: 2, c2: 5}
        # ... and the composite version records them in its manifest.
        manifest = _composite_manifest(env, comp)
        recorded = {c["content_view_id"]: c["version"] for c in manifest["components"]}
        assert recorded == {c1: 2, c2: 5}

    def test_component_without_published_version_rejected(self, env):
        host = str(uuid.uuid4())
        c1 = _make_component(env, "Base", _seed_mirror(env, host=host, name="os"))
        # c1 has no published version.
        comp = _make_composite(env, "Full", [c1])
        r = env.client.post(f"{_CV}/{comp}/publish")
        assert r.status_code == 400
        assert "published" in r.json()["detail"].lower()

    def test_components_on_different_hosts_rejected(self, env):
        c1 = _make_component(
            env, "Base", _seed_mirror(env, host=str(uuid.uuid4()), name="os")
        )
        c2 = _make_component(
            env, "Apps", _seed_mirror(env, host=str(uuid.uuid4()), name="epel")
        )
        _seed_published(env, c1, 1)
        _seed_published(env, c2, 1)
        comp = _make_composite(env, "Full", [c1, c2])
        r = env.client.post(f"{_CV}/{comp}/publish")
        assert r.status_code == 400
        assert "one host" in r.json()["detail"]


class TestCompositeServing:
    def test_serve_resolves_through_components(self, env):
        host = str(uuid.uuid4())
        c1 = _make_component(env, "Base", _seed_mirror(env, host=host, name="os"))
        _seed_published(env, c1, 1)
        comp = _make_composite(env, "Full", [c1])

        r = env.client.post(f"{_CV}/{comp}/serve")
        assert r.status_code == 200, r.text
        assert env.dispatched["host_id"] == host
        assert env.dispatched["plan"]["action"] == "serve_content"
