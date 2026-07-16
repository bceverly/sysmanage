# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for backend/api/advisory_actions.py — install by advisory (Phase 14.1)."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.api import advisory_actions as mod
from backend.api.advisory_actions import AdvisoryInstallRequest, install_by_advisory
from backend.persistence.models import HostApplicableAdvisory

NOW = datetime(2026, 7, 12, 12, 0)


def _seed(db, host_id, advisory_id, packages, status="applicable", source=None):
    for name in packages:
        db.add(
            HostApplicableAdvisory(
                host_id=host_id,
                advisory_id=advisory_id,
                advisory_identifier="USN-1-1",
                source=source,
                package_name=name,
                status=status,
                computed_at=NOW,
            )
        )
    db.commit()


@pytest.mark.asyncio
async def test_unlicensed_is_402(db_session):
    with patch.object(mod.license_service, "has_feature", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await install_by_advisory(
                str(uuid.uuid4()),
                AdvisoryInstallRequest(advisory_id=str(uuid.uuid4())),
                db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_no_applicable_rows_is_404(db_session):
    with patch.object(mod.license_service, "has_feature", return_value=True):
        with pytest.raises(HTTPException) as exc:
            await install_by_advisory(
                str(uuid.uuid4()),
                AdvisoryInstallRequest(advisory_id=str(uuid.uuid4())),
                db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_dispatches_package_set(db_session):
    host_id = uuid.uuid4()
    advisory_id = uuid.uuid4()
    _seed(db_session, host_id, advisory_id, ["openssl", "libssl"])

    with patch.object(
        mod.license_service, "has_feature", return_value=True
    ), patch.object(
        mod, "install_packages_operation", new=AsyncMock(return_value={"ok": True})
    ) as install:
        result = await install_by_advisory(
            str(host_id),
            AdvisoryInstallRequest(advisory_id=str(advisory_id)),
            db=db_session,
            current_user="admin@example.com",
        )

    assert result == {"ok": True}
    # install_packages_operation(host_id, request, db, current_user)
    call = install.call_args
    request = call.args[1]
    assert sorted(request.package_names) == ["libssl", "openssl"]
    assert request.requested_by == "admin@example.com"


@pytest.mark.asyncio
async def test_openbsd_dispatches_syspatch_not_install(db_session):
    """OpenBSD errata remediate via a queued ``apply_updates`` (syspatch) command,
    NOT the package-install path."""
    host_id = uuid.uuid4()
    advisory_id = uuid.uuid4()
    _seed(
        db_session,
        host_id,
        advisory_id,
        ["001_xmss", "002_ssh"],
        source="openbsd",
    )

    captured = {}

    class _FakeQueue:
        def enqueue_message(self, **kwargs):
            captured.update(kwargs)

    with patch.object(
        mod.license_service, "has_feature", return_value=True
    ), patch.object(
        mod, "install_packages_operation", new=AsyncMock()
    ) as install, patch(
        "backend.websocket.queue_operations.QueueOperations",
        return_value=_FakeQueue(),
    ), patch(
        "backend.websocket.messages.create_command_message",
        side_effect=lambda ct, params: {"command_type": ct, "parameters": params},
    ):
        result = await install_by_advisory(
            str(host_id),
            AdvisoryInstallRequest(advisory_id=str(advisory_id)),
            db=db_session,
            current_user="admin@example.com",
        )

    install.assert_not_called()  # NOT the pkg-install path
    assert result["success"] is True
    assert result["packages_count"] == 2
    assert captured["message_type"] == "command"
    cmd = captured["message_data"]
    assert cmd["command_type"] == "apply_updates"
    pkgs = cmd["parameters"]["packages"]
    assert {p["package_name"] for p in pkgs} == {"001_xmss", "002_ssh"}
    assert all(p["package_manager"] == "syspatch" for p in pkgs)


@pytest.mark.asyncio
async def test_ignores_non_applicable_status(db_session):
    host_id = uuid.uuid4()
    advisory_id = uuid.uuid4()
    _seed(db_session, host_id, advisory_id, ["resolved-pkg"], status="resolved")

    with patch.object(mod.license_service, "has_feature", return_value=True):
        with pytest.raises(HTTPException) as exc:
            await install_by_advisory(
                str(host_id),
                AdvisoryInstallRequest(advisory_id=str(advisory_id)),
                db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 404
