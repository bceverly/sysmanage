"""Live-engine HTTP smoke test for the federation SITE engine.

Symmetric to ``test_federation_engine_http_smoke`` (the controller side): loads
the actual compiled ``federation_site_engine`` ``.so``, mounts its router under
``_cython_compat`` exactly as ``proplus_routes`` does, and drives the INBOUND
endpoints (coordinator → site) over real HTTP with a ``TestClient``.

These inbound routes (``/site/policies``, ``/site/commands``) and their
``_verify_coordinator_bearer`` dependency are exactly where the site-side
``Header``/``request: Request`` Cython-introspection bugs lived — this guards
that class of regression on the site engine, which nothing else covers.

Skips automatically when the engine ``.so`` isn't built (OSS-only checkout).
"""

# pylint: disable=redefined-outer-name,import-outside-toplevel

import hashlib
import importlib.util
import logging
import sys
import sysconfig
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models
from backend.persistence.db import Base, get_db
from backend.services import federation_coordinator_service as coord_svc

pytestmark = pytest.mark.integration

_INBOUND_TOKEN = "smoke-inbound-bearer"


def _candidate_so_paths():
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    candidates = []
    proplus = (
        Path.home() / "dev" / "sysmanage-professional-plus" / "storage" / "modules"
    )
    version_dir = proplus / "federation_site_engine"
    if version_dir.exists():
        for version in sorted(version_dir.iterdir(), reverse=True):
            py_dir = version / "linux" / "x86_64" / py
            if py_dir.exists():
                ext = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
                candidates.extend(sorted(py_dir.glob(f"*{ext}")))
    candidates.append(
        Path("/var/lib/sysmanage/modules") / f"federation_site_engine_{py}.so"
    )
    return candidates


def _load_engine():
    for path in _candidate_so_paths():
        if path.exists():
            spec = importlib.util.spec_from_file_location(
                "federation_site_engine", path
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def _noop_gate(*_args, **_kwargs):
    def deco(func):
        return func

    return deco


def _stub_user():
    return {"id": "smoke-test-user"}


@pytest.fixture(scope="module")
def engine():
    mod = _load_engine()
    if mod is None:
        pytest.skip(
            "federation_site_engine .so not available — build the Pro+ engine "
            "first (this smoke test needs the real compiled engine)"
        )
    return mod


@pytest.fixture
def harness(engine):
    """Mount the real site engine router on an in-memory DB whose coordinator
    singleton is enrolled with a known inbound bearer.  Yields the client."""
    from backend.api.proplus_routes import _cython_compat

    sa_engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(sa_engine)
    session_factory = sessionmaker(bind=sa_engine, expire_on_commit=False)

    with session_factory() as sess:
        coord_svc.start_enrollment(
            sess, coordinator_url="https://coord", coordinator_tls_cert_pem="c"
        )
        coord_svc.mark_enrolled(
            sess,
            site_id=str(uuid.uuid4()),
            site_tls_cert_pem="site-cert",
            coordinator_inbound_bearer_token_hash=hashlib.sha256(
                _INBOUND_TOKEN.encode("utf-8")
            ).hexdigest(),
        )
        sess.commit()

    def _test_get_db():
        sess = session_factory()
        try:
            yield sess
        finally:
            sess.close()

    app = FastAPI()
    with _cython_compat():
        router = engine.get_federation_site_router(
            db_dependency=Depends(get_db),
            auth_dependency=Depends(_stub_user),
            feature_gate=_noop_gate,
            module_gate=_noop_gate,
            models=models,
            http_exception=HTTPException,
            status_codes=status,
            logger=logging.getLogger("federation-site-smoke"),
        )
        app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = _test_get_db

    client = TestClient(app)
    try:
        yield client
    finally:
        sa_engine.dispose()


def _auth():
    return {"Authorization": f"Bearer {_INBOUND_TOKEN}"}


def test_inbound_policy_accepts_coordinator_bearer(harness):
    """coordinator → site policy push succeeds over real HTTP (guards the
    site-side ``request: Request`` 422 regression)."""
    resp = harness.post(
        "/api/v1/federation/site/policies",
        json={
            "policy_id": str(uuid.uuid4()),
            "policy_type": "update_profile",
            "name": "default",
            "definition": {"channel": "stable"},
            "version": 1,
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text


def test_inbound_command_accepts_coordinator_bearer(harness):
    resp = harness.post(
        "/api/v1/federation/site/commands",
        json={
            "command_id": str(uuid.uuid4()),
            "command_type": "reboot",
            "parameters": {},
            "target_host_ids": [],
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text


def test_inbound_rejects_missing_bearer(harness):
    resp = harness.post(
        "/api/v1/federation/site/policies",
        json={"policy_id": str(uuid.uuid4()), "policy_type": "x", "name": "y"},
    )
    assert resp.status_code == 401
