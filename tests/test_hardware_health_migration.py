# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Migration q42hwhealth (Phase 23.1 S2): the hardware component and event
tables, the host summary columns and the Manage Hardware Health role --
idempotent, granted to each administrator once, downgradable."""

import os
import tempfile
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from tests.test_machine_migration import _alembic, _columns, _grants

_HOST_COLUMNS = {"hardware_state", "hardware_reported_at", "hardware_sources"}
_ROLE = "Manage Hardware Health"


def test_q42_builds_hardware_health_and_grants_the_role_once():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["upgrade", "q41alertgroup"], db)
        engine = create_engine(f"sqlite:///{db}")
        with sessionmaker(bind=engine)() as session:
            session.add(
                models.User(
                    id=uuid.uuid4(),
                    userid="admin@example.com",
                    active=True,
                    is_admin=True,
                )
            )
            session.commit()
        engine.dispose()
        _alembic(["upgrade", "head"], db)
        assert _HOST_COLUMNS <= _columns(db, "host")
        assert {"host_id", "kind", "ident", "state", "state_since"} <= _columns(
            db, "hardware_component"
        )
        assert {"from_state", "to_state", "acknowledged_at", "resolved_at"} <= (
            _columns(db, "hardware_event")
        )
        assert _grants(db, _ROLE) == 1
        # over the schema it already built: no error, no second grant
        _alembic(["stamp", "q41alertgroup"], db)
        _alembic(["upgrade", "head"], db)
        assert _grants(db, _ROLE) == 1
        _alembic(["downgrade", "q41alertgroup"], db)
        assert not _HOST_COLUMNS & _columns(db, "host")
        assert not _columns(db, "hardware_component")
        assert not _columns(db, "hardware_event")
        assert _grants(db, _ROLE) == 0
    finally:
        if os.path.exists(db):
            os.unlink(db)


def test_q43_builds_the_install_table_idempotently():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["upgrade", "head"], db)
        columns = {"host_id", "package", "status", "attempts", "command_id"}
        assert columns <= _columns(db, "hardware_tool_install")
        _alembic(["stamp", "q42hwhealth"], db)
        _alembic(["upgrade", "head"], db)  # over the table it already built
        _alembic(["downgrade", "q42hwhealth"], db)
        assert not _columns(db, "hardware_tool_install")
    finally:
        if os.path.exists(db):
            os.unlink(db)
