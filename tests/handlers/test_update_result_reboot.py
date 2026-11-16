# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""An update result that needs a reboot is recorded, not rolled back
(production, nextcloud, 2026-11-02: "Unconsumed column names:
requires_reboot")."""

from datetime import datetime, timezone

import pytest

from backend.api.update_handlers import handle_update_apply_result
from backend.persistence import models


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _host_with_update(session):
    host = models.Host(
        fqdn="nextcloud",
        ipv4="192.168.4.30",
        active=True,
        status="up",
        approval_status="approved",
    )
    session.add(host)
    session.flush()
    session.add(
        models.PackageUpdate(
            host_id=host.id,
            package_name="libc6",
            current_version="2.39-0ubuntu8.5",
            available_version="2.39-0ubuntu8.6",
            package_manager="apt",
            update_type="security",
            status="updating",
            discovered_at=_now(),
            created_at=_now(),
            updated_at=_now(),
        )
    )
    session.add(
        models.UpdateExecutionLog(
            host_id=host.id,
            package_name="libc6",
            package_manager="apt",
            from_version="2.39-0ubuntu8.5",
            to_version="2.39-0ubuntu8.6",
            execution_status="pending",
            created_at=_now(),
            updated_at=_now(),
        )
    )
    session.commit()
    return host


@pytest.mark.parametrize(
    "result",
    [
        {"requires_reboot": True},  # macOS / the BSDs: the whole run
        {"package_extra": {"requires_reboot": True}},  # fwupd: one package
    ],
)
@pytest.mark.asyncio
async def test_a_result_that_needs_a_reboot_is_recorded(
    session, mock_connection, result
):
    host = _host_with_update(session)
    mock_connection.host_id = host.id
    package = {"package_name": "libc6", "package_manager": "apt"}
    package.update(result.get("package_extra", {}))
    message = {
        "hostname": "nextcloud",
        "updated_packages": [package],
        "failed_packages": [],
        "requires_reboot": result.get("requires_reboot", False),
    }

    reply = await handle_update_apply_result(session, mock_connection, message)

    assert reply["message_type"] == "success"
    session.expire_all()
    assert session.get(models.Host, host.id).reboot_required is True
    assert session.query(models.PackageUpdate).count() == 0
    log = session.query(models.UpdateExecutionLog).one()
    assert log.execution_status == "success"
