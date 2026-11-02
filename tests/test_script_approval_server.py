# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A host whose agent runs only approved scripts (script_approval_required):
the server stores what the agent reports and refuses one-off runs to it."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api import host_utils
from backend.api.message_handlers_core import _build_system_info_update_values
from backend.api.scripts import routes_executions
from backend.api.scripts.models import ScriptExecutionRequest
from backend.persistence import models


def _host(db_session, required):
    host = models.Host(
        fqdn="locked.example",
        active=True,
        status="up",
        approval_status="approved",
        script_approval_required=required,
    )
    db_session.add(host)
    db_session.commit()
    return str(host.id)


def _execute(engine, host_id):
    user = SimpleNamespace(has_role=lambda _role: True)
    request = ScriptExecutionRequest(
        host_id=host_id, script_content="id", shell_type="bash"
    )
    with patch.object(
        routes_executions,
        "request_sessionmaker",
        return_value=sessionmaker(bind=engine),
    ), patch.object(routes_executions, "load_user_on_main", return_value=user):
        return asyncio.run(routes_executions.execute_script(request, current_user="op"))


def test_a_one_off_run_to_a_host_that_requires_approval_is_refused(engine, db_session):
    host_id = _host(db_session, True)
    with pytest.raises(HTTPException) as refused:
        _execute(engine, host_id)
    assert refused.value.status_code == 400
    assert "requires approval" in refused.value.detail


def test_update_or_create_host_stores_the_reported_setting(db_session):
    host = asyncio.run(
        host_utils.update_or_create_host(
            db_session, "new.example", script_approval_required=True
        )
    )
    assert host.script_approval_required is True
    # An older agent reports nothing: the stored setting stays.
    host = asyncio.run(host_utils.update_or_create_host(db_session, "new.example"))
    assert host.script_approval_required is True
    host = asyncio.run(
        host_utils.update_or_create_host(
            db_session, "new.example", script_approval_required=False
        )
    )
    assert host.script_approval_required is False


def test_system_info_carries_the_setting_into_the_host_update():
    values, _privileged = _build_system_info_update_values(
        {"script_approval_required": True},
        SimpleNamespace(),
        SimpleNamespace(approval_status="pending"),
        "Linux",
    )
    assert values["script_approval_required"] is True
    values, _privileged = _build_system_info_update_values(
        {}, SimpleNamespace(), SimpleNamespace(approval_status="pending"), "Linux"
    )
    assert "script_approval_required" not in values
