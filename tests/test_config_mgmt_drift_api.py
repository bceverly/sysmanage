# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The drift dashboard and remediation endpoints (Phase 20.2).

Remediation is the sharp edge: it re-applies a profile for real. The rules it
must not break are that a retired profile is not silently re-imposed, and that
queuing is never reported as fixed -- findings resolve when the next CHECK run
observes the host is back in line, not when we press the button.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import config_mgmt_drift as api
from backend.security.roles import SecurityRoles

NOW = datetime(2026, 8, 28, 12, 0, 0)
HOST = uuid.UUID("22222222-2222-4222-8222-222222222222")
HOST2 = uuid.UUID("33333333-3333-4333-8333-333333333333")
PROFILE = uuid.UUID("44444444-4444-4444-8444-444444444444")


def finding(**over):
    base = {
        "id": uuid.uuid4(),
        "host_id": HOST,
        "profile_id": PROFILE,
        "profile_name": "baseline",
        "task_name": "ensure sshd config",
        "detail": "would set 0600",
        "first_seen_at": NOW - timedelta(days=3),
        "last_seen_at": NOW,
        "resolved_at": None,
        "last_run_id": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def host(host_id=HOST, active=True):
    return SimpleNamespace(
        id=host_id, fqdn=f"h{host_id.int % 10}.invalid", active=active
    )


def profile(**over):
    base = {
        "id": PROFILE,
        "name": "baseline",
        "engine": "ansible-core",
        "content": "- hosts: all\n",
        "is_active": True,
    }
    base.update(over)
    return SimpleNamespace(**base)


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, **by_name):
        self._by_name = by_name
        self.commits = 0

    def query(self, entity):
        return _Query(self._by_name.get(entity.__name__, []))

    def commit(self):
        self.commits += 1


def user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        userid="op@invalid", id=uuid.uuid4(), has_role=lambda r: r in granted
    )


class TestFleetView:
    @pytest.mark.asyncio
    async def test_hosts_are_grouped_with_a_finding_count(self):
        session = _Session(
            ConfigDriftFinding=[finding(), finding(task_name="other")],
            Host=[host()],
        )
        out = await api.list_drifting_hosts(session)
        assert len(out) == 1
        assert out[0].finding_count == 2

    @pytest.mark.asyncio
    async def test_drifting_since_is_the_OLDEST_finding(self):
        # The newest would understate how long the host has been diverging,
        # which is the number an operator triages on.
        oldest = NOW - timedelta(days=10)
        session = _Session(
            ConfigDriftFinding=[
                finding(first_seen_at=NOW - timedelta(days=1)),
                finding(task_name="b", first_seen_at=oldest),
            ],
            Host=[host()],
        )
        out = await api.list_drifting_hosts(session)
        assert out[0].drifting_since == oldest.replace(tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_longest_drifting_host_comes_first(self):
        # Alphabetical order would bury a three-week divergence under a
        # one-hour one.
        session = _Session(
            ConfigDriftFinding=[
                finding(host_id=HOST, first_seen_at=NOW - timedelta(hours=1)),
                finding(host_id=HOST2, first_seen_at=NOW - timedelta(days=20)),
            ],
            Host=[host(HOST), host(HOST2)],
        )
        out = await api.list_drifting_hosts(session)
        assert out[0].host_id == str(HOST2)

    @pytest.mark.asyncio
    async def test_profile_names_are_deduplicated(self):
        session = _Session(
            ConfigDriftFinding=[finding(), finding(task_name="b")],
            Host=[host()],
        )
        out = await api.list_drifting_hosts(session)
        assert out[0].profile_names == ["baseline"]

    @pytest.mark.asyncio
    async def test_a_clean_fleet_is_an_empty_list_not_an_error(self):
        out = await api.list_drifting_hosts(_Session(ConfigDriftFinding=[]))
        assert out == []

    @pytest.mark.asyncio
    async def test_timestamps_come_back_marked_utc(self):
        session = _Session(ConfigDriftFinding=[finding()], Host=[host()])
        out = await api.list_drifting_hosts(session)
        assert out[0].drifting_since.tzinfo is timezone.utc


class TestHostView:
    @pytest.mark.asyncio
    async def test_a_missing_host_is_404(self):
        with pytest.raises(HTTPException) as err:
            await api.list_host_drift(str(HOST), _Session(Host=[]))
        assert err.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_malformed_id_is_400_not_500(self):
        with pytest.raises(HTTPException) as err:
            await api.list_host_drift("not-a-uuid", _Session())
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_findings_carry_the_detail_an_operator_acts_on(self):
        session = _Session(Host=[host()], ConfigDriftFinding=[finding()])
        out = await api.list_host_drift(str(HOST), session)
        assert out[0].task_name == "ensure sshd config"
        assert out[0].detail == "would set 0600"


class TestRemediation:
    @pytest.mark.asyncio
    async def test_requires_the_run_script_role(self):
        # It runs the profile for real; a softer permission for the same
        # capability would be an escalation path.
        with pytest.raises(HTTPException) as err:
            await api.remediate_drift(
                api.RemediateRequest(host_id=str(HOST), profile_id=str(PROFILE)),
                _Session(),
                user(),
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_an_inactive_host_is_refused(self):
        session = _Session(Host=[host(active=False)])
        with pytest.raises(HTTPException) as err:
            await api.remediate_drift(
                api.RemediateRequest(host_id=str(HOST), profile_id=str(PROFILE)),
                session,
                user(SecurityRoles.RUN_SCRIPT),
            )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_retired_profile_is_not_silently_re_imposed(self):
        # Somebody deactivated it deliberately; remediating to it would undo a
        # decision rather than enforce one.
        session = _Session(Host=[host()], ConfigProfile=[profile(is_active=False)])
        with pytest.raises(HTTPException) as err:
            await api.remediate_drift(
                api.RemediateRequest(host_id=str(HOST), profile_id=str(PROFILE)),
                session,
                user(SecurityRoles.RUN_SCRIPT),
            )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_missing_profile_is_404(self):
        session = _Session(Host=[host()], ConfigProfile=[])
        with pytest.raises(HTTPException) as err:
            await api.remediate_drift(
                api.RemediateRequest(host_id=str(HOST), profile_id=str(PROFILE)),
                session,
                user(SecurityRoles.RUN_SCRIPT),
            )
        assert err.value.status_code == 404

    @pytest.mark.asyncio
    async def test_remediation_runs_LIVE_not_in_check_mode(self):
        # A check-mode "remediation" would report the drift again and fix
        # nothing, which is the one outcome the button must never produce.
        session = _Session(Host=[host()], ConfigProfile=[profile()])
        queued = {}

        class FakeQueue:
            def enqueue_message(self, **kwargs):
                queued.update(kwargs)

        with patch.object(api, "QueueOperations", FakeQueue):
            out = await api.remediate_drift(
                api.RemediateRequest(host_id=str(HOST), profile_id=str(PROFILE)),
                session,
                user(SecurityRoles.RUN_SCRIPT),
            )

        params = queued["message_data"]["data"]["parameters"]
        assert params["check_mode"] is False
        assert params["profile_id"] == str(PROFILE)
        assert out.queued is True

    @pytest.mark.asyncio
    async def test_the_queue_row_carries_the_envelope_id_so_results_correlate(self):
        # REGRESSION (2026-08-28). The agent echoes the ENVELOPE's message_id
        # back as `command_id`; enqueue_message mints a DIFFERENT uuid unless
        # you pass one. While those diverged, a remediation ran on the host and
        # its result could never be matched back to the command -- so the
        # finding stayed open and the dashboard reported drift that was fixed.
        session = _Session(Host=[host()], ConfigProfile=[profile()])
        queued = {}

        class FakeQueue:
            def enqueue_message(self, **kwargs):
                queued.update(kwargs)

        with patch.object(api, "QueueOperations", FakeQueue):
            await api.remediate_drift(
                api.RemediateRequest(host_id=str(HOST), profile_id=str(PROFILE)),
                session,
                user(SecurityRoles.RUN_SCRIPT),
            )

        assert queued["message_id"] == queued["message_data"]["message_id"]

    @pytest.mark.asyncio
    async def test_queuing_is_not_reported_as_fixed(self):
        # Findings resolve when the next CHECK run says so. Claiming success
        # here would be a dashboard that lies about the fleet.
        session = _Session(Host=[host()], ConfigProfile=[profile()])

        class FakeQueue:
            def enqueue_message(self, **_kwargs):
                return None

        with patch.object(api, "QueueOperations", FakeQueue):
            out = await api.remediate_drift(
                api.RemediateRequest(host_id=str(HOST), profile_id=str(PROFILE)),
                session,
                user(SecurityRoles.RUN_SCRIPT),
            )
        assert "queued" in out.message.lower()
        assert "resolved" not in out.message.lower()

    @pytest.mark.asyncio
    async def test_an_undispatchable_profile_surfaces_its_status(self):
        session = _Session(
            Host=[host()], ConfigProfile=[profile(engine="dsc", content="{not json")]
        )
        with pytest.raises(HTTPException) as err:
            await api.remediate_drift(
                api.RemediateRequest(host_id=str(HOST), profile_id=str(PROFILE)),
                session,
                user(SecurityRoles.RUN_SCRIPT),
            )
        assert err.value.status_code == 400
        assert "baseline" in err.value.detail
