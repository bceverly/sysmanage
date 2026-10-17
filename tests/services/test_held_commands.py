# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Commands a maintenance window is holding: counted, listed, described
without secrets, cancelable -- and NOT expired by age while held.

Production, 2026-10-16: an Ubuntu Pro attach queued at 19:38 behind a 02:00
allow-window looked broken (the UI said "requested", then nothing), and the
hourly age-expiry would have killed it long before the window opened."""

import json
import uuid
from datetime import datetime, timedelta, timezone

from backend.persistence import models
from backend.services import held_commands as held
from backend.services import maintenance_window_service as mw
from backend.websocket.queue_enums import QueueDirection, QueueStatus


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _host(db, fqdn="vm.example.invalid"):
    host = models.Host(
        id=uuid.uuid4(), fqdn=fqdn, active=True, approval_status="approved"
    )
    db.add(host)
    db.commit()
    return host


def _row(
    db,
    host_id,
    command_type="ubuntu_pro_attach",
    params=None,
    *,
    held_by_window=True,
    status=QueueStatus.PENDING,
    direction=QueueDirection.OUTBOUND,
    age_minutes=5,
):
    row = models.MessageQueue(
        id=uuid.uuid4(),
        host_id=host_id,
        message_id=str(uuid.uuid4()),
        direction=direction,
        message_type="command",
        message_data=json.dumps(
            {"data": {"command_type": command_type, "parameters": params or {}}}
        ),
        status=status,
        priority="normal",
        retry_count=0,
        max_retries=3,
        created_at=_now() - timedelta(minutes=age_minutes),
        error_message=mw.DEFERRED_MARKER if held_by_window else None,
    )
    db.add(row)
    db.commit()
    return row


def test_counts_only_this_hosts_held_rows(db_session):
    host, other = _host(db_session), _host(db_session, "other.example.invalid")
    _row(db_session, host.id)
    _row(db_session, host.id, "apply_updates")
    _row(db_session, host.id, held_by_window=False)  # pending, not held
    _row(db_session, host.id, status=QueueStatus.COMPLETED)  # finished
    _row(db_session, host.id, direction=QueueDirection.INBOUND)
    _row(db_session, other.id)
    assert mw.held_commands(db_session, host.id)["count"] == 2
    assert mw.held_counts(db_session, [host.id, other.id]) == {
        str(host.id): 2,
        str(other.id): 1,
    }


def test_nothing_held_is_zero(db_session):
    host = _host(db_session)
    assert mw.held_commands(db_session, host.id) == {"count": 0, "oldest_at": None}
    assert mw.held_counts(db_session, [host.id]) == {}
    assert mw.held_counts(db_session, []) == {}


def test_secrets_and_file_contents_are_never_described():
    attach = held.describe(
        json.dumps(
            {
                "data": {
                    "command_type": "ubuntu_pro_attach",
                    "parameters": {
                        "token": "C1-SECRET",
                        "api_key": "k",
                        "password": "p",
                    },
                }
            }
        )
    )
    assert attach == {"command_type": "ubuntu_pro_attach", "details": {}}
    plan = held.describe(
        json.dumps(
            {
                "data": {
                    "command_type": "apply_deployment_plan",
                    "parameters": {
                        "plan": {
                            "av_product": "clamav",
                            "packages": ["clamav", "clamav-daemon"],
                            "files": [
                                {
                                    "path": "/etc/clamav/clamd.conf",
                                    "content": "SECRET-FILE",
                                }
                            ],
                        }
                    },
                }
            }
        )
    )
    assert "SECRET-FILE" not in json.dumps(plan)
    assert plan["details"]["av_product"] == "clamav"
    assert plan["details"]["packages"] == {
        "names": ["clamav", "clamav-daemon"],
        "count": 2,
    }


def test_package_lists_are_summarized():
    pkgs = [{"package_name": f"p{i}"} for i in range(8)]
    out = held.describe(
        json.dumps(
            {
                "data": {
                    "command_type": "apply_updates",
                    "parameters": {"packages": pkgs},
                }
            }
        )
    )
    assert out["details"]["packages"] == {
        "names": ["p0", "p1", "p2", "p3", "p4"],
        "count": 8,
    }


def test_the_list_is_newest_first_and_names_the_host(db_session):
    host = _host(db_session)
    _row(db_session, host.id, "collect_available_packages", age_minutes=30)
    newest = _row(db_session, host.id, "apply_updates", age_minutes=1)
    _row(db_session, host.id, held_by_window=False)
    out = held.list_held(db_session)
    assert out["total"] == 2
    assert out["items"][0]["id"] == str(newest.id)
    assert out["items"][0]["fqdn"] == host.fqdn
    assert out["items"][0]["expires_at"] is not None


def test_cancel_only_a_held_row(db_session):
    host = _host(db_session)
    row = _row(db_session, host.id)
    released = _row(db_session, host.id, held_by_window=False)
    assert held.cancel(db_session, released.id, "bryan") is None
    canceled = held.cancel(db_session, row.id, "bryan")
    db_session.commit()
    assert canceled.status == QueueStatus.FAILED
    assert canceled.error_message == "canceled by bryan"
    assert held.cancel(db_session, row.id, "bryan") is None  # not held anymore
    assert mw.held_commands(db_session, host.id)["count"] == 0
