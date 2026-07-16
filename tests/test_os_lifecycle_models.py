# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Smoke tests for the Phase 14.3 OS lifecycle / release-upgrade schema."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from backend.persistence.models import (
    Host,
    ReleaseUpgradeJob,
    SharedOsLifecycle,
)

NOW = datetime(2026, 7, 13, 12, 0)


class TestSharedOsLifecycle:
    def test_round_trip_and_eol_join(self, db_session):
        db_session.add(
            SharedOsLifecycle(
                os_name="ubuntu",
                os_version="22.04",
                codename="jammy",
                release_date=datetime(2022, 4, 21),
                eol_date=datetime(2027, 4, 1),
                lts=True,
                upgrade_to="24.04",
                source="endoflife.date",
            )
        )
        db_session.commit()

        # The "approaching EOL" join a host query would run.
        row = (
            db_session.query(SharedOsLifecycle)
            .filter(
                SharedOsLifecycle.os_name == "ubuntu",
                SharedOsLifecycle.os_version == "22.04",
            )
            .first()
        )
        assert row.upgrade_to == "24.04"
        assert row.to_dict()["lts"] is True
        assert row.to_dict()["eol_date"].startswith("2027-04-01")

    def test_unique_os_version(self, db_session):
        for _ in range(2):
            db_session.add(SharedOsLifecycle(os_name="debian", os_version="12"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestReleaseUpgradeJob:
    def test_job_lifecycle(self, db_session):
        host = Host(fqdn="web01.example", active=True, approval_status="approved")
        db_session.add(host)
        db_session.flush()

        job = ReleaseUpgradeJob(
            host_id=host.id,
            from_os_name="ubuntu",
            from_version="22.04",
            to_version="24.04",
            method="do-release-upgrade",
            status="scheduled",
            scheduled_at=NOW,
            precheck_results={"disk_ok": True, "reboot_required": True},
            created_at=NOW,
            updated_at=NOW,
        )
        db_session.add(job)
        db_session.commit()

        loaded = db_session.query(ReleaseUpgradeJob).first()
        d = loaded.to_dict()
        assert d["to_version"] == "24.04"
        assert d["method"] == "do-release-upgrade"
        assert d["status"] == "scheduled"
        assert d["precheck_results"]["reboot_required"] is True
        assert str(loaded.host_id) == str(host.id)

    def test_status_default_is_pending(self, db_session):
        host = Host(fqdn="db01.example", active=True, approval_status="approved")
        db_session.add(host)
        db_session.flush()
        job = ReleaseUpgradeJob(host_id=host.id, created_at=NOW, updated_at=NOW)
        db_session.add(job)
        db_session.commit()
        assert db_session.query(ReleaseUpgradeJob).first().status == "pending"
