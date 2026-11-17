# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""An update keeps the time it was first seen across reports (ROADMAP 26.3):
the waiting period before applying it counts from there, and every report
used to reset it to "now"."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.api.handlers.software_package_handlers import (
    handle_package_updates_update,
)
from backend.persistence import models


def _report(version):
    return {
        "available_updates": [
            {"package_name": "openssl", "package_manager": "apt",
             "current_version": "3.0.1", "available_version": version,
             "is_security_update": True},  # fmt: skip
        ]
    }


def _seen(session, host):
    session.expire_all()
    return session.query(models.PackageUpdate).filter_by(host_id=host.id).one()


@pytest.mark.asyncio
async def test_the_first_sighting_survives_later_reports(session):
    host = models.Host(fqdn="web1", ipv4="10.0.0.1", active=True, status="up",
                       approval_status="approved")  # fmt: skip
    session.add(host)
    session.commit()
    conn = SimpleNamespace(host_id=host.id, is_mock_connection=True)

    await handle_package_updates_update(session, conn, _report("3.0.2"))
    first = _seen(session, host)
    week_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    first.discovered_at = week_ago
    session.commit()

    await handle_package_updates_update(session, conn, _report("3.0.2"))
    assert _seen(session, host).discovered_at == week_ago

    await handle_package_updates_update(session, conn, _report("3.0.3"))
    assert _seen(session, host).discovered_at > week_ago  # a new version, a new clock
