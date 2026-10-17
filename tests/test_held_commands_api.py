# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The held-commands endpoints: the host status carries the held count, the
list shows only this tenant's held rows, cancel is audited and refused for
anything not held, and non-administrators need the right role."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import maintenance_windows as mod
from backend.persistence import models
from backend.persistence.db import Base
from backend.security.roles import SecurityRoles
from backend.services.maintenance_window_service import DEFERRED_MARKER
from backend.websocket.queue_enums import QueueDirection, QueueStatus


def _user(admin=False, roles=()):
    user = MagicMock()
    user.is_admin = admin
    user.id = uuid.uuid4()
    user.userid = "operator@example.invalid"
    user.has_role = lambda role: role in roles
    return user


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def tenant(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(mod, "_sessionmaker", lambda: sessionmaker(bind=engine))
    yield engine
    # StaticPool holds its one connection for the engine's lifetime; left to
    # the garbage collector, it closes mid-way through some LATER test, whose
    # ResourceWarning (an error under this suite's filterwarnings) then fails
    # whichever test happened to be running.
    engine.dispose()


def _held_row(engine, host_id, held=True, token="C1-SECRET"):
    with sessionmaker(bind=engine)() as db:
        if db.get(models.Host, host_id) is None:
            db.add(models.Host(id=host_id, fqdn="vm.example.invalid", active=True,
                               approval_status="approved"))  # fmt: skip
        row = models.MessageQueue(
            id=uuid.uuid4(), host_id=host_id, message_id=str(uuid.uuid4()),
            direction=QueueDirection.OUTBOUND, message_type="command",
            message_data=json.dumps({"data": {"command_type": "ubuntu_pro_attach",
                                              "parameters": {"token": token}}}),
            status=QueueStatus.PENDING, priority="normal", retry_count=0, max_retries=3,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            error_message=DEFERRED_MARKER if held else None,
        )  # fmt: skip
        db.add(row)
        db.commit()
        return row.id


def _run(coro):
    return asyncio.run(coro)


def test_host_status_carries_the_held_count(tenant):
    host = uuid.uuid4()
    _held_row(tenant, host)
    _held_row(tenant, host, held=False)
    viewer = _user(roles={SecurityRoles.VIEW_HOST_DETAILS})
    status = _run(mod.host_window_status(str(host), current_user=viewer))
    assert status["held_commands"]["count"] == 1


def test_host_status_needs_view_rights(tenant):
    with pytest.raises(HTTPException) as exc:
        _run(mod.host_window_status(str(uuid.uuid4()), current_user=_user()))
    assert exc.value.status_code == 403


def test_the_list_is_this_tenants_and_never_shows_the_token(tenant):
    elsewhere = _engine()
    try:
        _held_row(elsewhere, uuid.uuid4())  # another tenant's database
        mine = _held_row(tenant, uuid.uuid4())
        out = _run(
            mod.list_held_commands(limit=50, offset=0, current_user=_user(admin=True))
        )
    finally:
        elsewhere.dispose()
    assert [item["id"] for item in out["items"]] == [str(mine)]
    assert "C1-SECRET" not in json.dumps(out)
    assert out["items"][0]["command_type"] == "ubuntu_pro_attach"


def test_cancel_is_audited(tenant):
    row_id = _held_row(tenant, uuid.uuid4())
    assert _run(
        mod.cancel_held_command(str(row_id), current_user=_user(admin=True))
    ) == {"result": True}
    with sessionmaker(bind=tenant)() as db:
        row = db.get(models.MessageQueue, row_id)
        assert row.status == QueueStatus.FAILED
        assert row.error_message == "canceled by operator@example.invalid"
        audit = db.query(models.AuditLog).one()
        assert "C1-SECRET" not in json.dumps(audit.details)


def test_cancel_refuses_a_command_that_is_not_held(tenant):
    row_id = _held_row(tenant, uuid.uuid4(), held=False)
    with pytest.raises(HTTPException) as exc:
        _run(mod.cancel_held_command(str(row_id), current_user=_user(admin=True)))
    assert exc.value.status_code == 409


def test_cancel_needs_admin_or_the_queue_role(tenant):
    row_id = _held_row(tenant, uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        _run(mod.cancel_held_command(str(row_id), current_user=_user()))
    assert exc.value.status_code == 403
    queue_admin = _user(roles={SecurityRoles.DELETE_QUEUE_MESSAGE})
    assert _run(mod.cancel_held_command(str(row_id), current_user=queue_admin))[
        "result"
    ]
