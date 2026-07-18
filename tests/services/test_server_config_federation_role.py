# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 12 federation-role accessors in server_config_service
(separate axis from the air-gap server_role).  Drives ``db.get_session_local``
at an isolated in-memory DB so the role round-trips deterministically without
touching the real configured database.
"""

# pylint: disable=missing-function-docstring,redefined-outer-name

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.server_configuration import ServerConfiguration
from backend.services import server_config_service as svc


@pytest.fixture
def isolated_db(monkeypatch):
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables["server_configuration"]]
    )
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("backend.persistence.db.get_session_local", lambda: Session)
    yield Session
    engine.dispose()


def test_default_when_unset(isolated_db):
    assert svc.get_federation_role() == "none"


def test_set_and_get(isolated_db):
    assert svc.set_federation_role("coordinator") == "coordinator"
    assert svc.get_federation_role() == "coordinator"


def test_invalid_role_raises(isolated_db):
    with pytest.raises(ValueError):
        svc.set_federation_role("overlord")


def test_independent_of_server_role(isolated_db):
    # The two axes live in the same singleton row but never clobber each other.
    svc.set_server_role("collector")
    svc.set_federation_role("site")
    assert svc.get_server_role() == "collector"
    assert svc.get_federation_role() == "site"
    # And the reverse ordering.
    svc.set_federation_role("coordinator")
    assert svc.get_server_role() == "collector"  # unchanged


def test_singleton_stays_one_row(isolated_db):
    svc.set_federation_role("site")
    svc.set_federation_role("coordinator")
    svc.set_server_role("repository")
    with isolated_db() as session:
        assert session.query(ServerConfiguration).count() == 1


def test_invalid_server_role_raises(isolated_db):
    with pytest.raises(ValueError):
        svc.set_server_role("overlord")


def test_server_role_default_when_unset(isolated_db):
    assert svc.get_server_role() == "standard"


# ---------------------------------------------------------------------
# air-gap import device accessors
# ---------------------------------------------------------------------


def test_import_device_default_none(isolated_db):
    assert svc.get_import_device() is None


def test_import_device_set_and_get(isolated_db):
    assert svc.set_import_device("/dev/sr0") == "/dev/sr0"
    assert svc.get_import_device() == "/dev/sr0"


def test_import_device_clears_to_none(isolated_db):
    svc.set_import_device("/dev/sr0")
    svc.set_import_device(None)
    assert svc.get_import_device() is None


def test_import_device_set_creates_singleton_when_row_absent(isolated_db):
    # Fresh DB with no row: set_import_device must create it (with the
    # default air_gap_role) rather than crash.
    with isolated_db() as session:
        assert session.query(ServerConfiguration).count() == 0
    svc.set_import_device("/dev/cd0")
    assert svc.get_import_device() == "/dev/cd0"
    with isolated_db() as session:
        assert session.query(ServerConfiguration).count() == 1


# ---------------------------------------------------------------------
# graceful degradation on DB failure
# ---------------------------------------------------------------------


def test_get_server_role_degrades_on_db_error(monkeypatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("backend.persistence.db.get_session_local", _boom)
    assert svc.get_server_role() == "standard"


def test_get_federation_role_degrades_on_db_error(monkeypatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("backend.persistence.db.get_session_local", _boom)
    assert svc.get_federation_role() == "none"


def test_get_import_device_degrades_on_db_error(monkeypatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("backend.persistence.db.get_session_local", _boom)
    assert svc.get_import_device() is None
