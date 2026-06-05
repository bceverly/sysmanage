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
