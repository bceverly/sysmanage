# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Image-mode host action tests (Phase 17.3, Slices 4-5).

Covers the persistence helper that lands agent-reported image-mode state on the
host row, and the stage/apply/rollback dispatch endpoints: the 402 Enterprise
gate, the not-image-mode 400, unknown-host 404, and that each action builds the
right engine plan and dispatches it via apply_deployment_plan (plus the extra
update_os_version refresh after a no-reboot stage).
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

from backend.api import image_mode_actions as ima
from backend.api.handlers.os_hardware_handlers import _apply_image_mode_fields
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.persistence import models
from backend.persistence.db import Base
from backend.persistence.partitions import get_tenant_db

_BASE = "/api/v1/image-mode/host"


# ----------------------------------------------------------- persistence unit


def _os_info(**over):
    base = {
        "is_image_mode": True,
        "image_backend": "bootc",
        "booted_image_ref": "quay.io/fedora/fedora-bootc:41",
        "booted_image_digest": "sha256:" + "2" * 64,
        "staged_image_ref": "quay.io/fedora/fedora-bootc:41",
        "staged_image_digest": "sha256:" + "1" * 64,
        "rollback_available": True,
    }
    base.update(over)
    return base


def test_apply_fields_sets_image_mode_state():
    host = SimpleNamespace()
    _apply_image_mode_fields(host, _os_info())
    assert host.is_image_mode is True
    assert host.image_backend == "bootc"
    assert host.booted_image_digest.endswith("2" * 4)
    assert host.rollback_available is True
    assert host.image_mode_updated_at is not None


def test_apply_fields_clears_when_left_image_mode():
    host = SimpleNamespace()
    _apply_image_mode_fields(host, {"is_image_mode": False})
    assert host.is_image_mode is False
    assert host.image_backend is None
    assert host.booted_image_ref is None
    assert host.rollback_available is None


def test_apply_fields_ignored_when_key_absent():
    # Non-Linux / older agent: no is_image_mode key → leave columns untouched.
    host = SimpleNamespace(is_image_mode="SENTINEL")
    _apply_image_mode_fields(host, {"distribution": "Ubuntu"})
    assert host.is_image_mode == "SENTINEL"
    _apply_image_mode_fields(host, None)
    assert host.is_image_mode == "SENTINEL"


# ----------------------------------------------------------- dispatch harness


class _FakeImageEngine:
    class ImageModeError(Exception):
        pass

    def __init__(self):
        self.calls = []

    # ``bypass_driver`` mirrors the real engine's signature (2026-08-24): the
    # router must be able to pass the Zincati bypass through, and a fake that
    # silently accepted **kwargs would hide a router that stopped sending it.
    def build_image_stage_plan(self, backend, target_ref=None, bypass_driver=True):
        self.calls.append(("stage", backend, target_ref))
        self.bypass = bypass_driver
        return self._plan("image_mode_stage", backend)

    def build_image_apply_plan(self, backend, bypass_driver=True):
        self.calls.append(("apply", backend, None))
        self.bypass = bypass_driver
        return self._plan("image_mode_apply", backend)

    def build_image_rollback_plan(self, backend):
        # No bypass parameter ON PURPOSE: rpm-ostree rollback rejects the flag,
        # so a router that tried to pass one here must fail loudly.
        self.calls.append(("rollback", backend, None))
        return self._plan("image_mode_rollback", backend)

    @staticmethod
    def _plan(action, backend):
        return {
            "engine": "image_mode_engine",
            "action": action,
            "backend": backend,
            "files": [],
            "commands": [{"argv": ["sudo", backend, "upgrade"]}],
        }


@pytest.fixture
def env():
    tenant_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(tenant_engine, tables=[models.Host.__table__])
    tenant_s = sessionmaker(bind=tenant_engine)

    app = FastAPI()
    app.include_router(ima.router, prefix="/api/v1")

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

    enqueued = []

    def _fake_enqueue(**kwargs):
        enqueued.append(kwargs["message_data"])
        return "msg-1"

    engine = _FakeImageEngine()
    modules = {"image_mode_engine": engine}

    with patch.object(
        ima.module_loader, "get_module", side_effect=modules.get
    ), patch.object(JWTBearer, "__call__", _bypass_auth), patch.object(
        ima.queue_ops, "enqueue_message", side_effect=_fake_enqueue
    ), patch.object(
        ima.AuditService, "log"
    ), patch.object(
        ima.db_module, "get_engine", return_value=tenant_engine
    ):
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                tenant_s=tenant_s,
                enqueued=enqueued,
                engine=engine,
                modules=modules,
            )
    tenant_engine.dispose()


def _seed_host(env, is_image_mode=True, backend="bootc"):
    hid = str(uuid.uuid4())
    tdb = env.tenant_s()
    try:
        tdb.add(
            models.Host(
                id=hid,
                fqdn="img-host",
                active=True,
                is_image_mode=is_image_mode,
                image_backend=backend if is_image_mode else None,
            )
        )
        tdb.commit()
        return hid
    finally:
        tdb.close()


# ------------------------------------------------------------------- gate/400


def test_stage_402_when_unlicensed(env):
    env.modules.clear()
    hid = _seed_host(env)
    r = env.client.post(f"{_BASE}/{hid}/stage", json={})
    assert r.status_code == 402


def test_404_unknown_host(env):
    r = env.client.post(f"{_BASE}/{uuid.uuid4()}/apply")
    assert r.status_code == 404


def test_400_when_not_image_mode(env):
    hid = _seed_host(env, is_image_mode=False)
    r = env.client.post(f"{_BASE}/{hid}/stage", json={})
    assert r.status_code == 400


# ------------------------------------------------------------------- dispatch


def test_stage_dispatches_plan_and_refresh(env):
    hid = _seed_host(env, backend="bootc")
    r = env.client.post(f"{_BASE}/{hid}/stage", json={})
    assert r.status_code == 200
    assert r.json()["action"] == "stage"
    assert env.engine.calls == [("stage", "bootc", None)]
    # a no-reboot stage enqueues the plan AND an os-version refresh
    assert len(env.enqueued) == 2


def test_stage_with_target_ref(env):
    hid = _seed_host(env, backend="bootc")
    ref = "quay.io/fedora/fedora-bootc:42"
    r = env.client.post(f"{_BASE}/{hid}/stage", json={"target_ref": ref})
    assert r.status_code == 200
    assert env.engine.calls == [("stage", "bootc", ref)]


def test_apply_dispatches_once(env):
    hid = _seed_host(env, backend="rpm-ostree")
    r = env.client.post(f"{_BASE}/{hid}/apply")
    assert r.status_code == 200
    assert env.engine.calls == [("apply", "rpm-ostree", None)]
    # apply reboots -> no extra refresh command
    assert len(env.enqueued) == 1


def test_rollback_dispatches_once(env):
    hid = _seed_host(env, backend="bootc")
    r = env.client.post(f"{_BASE}/{hid}/rollback")
    assert r.status_code == 200
    assert env.engine.calls == [("rollback", "bootc", None)]
    assert len(env.enqueued) == 1


# ------------------------------------------------- update-driver bypass (S19)


def test_stage_defaults_to_bypassing_the_host_update_driver(env):
    """Default ON.  Fedora CoreOS hands updates to Zincati and rpm-ostree then
    refuses -- "Updates and deployments are driven by Zincati", exit 1 --
    measured on a live FCOS 44 host 2026-08-24.  Without the bypass SysManage
    cannot update FCOS at all."""
    hid = _seed_host(env, backend="rpm-ostree")
    r = env.client.post(f"{_BASE}/{hid}/stage", json={})
    assert r.status_code == 200
    assert env.engine.bypass is True


def test_apply_defaults_to_bypassing_the_host_update_driver(env):
    hid = _seed_host(env, backend="rpm-ostree")
    r = env.client.post(f"{_BASE}/{hid}/apply", json={})
    assert r.status_code == 200
    assert env.engine.bypass is True


def test_bypass_can_be_turned_off_per_request(env):
    """It is a setting, not a hardcode: an estate that wants its own update
    driver left in charge can say so, and then owns the consequence."""
    hid = _seed_host(env, backend="rpm-ostree")
    r = env.client.post(f"{_BASE}/{hid}/stage", json={"bypass_update_driver": False})
    assert r.status_code == 200
    assert env.engine.bypass is False


def test_apply_still_works_without_a_body(env):
    """The new body is optional -- an existing client that posts nothing must
    keep working, and get the default."""
    hid = _seed_host(env, backend="rpm-ostree")
    r = env.client.post(f"{_BASE}/{hid}/apply")
    assert r.status_code == 200
    assert env.engine.bypass is True
