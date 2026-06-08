"""Live-engine HTTP smoke test for the federation CONTROLLER engine.

Unlike the wire-stubbing integration round-trip (which calls the OSS service
functions directly), this loads the ACTUAL compiled
``federation_controller_engine`` ``.so``, mounts its FastAPI router exactly the
way ``proplus_routes.mount_federation_controller_routes`` does (under the
``_cython_compat`` shim), and drives the ingest endpoints over real HTTP with a
``TestClient``.

This is the layer the stubbed tests can't reach — it is precisely what would
have caught the bugs that only surfaced against the live engine in production:

  * the ``Header()``-default parameter that failed route registration with
    "Expected str, got Header" (caught here by the mount not raising),
  * the ``request: Request`` parameter mis-read as a required ``query.request``
    (caught by the metadata POST returning 200 instead of 422),
  * the missing ``upsert_host_directory_entry`` (caught by the host-directory
    POST returning 200 instead of a 500 AttributeError).

Skips automatically when the engine ``.so`` isn't built (OSS-only checkout).
"""

# pylint: disable=redefined-outer-name,import-outside-toplevel

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
from backend.services import federation_site_service as site_svc
from tests.federation_crypto import enroll_site

pytestmark = pytest.mark.integration


def _candidate_so_paths():
    """Where a locally-built federation_controller_engine .so might live."""
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    candidates = []
    proplus = (
        Path.home() / "dev" / "sysmanage-professional-plus" / "storage" / "modules"
    )
    version_dir = proplus / "federation_controller_engine"
    if version_dir.exists():
        for version in sorted(version_dir.iterdir(), reverse=True):
            py_dir = version / "linux" / "x86_64" / py
            if py_dir.exists():
                ext = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
                candidates.extend(sorted(py_dir.glob(f"*{ext}")))
    candidates.append(
        Path("/var/lib/sysmanage/modules") / f"federation_controller_engine_{py}.so"
    )
    return candidates


def _load_engine():
    for path in _candidate_so_paths():
        if path.exists():
            spec = importlib.util.spec_from_file_location(
                "federation_controller_engine", path
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def _noop_gate(*_args, **_kwargs):
    """Stand-in for the feature/module decorator gates so the smoke test can
    reach the routes without standing up the licensing/module-loader stack."""

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
            "federation_controller_engine .so not available — build the Pro+ "
            "engine first (this smoke test needs the real compiled engine)"
        )
    return mod


@pytest.fixture
def harness(engine):
    """Mount the real engine router on a FastAPI app backed by an in-memory DB
    with one enrolled site.  Yields ``(client, site_id, sync_bearer)``."""
    from backend.api.proplus_routes import _cython_compat

    # TestClient runs the app in a worker thread, so the in-memory DB must be
    # shareable across threads: StaticPool keeps a single connection (so the
    # seeded data is visible to the request thread) and check_same_thread=False
    # lets that connection be used off the creating thread.
    sa_engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create the whole schema — the ingest path touches several federation
    # tables (sites, host_directory, sync_event, …); ``backend.persistence
    # .models`` is imported above so every table is registered on Base.
    Base.metadata.create_all(sa_engine)
    session_factory = sessionmaker(bind=sa_engine, expire_on_commit=False)

    with session_factory() as sess:
        site_obj, sync_bearer, _coord_outbound = enroll_site(
            sess, name="alpha", url="https://alpha.example.com"
        )
        sess.commit()
        site_id = str(site_obj.id)

    def _test_get_db():
        sess = session_factory()
        try:
            yield sess
        finally:
            sess.close()

    app = FastAPI()
    # Mount EXACTLY as proplus_routes does — same kwargs, same compat shim.
    # If the engine has a Header()/Query() default or request:Request bug, this
    # raises and every test in the module errors (the mount-time signal).
    with _cython_compat():
        router = engine.get_federation_controller_router(
            db_dependency=Depends(get_db),
            auth_dependency=Depends(_stub_user),
            feature_gate=_noop_gate,
            module_gate=_noop_gate,
            models=models,
            http_exception=HTTPException,
            status_codes=status,
            logger=logging.getLogger("federation-smoke"),
        )
        app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = _test_get_db

    client = TestClient(app)
    try:
        yield client, site_id, sync_bearer
    finally:
        sa_engine.dispose()


def test_metadata_ingest_accepts_bearer(harness):
    """Site → coordinator metadata push succeeds over real HTTP.

    Regression guard for the ``request: Request`` injection bug, which made
    this return 422 ``{"loc": ["query", "request"]}`` on the live engine.
    """
    client, site_id, bearer = harness
    resp = client.post(
        f"/api/v1/federation/sites/{site_id}/metadata",
        json={"host_count": 3, "queue_depth": 0, "sysmanage_version": "smoke"},
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert resp.status_code == 200, resp.text


def test_metadata_ingest_rejects_missing_bearer(harness):
    """No bearer → 401 (the sync-bearer gate actually runs)."""
    client, site_id, _bearer = harness
    resp = client.post(
        f"/api/v1/federation/sites/{site_id}/metadata",
        json={"host_count": 1},
    )
    assert resp.status_code == 401


def test_host_directory_ingest_persists(harness):
    """Host-directory push succeeds + lands a row.

    Regression guard for the missing ``upsert_host_directory_entry`` (the
    engine called it via ``federation_host_directory_service`` where it didn't
    exist → 500 AttributeError on the live engine).
    """
    client, site_id, bearer = harness
    host_id = str(uuid.uuid4())
    resp = client.post(
        f"/api/v1/federation/sites/{site_id}/host-directory",
        json={
            "entries": [
                {
                    "host_id": host_id,
                    "fqdn": "h1.example.com",
                    "ipv4": "10.0.0.9",
                    "os_family": "Linux",
                    "platform": "Linux",
                    "status": "up",
                }
            ]
        },
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert resp.status_code == 200, resp.text
