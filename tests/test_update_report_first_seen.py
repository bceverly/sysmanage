# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The HTTP update report keeps when each update was first seen, like the
WebSocket report does: a policy's waiting period counts from it, so a
re-report must not restart the clock -- and a newer version starts its own."""

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

from backend.api.updates.models import PackageUpdateInfo, UpdatesReport
from backend.api.updates.report_routes import report_updates
from backend.persistence import models

FIRST = datetime(2026, 11, 26, 7, 57)


def _report(*updates):
    return UpdatesReport(
        available_updates=[PackageUpdateInfo(package_name=n, available_version=v,
                                             package_manager="apt") for n, v in updates],
        total_updates=len(updates), security_updates=0, system_updates=0,
        application_updates=len(updates), platform="Linux",
    )  # fmt: skip


def test_a_re_report_keeps_first_seen_and_a_new_version_starts_over(db_session):
    host = models.Host(fqdn="web.example.com", active=True, approval_status="approved")
    db_session.add(host)
    db_session.flush()
    for name in ("libexpat1", "libkrb5-3"):
        db_session.add(models.PackageUpdate(
            host_id=host.id, package_name=name, current_version="1", available_version="2",
            package_manager="apt", update_type="security", status="available",
            discovered_at=FIRST, created_at=FIRST, updated_at=FIRST,
        ))  # fmt: skip
    db_session.commit()

    @contextmanager
    def session():
        yield db_session

    with patch("backend.api.updates.report_routes.request_sessionmaker",
               return_value=session):  # fmt: skip
        report_updates(str(host.id), _report(("libexpat1", "2"), ("libkrb5-3", "3")))

    seen = {
        u.package_name: u.discovered_at for u in db_session.query(models.PackageUpdate)
    }
    assert seen["libexpat1"] == FIRST
    assert seen["libkrb5-3"] > FIRST
