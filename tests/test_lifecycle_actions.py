# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for backend/api/lifecycle_actions.py — release-upgrade dispatch (Phase 14.3)."""

import types
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api import lifecycle_actions as mod
from backend.api.lifecycle_actions import ReleaseUpgradeRequest, upgrade_host_release
from backend.persistence import models


def _seed_host(db):
    host_id = uuid.uuid4()
    db.add(
        models.Host(
            id=host_id,
            fqdn="rel-host.example.com",
            ipv4="192.168.1.90",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
    )
    db.commit()
    return host_id


def _fake_engine(job):
    """A stand-in lifecycle_engine whose service returns a fixed job dict."""
    svc = MagicMock()
    svc.create_upgrade_job.return_value = job
    return types.SimpleNamespace(_lifecycle_service=svc)


@pytest.mark.asyncio
async def test_unlicensed_is_402(db_session):
    with patch.object(mod.license_service, "has_feature", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await upgrade_host_release(
                str(uuid.uuid4()),
                ReleaseUpgradeRequest(),
                tenant_db=db_session,
                shared_db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_missing_host_is_404(db_session):
    with patch.object(
        mod.license_service, "has_feature", return_value=True
    ), patch.object(mod.license_service, "has_module", return_value=True), patch.object(
        mod.module_loader, "get_module", return_value=_fake_engine({})
    ):
        with pytest.raises(HTTPException) as exc:
            await upgrade_host_release(
                str(uuid.uuid4()),
                ReleaseUpgradeRequest(),
                tenant_db=db_session,
                shared_db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_creates_job_and_dispatches_command(db_session):
    host_id = _seed_host(db_session)
    job = {
        "id": "job-1",
        "method": "do-release-upgrade",
        "to_version": "24.04",
        "from_version": "22.04",
    }
    engine = _fake_engine(job)

    with patch.object(
        mod.license_service, "has_feature", return_value=True
    ), patch.object(mod.license_service, "has_module", return_value=True), patch.object(
        mod.module_loader, "get_module", return_value=engine
    ), patch.object(
        mod.queue_ops, "enqueue_message"
    ) as enqueue, patch.object(
        mod.AuditService, "log"
    ):
        result = await upgrade_host_release(
            str(host_id),
            ReleaseUpgradeRequest(to_version="24.04"),
            tenant_db=db_session,
            shared_db=db_session,
            current_user="admin@example.com",
        )

    assert result["result"] is True
    assert result["job"] == job
    # The engine created the job with the request's tenant + shared sessions.
    engine._lifecycle_service.create_upgrade_job.assert_called_once()
    # An "os_release_upgrade" command was enqueued OUTBOUND for the host.
    kwargs = enqueue.call_args.kwargs
    assert kwargs["message_type"] == "command"
    assert kwargs["host_id"] == str(host_id)
    cmd = kwargs["message_data"]
    payload = cmd.get("data", cmd)
    assert payload["command_type"] == "os_release_upgrade"
    assert payload["parameters"]["job_id"] == "job-1"
    assert payload["parameters"]["method"] == "do-release-upgrade"
