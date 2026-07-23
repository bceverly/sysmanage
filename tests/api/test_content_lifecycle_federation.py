# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Federated site-sync tests for the content-lifecycle API (Phase 16, Slice 7b).

Covers the coordinator-side env<->site subscription CRUD (idempotent create,
list, delete) and the coordinator-role gate.
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

from backend.api import content_lifecycle, content_lifecycle_federation
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.persistence import models
from backend.persistence.db import Base
from backend.persistence.partitions import get_shared_db, get_tenant_db

_ENV = "/api/v1/content-lifecycle/environments"
_ACTOR = str(uuid.uuid4())


@pytest.fixture
def env():
    shared_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    tenant_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        shared_engine, tables=[models.SharedLifecycleEnvironment.__table__]
    )
    Base.metadata.create_all(
        tenant_engine, tables=[models.EnvironmentSiteSubscription.__table__]
    )
    shared_s = sessionmaker(bind=shared_engine)
    tenant_s = sessionmaker(bind=tenant_engine)

    app = FastAPI()
    app.include_router(content_lifecycle.router, prefix="/api/v1")
    app.include_router(content_lifecycle_federation.router, prefix="/api/v1")

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

    role = {"value": "coordinator"}

    try:
        with patch.object(
            content_lifecycle.module_loader, "get_module", return_value=object()
        ), patch.object(JWTBearer, "__call__", _bypass_auth), patch(
            "backend.services.server_config_service.get_federation_role",
            lambda: role["value"],
        ):
            with TestClient(app) as client:
                yield SimpleNamespace(client=client, role=role)
    finally:
        shared_engine.dispose()
        tenant_engine.dispose()


def _make_env(env, name="Prod"):
    r = env.client.post(_ENV, json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestSubscriptions:
    def test_subscribe_list_unsubscribe(self, env):
        env_id = _make_env(env)
        site = str(uuid.uuid4())

        r = env.client.post(f"{_ENV}/{env_id}/subscriptions", json={"site_id": site})
        assert r.status_code == 200, r.text
        assert r.json()["site_id"] == site

        rows = env.client.get(f"{_ENV}/{env_id}/subscriptions").json()
        assert len(rows) == 1 and rows[0]["site_id"] == site

        d = env.client.delete(f"{_ENV}/{env_id}/subscriptions/{site}")
        assert d.status_code == 200
        assert env.client.get(f"{_ENV}/{env_id}/subscriptions").json() == []

    def test_subscribe_is_idempotent(self, env):
        env_id = _make_env(env)
        site = str(uuid.uuid4())
        env.client.post(f"{_ENV}/{env_id}/subscriptions", json={"site_id": site})
        env.client.post(f"{_ENV}/{env_id}/subscriptions", json={"site_id": site})
        assert len(env.client.get(f"{_ENV}/{env_id}/subscriptions").json()) == 1

    def test_non_coordinator_cannot_subscribe(self, env):
        env_id = _make_env(env)
        env.role["value"] = "site"
        r = env.client.post(
            f"{_ENV}/{env_id}/subscriptions", json={"site_id": str(uuid.uuid4())}
        )
        assert r.status_code == 400
        assert "coordinator" in r.json()["detail"].lower()

    def test_list_works_regardless_of_role(self, env):
        # Listing subscriptions is read-only, so it isn't coordinator-gated.
        env_id = _make_env(env)
        env.role["value"] = "site"
        assert env.client.get(f"{_ENV}/{env_id}/subscriptions").status_code == 200


# --- Site side: content_view_sync command actuation (byte pull) -------------


class _PullEngine:
    def build_pull_content_plan(
        self, source_url, mirror_root, cv_id, env_name, version
    ):
        return {
            "action": "pull_content",
            "source_url": source_url,
            "store_path": f"{mirror_root}/.content-views/{cv_id}/rv{version}",
            "commands": [{"argv": ["echo", "pull"]}],
        }


def _site_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[
            models.FederationReceivedCommand.__table__,
            models.MirrorRepository.__table__,
            models.MirrorSettings.__table__,
        ],
    )
    return engine


def _seed_received(session, params):
    import json

    cmd = models.FederationReceivedCommand(
        id=uuid.uuid4(),
        command_type="content_view_sync",
        parameters_json=json.dumps(params),
        status="queued",
    )
    session.add(cmd)
    session.commit()
    return cmd


class TestSiteSync:
    def test_handler_dispatches_pull_and_marks_in_progress(self):
        import json  # noqa: F401  (used indirectly via _seed_received)

        from backend.services import content_lifecycle_federation_sync as sync

        engine = _site_engine()
        make = sessionmaker(bind=engine)
        session = make()
        host = str(uuid.uuid4())
        session.add(models.MirrorSettings(mirror_root_path="/var/mirror"))
        session.add(
            models.MirrorRepository(
                name="os", package_manager="dnf", upstream_url="http://u/", host_id=host
            )
        )
        cmd = _seed_received(
            session,
            {
                "cv_id": "cv1",
                "env_name": "prod",
                "version": 3,
                "source_url": "http://coord/content-views/cv1/prod",
            },
        )
        cmd_id = cmd.id

        dispatched = {}

        def _enq(host_id, plan, timeout=300):
            dispatched.update(host_id=str(host_id), plan=plan)
            return "m1"

        def _reg(message_id, action, host_id, cv_version_id=""):
            dispatched.update(action=action, ref=cv_version_id)

        with patch.object(
            sync.module_loader, "get_module", return_value=_PullEngine()
        ), patch("backend.services.proplus_dispatch.enqueue_apply_plan", _enq), patch(
            "backend.services.proplus_dispatch.register_content_lifecycle_correlation",
            _reg,
        ):
            sync.handle_content_view_sync(session, cmd)
        session.commit()

        row = make().get(models.FederationReceivedCommand, cmd_id)
        assert row.status == "in_progress"
        assert dispatched["host_id"] == host
        assert dispatched["plan"]["action"] == "pull_content"
        assert dispatched["action"] == "cv_pull" and dispatched["ref"] == str(cmd_id)
        session.close()
        engine.dispose()

    def test_handler_fails_on_incomplete_params(self):
        from backend.services import content_lifecycle_federation_sync as sync

        engine = _site_engine()
        make = sessionmaker(bind=engine)
        session = make()
        cmd = _seed_received(session, {"cv_id": "cv1"})  # missing env/version/url
        cmd_id = cmd.id

        sync.handle_content_view_sync(session, cmd)
        session.commit()

        row = make().get(models.FederationReceivedCommand, cmd_id)
        assert row.status == "failed"
        session.close()
        engine.dispose()

    def test_handler_fails_on_malformed_params_json(self):
        from backend.services import content_lifecycle_federation_sync as sync

        engine = _site_engine()
        make = sessionmaker(bind=engine)
        session = make()
        cmd = models.FederationReceivedCommand(
            id=uuid.uuid4(),
            command_type="content_view_sync",
            parameters_json="{not valid json",
            status="queued",
        )
        session.add(cmd)
        session.commit()
        cmd_id = cmd.id

        sync.handle_content_view_sync(session, cmd)
        session.commit()

        row = make().get(models.FederationReceivedCommand, cmd_id)
        assert row.status == "failed"
        session.close()
        engine.dispose()

    def test_handler_fails_when_engine_not_loaded(self):
        from backend.services import content_lifecycle_federation_sync as sync

        engine = _site_engine()
        make = sessionmaker(bind=engine)
        session = make()
        host = str(uuid.uuid4())
        session.add(models.MirrorSettings(mirror_root_path="/var/mirror"))
        session.add(
            models.MirrorRepository(
                name="os", package_manager="dnf", upstream_url="http://u/", host_id=host
            )
        )
        cmd = _seed_received(
            session,
            {
                "cv_id": "cv1",
                "env_name": "prod",
                "version": 3,
                "source_url": "http://coord/content-views/cv1/prod",
            },
        )
        cmd_id = cmd.id

        with patch.object(sync.module_loader, "get_module", return_value=None):
            sync.handle_content_view_sync(session, cmd)
        session.commit()

        row = make().get(models.FederationReceivedCommand, cmd_id)
        assert row.status == "failed"
        session.close()
        engine.dispose()

    def test_handler_fails_without_mirror_host(self):
        from backend.services import content_lifecycle_federation_sync as sync

        engine = _site_engine()
        make = sessionmaker(bind=engine)
        session = make()
        # engine loaded + complete params, but the site has no mirror settings/host.
        cmd = _seed_received(
            session,
            {
                "cv_id": "cv1",
                "env_name": "prod",
                "version": 3,
                "source_url": "http://coord/content-views/cv1/prod",
            },
        )
        cmd_id = cmd.id

        with patch.object(sync.module_loader, "get_module", return_value=_PullEngine()):
            sync.handle_content_view_sync(session, cmd)
        session.commit()

        row = make().get(models.FederationReceivedCommand, cmd_id)
        assert row.status == "failed"
        session.close()
        engine.dispose()


class TestCvPullResult:
    def test_marks_command_completed(self):
        from backend.services import content_lifecycle_result_handlers as clrh

        engine = _site_engine()
        make = sessionmaker(bind=engine)
        session = make()
        cmd = models.FederationReceivedCommand(
            id=uuid.uuid4(), command_type="content_view_sync", status="in_progress"
        )
        session.add(cmd)
        session.commit()
        cmd_id = str(cmd.id)
        session.close()

        with patch.object(clrh, "_tenant_session_for_host", return_value=make()):
            clrh._apply_content_lifecycle_op_result(
                f"cv_pull:{cmd_id}", "host-1", {"status": "succeeded"}
            )

        row = make().get(models.FederationReceivedCommand, uuid.UUID(cmd_id))
        assert row.status == "completed"
        engine.dispose()

    def test_marks_command_failed(self):
        from backend.services import content_lifecycle_result_handlers as clrh

        engine = _site_engine()
        make = sessionmaker(bind=engine)
        session = make()
        cmd = models.FederationReceivedCommand(
            id=uuid.uuid4(), command_type="content_view_sync", status="in_progress"
        )
        session.add(cmd)
        session.commit()
        cmd_id = str(cmd.id)
        session.close()

        with patch.object(clrh, "_tenant_session_for_host", return_value=make()):
            clrh._apply_content_lifecycle_op_result(
                f"cv_pull:{cmd_id}", "host-1", {"status": "failed", "error": "wget 404"}
            )

        row = make().get(models.FederationReceivedCommand, uuid.UUID(cmd_id))
        assert row.status == "failed"
        engine.dispose()


class TestOpResultDispatch:
    """The by-action router for completed content_lifecycle_engine plans."""

    def test_unhandled_primary_id_is_logged_not_dropped(self):
        from backend.services import content_lifecycle_result_handlers as clrh

        # An unroutable correlation must never raise or silently vanish — it hits
        # the warn-and-return fallback (no tenant session is ever resolved).
        clrh._apply_content_lifecycle_op_result(
            "bogus-no-colon", "host-1", {"status": "succeeded"}
        )

    def test_log_only_op_is_logged(self):
        from backend.services import content_lifecycle_result_handlers as clrh

        # serve_content / set_env_symlink / repoint are log-only correlations:
        # they record the outcome without touching the DB.
        clrh._apply_content_lifecycle_op_result(
            "serve_content:cv-1", "host-1", {"status": "failed", "error": "nginx -t"}
        )


class TestAnnounce:
    def test_announces_to_each_subscribed_site(self):
        from backend.services import content_lifecycle_federation_sync as sync

        tenant_engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(
            tenant_engine, tables=[models.EnvironmentSiteSubscription.__table__]
        )
        tmake = sessionmaker(bind=tenant_engine)
        tenant_db = tmake()
        to_env = SimpleNamespace(id=uuid.uuid4(), name="prod")
        cv = SimpleNamespace(id=uuid.uuid4(), name="RHEL9")
        site = uuid.uuid4()
        tenant_db.add(
            models.EnvironmentSiteSubscription(environment_id=to_env.id, site_id=site)
        )
        tenant_db.commit()

        calls = []

        def _dispatch(session, *, command_type, target_site_id, parameters=None, **kw):
            calls.append(
                {"type": command_type, "site": target_site_id, "params": parameters}
            )
            return SimpleNamespace(id=uuid.uuid4())

        with patch(
            "backend.services.server_config_service.get_federation_role",
            lambda: "coordinator",
        ), patch(
            "backend.api.content_lifecycle._resolve_cv_serving_host",
            lambda c, s, t: ("host-1", "/var/mirror", []),
        ), patch(
            "backend.api.content_lifecycle._host_fqdn", lambda t, h: "coord.local"
        ), patch(
            "backend.persistence.db.get_engine", return_value=tenant_engine
        ), patch(
            "backend.services.federation_dispatch_service.dispatch_command", _dispatch
        ):
            sync.announce_promotion_to_sites(cv, to_env, 2, None, tenant_db)

        assert len(calls) == 1
        assert calls[0]["type"] == "content_view_sync"
        assert calls[0]["site"] == str(site)
        assert (
            calls[0]["params"]["source_url"]
            == f"http://coord.local/content-views/{cv.id}/prod"
        )
        assert calls[0]["params"]["version"] == 2
        tenant_db.close()
        tenant_engine.dispose()

    def test_noop_when_not_coordinator(self):
        from backend.services import content_lifecycle_federation_sync as sync

        calls = []
        with patch(
            "backend.services.server_config_service.get_federation_role",
            lambda: "site",
        ), patch(
            "backend.services.federation_dispatch_service.dispatch_command",
            lambda *a, **k: calls.append(1),
        ):
            sync.announce_promotion_to_sites(
                SimpleNamespace(id=uuid.uuid4(), name="x"),
                SimpleNamespace(id=uuid.uuid4(), name="prod"),
                1,
                None,
                None,
            )
        assert calls == []

    def test_noop_when_no_subscriptions(self):
        from backend.services import content_lifecycle_federation_sync as sync

        tenant_engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(
            tenant_engine, tables=[models.EnvironmentSiteSubscription.__table__]
        )
        tenant_db = sessionmaker(bind=tenant_engine)()
        calls = []
        with patch(
            "backend.services.server_config_service.get_federation_role",
            lambda: "coordinator",
        ), patch(
            "backend.services.federation_dispatch_service.dispatch_command",
            lambda *a, **k: calls.append(1),
        ):
            sync.announce_promotion_to_sites(
                SimpleNamespace(id=uuid.uuid4(), name="x"),
                SimpleNamespace(id=uuid.uuid4(), name="prod"),
                1,
                None,
                tenant_db,
            )
        assert calls == []
        tenant_db.close()
        tenant_engine.dispose()

    def test_swallows_serve_url_resolution_failure(self):
        from backend.services import content_lifecycle_federation_sync as sync

        tenant_engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(
            tenant_engine, tables=[models.EnvironmentSiteSubscription.__table__]
        )
        tenant_db = sessionmaker(bind=tenant_engine)()
        to_env = SimpleNamespace(id=uuid.uuid4(), name="prod")
        tenant_db.add(
            models.EnvironmentSiteSubscription(
                environment_id=to_env.id, site_id=uuid.uuid4()
            )
        )
        tenant_db.commit()

        def _boom(*_a, **_k):
            raise RuntimeError("no serving host")

        calls = []
        with patch(
            "backend.services.server_config_service.get_federation_role",
            lambda: "coordinator",
        ), patch(
            "backend.api.content_lifecycle._resolve_cv_serving_host", _boom
        ), patch(
            "backend.services.federation_dispatch_service.dispatch_command",
            lambda *a, **k: calls.append(1),
        ):
            # best-effort: the resolution failure is logged and swallowed.
            sync.announce_promotion_to_sites(
                SimpleNamespace(id=uuid.uuid4(), name="RHEL9"),
                to_env,
                2,
                None,
                tenant_db,
            )
        assert calls == []
        tenant_db.close()
        tenant_engine.dispose()

    def test_one_bad_site_never_blocks_the_rest(self):
        from backend.services import content_lifecycle_federation_sync as sync

        tenant_engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(
            tenant_engine, tables=[models.EnvironmentSiteSubscription.__table__]
        )
        tenant_db = sessionmaker(bind=tenant_engine)()
        to_env = SimpleNamespace(id=uuid.uuid4(), name="prod")
        tenant_db.add(
            models.EnvironmentSiteSubscription(
                environment_id=to_env.id, site_id=uuid.uuid4()
            )
        )
        tenant_db.commit()

        def _dispatch_boom(*_a, **_k):
            raise RuntimeError("site unreachable")

        with patch(
            "backend.services.server_config_service.get_federation_role",
            lambda: "coordinator",
        ), patch(
            "backend.api.content_lifecycle._resolve_cv_serving_host",
            lambda c, s, t: ("host-1", "/var/mirror", []),
        ), patch(
            "backend.api.content_lifecycle._host_fqdn", lambda t, h: "coord.local"
        ), patch(
            "backend.persistence.db.get_engine", return_value=tenant_engine
        ), patch(
            "backend.services.federation_dispatch_service.dispatch_command",
            _dispatch_boom,
        ):
            # A failing per-site dispatch is caught; the call completes cleanly.
            sync.announce_promotion_to_sites(
                SimpleNamespace(id=uuid.uuid4(), name="RHEL9"),
                to_env,
                2,
                None,
                tenant_db,
            )
        tenant_db.close()
        tenant_engine.dispose()
