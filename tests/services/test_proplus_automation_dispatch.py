# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which hosts of a Pro+ execution require approval for scripts."""

from unittest.mock import patch

from backend.persistence import models
from backend.services import proplus_automation_dispatch as dispatch


def _host(db_session, fqdn, required):
    host = models.Host(
        fqdn=fqdn,
        active=True,
        status="up",
        approval_status="approved",
        script_approval_required=required,
    )
    db_session.add(host)
    db_session.commit()
    return str(host.id)


def test_approval_hosts_reads_each_host_from_its_database(engine, db_session):
    held = _host(db_session, "held.example", True)
    free = _host(db_session, "free.example", False)
    with patch(
        "backend.persistence.partitions.tenant_engine_for_host", return_value=None
    ), patch("backend.persistence.partitions.get_request_engine", return_value=engine):
        assert dispatch._approval_hosts(
            [held, free, "00000000-0000-0000-0000-000000000000"]
        ) == [held]


def test_a_new_host_does_not_require_approval(db_session):
    host = models.Host(fqdn="new.example", active=True, status="up")
    db_session.add(host)
    db_session.commit()
    db_session.refresh(host)
    assert host.script_approval_required is False
