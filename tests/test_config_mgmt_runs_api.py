# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Reading config-profile run history (Phase 20.1).

The list is ordered newest-first and includes unchanged runs, because the
thing an operator is looking for is the QUIET STREAK -- a profile that has
stopped changing anything. A view that showed only the latest result, or that
filtered out no-ops as uninteresting, could not display convergence at all.

Timestamps are the other trap: rows are stored naive-UTC, and handing a naive
datetime to a browser makes it render as local time, so a run that happened an
hour ago can appear to be several hours in the future.
"""

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import config_mgmt_runs as api
from backend.security.roles import SecurityRoles

HOST_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
RUN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self.limit_used = None
        self.ordered = False

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a):
        self.ordered = True
        return self

    def limit(self, n):
        self.limit_used = n
        self._rows = self._rows[:n]
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, **by_name):
        self._by_name = by_name
        self.queries = []
        self.commits = 0

    def commit(self):
        self.commits += 1

    def __call__(self, *_a, **_k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def query(self, entity):
        q = _Query(self._by_name.get(entity.__name__, []))
        self.queries.append(q)
        return q


def run(**over):
    base = {
        "id": RUN_ID,
        "host_id": HOST_ID,
        "profile_id": None,
        "profile_name": "baseline",
        "executor": "ansible-core",
        "check_mode": False,
        "success": True,
        "changed": False,
        "exit_code": 0,
        "tasks_ok": 3,
        "tasks_changed": 0,
        "tasks_failed": 0,
        "tasks_skipped": 1,
        "tasks_unreachable": 0,
        "reason": None,
        "task_detail": None,
        "error_output": None,
        "completed_at": datetime(2026, 8, 26, 12, 0, 0),
    }
    base.update(over)
    return SimpleNamespace(**base)


def host():
    return SimpleNamespace(id=HOST_ID, fqdn="host.invalid")


class TestList:
    @pytest.mark.asyncio
    async def test_unchanged_runs_are_returned_not_filtered_out(self):
        # The quiet streak is the signal, not noise to be hidden.
        session = _Session(
            Host=[host()],
            ConfigProfileRun=[run(changed=False), run(changed=False)],
        )
        out = await api.list_config_profile_runs(str(HOST_ID), 25, session)
        assert len(out) == 2
        assert all(r.changed is False for r in out)

    @pytest.mark.asyncio
    async def test_results_are_ordered_and_limited(self):
        session = _Session(Host=[host()], ConfigProfileRun=[run() for _ in range(10)])
        out = await api.list_config_profile_runs(str(HOST_ID), 3, session)
        assert len(out) == 3
        runs_query = session.queries[-1]
        assert runs_query.ordered is True
        assert runs_query.limit_used == 3

    @pytest.mark.asyncio
    async def test_naive_timestamps_come_back_marked_utc(self):
        # Without this a browser renders the naive value as local time and the
        # run appears to have happened in the future.
        session = _Session(Host=[host()], ConfigProfileRun=[run()])
        out = await api.list_config_profile_runs(str(HOST_ID), 25, session)
        assert out[0].completed_at.tzinfo is timezone.utc

    @pytest.mark.asyncio
    async def test_a_failed_run_reports_its_reason(self):
        session = _Session(
            Host=[host()],
            ConfigProfileRun=[run(success=False, reason="executor_missing")],
        )
        out = await api.list_config_profile_runs(str(HOST_ID), 25, session)
        assert out[0].success is False and out[0].reason == "executor_missing"

    @pytest.mark.asyncio
    async def test_check_mode_runs_are_distinguishable(self):
        session = _Session(Host=[host()], ConfigProfileRun=[run(check_mode=True)])
        out = await api.list_config_profile_runs(str(HOST_ID), 25, session)
        assert out[0].check_mode is True

    @pytest.mark.asyncio
    async def test_a_host_with_no_runs_returns_an_empty_list(self):
        session = _Session(Host=[host()], ConfigProfileRun=[])
        assert await api.list_config_profile_runs(str(HOST_ID), 25, session) == []

    @pytest.mark.asyncio
    async def test_malformed_host_id_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await api.list_config_profile_runs("nope", 25, _Session())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_host_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await api.list_config_profile_runs(str(HOST_ID), 25, _Session(Host=[]))
        assert exc.value.status_code == 404


class TestDetail:
    @pytest.mark.asyncio
    async def test_detail_decodes_the_task_list(self):
        tasks = [{"task": "t", "status": "changed", "changed": True}]
        session = _Session(ConfigProfileRun=[run(task_detail=json.dumps(tasks))])
        out = await api.get_config_profile_run(str(RUN_ID), session)
        assert out.tasks == tasks

    @pytest.mark.asyncio
    async def test_truncated_detail_degrades_instead_of_500ing(self):
        # Detail is deliberately truncated on ingest, so the tail of a long
        # playbook's JSON is EXPECTED to be unparsable. A run that really ran
        # must still be viewable.
        session = _Session(ConfigProfileRun=[run(task_detail='[{"task": "t"')])
        out = await api.get_config_profile_run(str(RUN_ID), session)
        assert out.tasks == []
        assert out.success is True

    @pytest.mark.asyncio
    async def test_non_list_detail_is_ignored(self):
        session = _Session(ConfigProfileRun=[run(task_detail='{"not": "a list"}')])
        out = await api.get_config_profile_run(str(RUN_ID), session)
        assert out.tasks == []

    @pytest.mark.asyncio
    async def test_missing_run_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await api.get_config_profile_run(str(RUN_ID), _Session(ConfigProfileRun=[]))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_malformed_run_id_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await api.get_config_profile_run("nope", _Session())
        assert exc.value.status_code == 400


class _Env:
    """Patches the queue, audit trail and audit engine for the apply route."""

    def __init__(self):
        self.enqueued = []
        self.audits = []

    def _enqueue(self, **kwargs):
        self.enqueued.append(kwargs)
        return "msg-1"

    def __enter__(self):
        self._patches = [
            patch(
                "backend.api.config_mgmt_runs.queue_ops.enqueue_message",
                side_effect=self._enqueue,
            ),
            patch("backend.api.config_mgmt_runs.persistence_db.get_engine"),
            patch("backend.api.config_mgmt_runs.sessionmaker", return_value=_Session()),
            patch(
                "backend.api.config_mgmt_runs.AuditService.log",
                side_effect=lambda **kw: self.audits.append(kw),
            ),
        ]
        for patcher in self._patches:
            patcher.start()
        return self

    def __exit__(self, *_exc):
        for patcher in self._patches:
            patcher.stop()
        return False


def _user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        id="u1", userid="admin@invalid", has_role=lambda role: role in granted
    )


def _host(platform="Linux", release="Ubuntu 24.04", active=True):
    return SimpleNamespace(
        id=HOST_ID,
        fqdn="host.invalid",
        platform=platform,
        platform_release=release,
        platform_version="24.04",
        active=active,
    )


def _req(**over):
    return api.ConfigProfileApplyRequest(**over)


class TestApply:
    """Applying an ad-hoc profile.

    A playbook can run anything the agent can, so this is remote code
    execution by another name. The role gate and the active-host check are the
    two things standing between a UI button and arbitrary root on a fleet.
    """

    @pytest.mark.asyncio
    async def test_it_requires_the_run_script_role(self):
        # Deliberately the SAME role as running a script, because the blast
        # radius is identical. A softer config-specific role would be a
        # privilege-escalation path dressed up as a feature.
        session = _Session(Host=[_host()])
        with _Env():
            with pytest.raises(HTTPException) as exc:
                await api.apply_config_profile(
                    str(HOST_ID), _req(playbook="- hosts: all"), session, _user()
                )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_an_inactive_host_is_refused_rather_than_queued(self):
        # Queuing for an inactive host buries the work in a queue that may
        # never drain while the operator is told it was accepted.
        session = _Session(Host=[_host(active=False)])
        with _Env() as env:
            with pytest.raises(HTTPException) as exc:
                await api.apply_config_profile(
                    str(HOST_ID),
                    _req(playbook="- hosts: all"),
                    session,
                    _user(SecurityRoles.RUN_SCRIPT),
                )
        assert exc.value.status_code == 400
        assert env.enqueued == []

    @pytest.mark.asyncio
    async def test_a_posix_host_gets_its_playbook_queued(self):
        session = _Session(Host=[_host()])
        with _Env() as env:
            out = await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook="- hosts: all", profile_name="baseline"),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        assert out.queued is True
        params = env.enqueued[0]["message_data"]["data"]["parameters"]
        assert params["profile"]["playbook"] == "- hosts: all"
        assert params["profile_name"] == "baseline"

    @pytest.mark.asyncio
    async def test_the_queue_row_carries_the_envelope_id_so_results_correlate(self):
        # REGRESSION (2026-08-28). enqueue_message mints its OWN uuid when you
        # don't pass one, but the agent echoes the ENVELOPE's message_id back as
        # `command_id`. When those two differed, every config-profile result
        # arrived un-correlatable and was dropped on the floor -- silently, with
        # the run never recorded. Found by a real four-engine round trip, not by
        # this suite, which is why it is now here.
        session = _Session(Host=[_host()])
        with _Env() as env:
            await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook="- hosts: all"),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        row = env.enqueued[0]
        assert row["message_id"] == row["message_data"]["message_id"]

    @pytest.mark.asyncio
    async def test_a_windows_host_gets_its_resources_queued(self):
        session = _Session(Host=[_host(platform="Windows", release="")])
        with _Env() as env:
            await api.apply_config_profile(
                str(HOST_ID),
                _req(resources=[{"name": "n", "type": "T"}]),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        params = env.enqueued[0]["message_data"]["data"]["parameters"]
        assert params["profile"]["resources"] == [{"name": "n", "type": "T"}]

    @pytest.mark.asyncio
    async def test_a_playbook_sent_to_windows_is_refused_up_front(self):
        # Letting this through fails at the far end, where the reason is far
        # less obvious than a 400 saying which field the host wants.
        session = _Session(Host=[_host(platform="Windows", release="")])
        with _Env() as env:
            with pytest.raises(HTTPException) as exc:
                await api.apply_config_profile(
                    str(HOST_ID),
                    _req(playbook="- hosts: all"),
                    session,
                    _user(SecurityRoles.RUN_SCRIPT),
                )
        assert exc.value.status_code == 400
        assert env.enqueued == []

    @pytest.mark.asyncio
    async def test_dsc_resources_sent_to_linux_are_refused_up_front(self):
        session = _Session(Host=[_host()])
        with _Env() as env:
            with pytest.raises(HTTPException) as exc:
                await api.apply_config_profile(
                    str(HOST_ID),
                    _req(resources=[{"name": "n"}]),
                    session,
                    _user(SecurityRoles.RUN_SCRIPT),
                )
        assert exc.value.status_code == 400
        assert env.enqueued == []

    @pytest.mark.asyncio
    async def test_an_empty_playbook_is_refused(self):
        session = _Session(Host=[_host()])
        with _Env():
            with pytest.raises(HTTPException) as exc:
                await api.apply_config_profile(
                    str(HOST_ID),
                    _req(playbook="   "),
                    session,
                    _user(SecurityRoles.RUN_SCRIPT),
                )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_check_mode_is_passed_through_and_reported(self):
        session = _Session(Host=[_host()])
        with _Env() as env:
            out = await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook="- hosts: all", check_mode=True),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        assert out.check_mode is True
        params = env.enqueued[0]["message_data"]["data"]["parameters"]
        assert params["check_mode"] is True

    @pytest.mark.asyncio
    async def test_the_profile_body_is_never_written_to_the_audit_log(self):
        # Profiles can carry secrets, and the audit log is readable by more
        # people than the profile is.
        secret = "- hosts: all\n  vars:\n    db_password: hunter2\n"
        session = _Session(Host=[_host()])
        with _Env() as env:
            await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook=secret),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        recorded = json.dumps(env.audits[0], default=str)
        assert "hunter2" not in recorded
        assert env.audits[0]["details"]["executor"] == "ansible-core"

    @pytest.mark.asyncio
    async def test_unknown_host_is_a_404(self):
        with _Env():
            with pytest.raises(HTTPException) as exc:
                await api.apply_config_profile(
                    str(HOST_ID),
                    _req(playbook="- hosts: all"),
                    _Session(Host=[]),
                    _user(SecurityRoles.RUN_SCRIPT),
                )
        assert exc.value.status_code == 404


class TestApplyLicensing:
    """Puppet/Salt/Chef are gated; ansible-core and DSC are not.

    The refusal happens BEFORE the message is queued. Gating after dispatch
    would leave a half-applied profile on the host and report success.
    """

    @pytest.mark.asyncio
    async def test_ansible_needs_no_license(self):
        session = _Session(Host=[_host()])
        with _Env() as env:
            out = await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook="- hosts: all"),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        assert out.queued is True
        assert len(env.enqueued) == 1

    @pytest.mark.asyncio
    async def test_an_unlicensed_puppet_apply_is_refused_before_queueing(self):
        session = _Session(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_runs.require_module",
            side_effect=HTTPException(status_code=403, detail="pro_plus_required"),
        ):
            with pytest.raises(HTTPException) as exc:
                await api.apply_config_profile(
                    str(HOST_ID),
                    _req(playbook="class x {}", engine="puppet"),
                    session,
                    _user(SecurityRoles.RUN_SCRIPT),
                )
        assert exc.value.status_code == 403
        assert env.enqueued == [], "nothing may be dispatched when unlicensed"

    @pytest.mark.asyncio
    async def test_a_licensed_puppet_apply_goes_through(self):
        # The module must be present as well as licensed: a licensed engine is
        # dispatched as a spec the Pro+ module builds, so mocking only the
        # licence gate leaves nothing to send (and correctly 503s).
        session = _Session(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_runs.require_module", return_value=None
        ), patch(
            "backend.api.config_mgmt_runs.spec_shim.build_licensed_spec",
            return_value={"engine": "puppet", "argv": ["puppet", "apply"]},
        ):
            out = await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook="class x {}", engine="puppet"),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        assert out.queued is True
        assert env.audits[0]["details"]["executor"] == "puppet"

    @pytest.mark.asyncio
    async def test_an_unknown_engine_is_a_400_not_a_403(self):
        # Rejected as nonsense, not upsold as a licensing problem.
        session = _Session(Host=[_host()])
        with _Env() as env:
            with pytest.raises(HTTPException) as exc:
                await api.apply_config_profile(
                    str(HOST_ID),
                    _req(playbook="x", engine="terraform"),
                    session,
                    _user(SecurityRoles.RUN_SCRIPT),
                )
        assert exc.value.status_code == 400
        assert env.enqueued == []

    @pytest.mark.asyncio
    async def test_the_engine_is_recorded_so_history_shows_which_ran(self):
        session = _Session(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_runs.require_module", return_value=None
        ), patch(
            "backend.api.config_mgmt_runs.spec_shim.build_licensed_spec",
            return_value={"engine": "salt", "argv": ["salt-call"]},
        ):
            await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook="x", engine="salt"),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        assert env.audits[0]["details"]["executor"] == "salt"


class TestApplySpecDispatch:
    """A licensed engine is dispatched as a SPEC built by the Pro+ module.

    The agent deliberately cannot drive Puppet/Salt/Chef itself, so without a
    spec there is nothing to send. The two failure modes must stay distinct:
    403 means the customer is unlicensed, 503 means the module is licensed but
    absent -- an administrator problem, not a sales one.
    """

    @pytest.mark.asyncio
    async def test_a_licensed_engine_dispatches_the_engines_spec(self):
        spec = {"engine": "puppet", "argv": ["puppet", "apply", "{profile}"]}
        session = _Session(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_runs.require_module", return_value=None
        ), patch(
            "backend.api.config_mgmt_runs.spec_shim.build_licensed_spec",
            return_value=spec,
        ):
            await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook="class x {}", engine="puppet"),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        params = env.enqueued[0]["message_data"]["data"]["parameters"]
        assert params["spec"] is spec

    @pytest.mark.asyncio
    async def test_a_licensed_but_unloaded_module_is_a_503_not_a_403(self):
        # 403 would tell a paying customer to buy something they already have.
        session = _Session(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_runs.require_module", return_value=None
        ), patch(
            "backend.api.config_mgmt_runs.spec_shim.build_licensed_spec",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc:
                await api.apply_config_profile(
                    str(HOST_ID),
                    _req(playbook="class x {}", engine="puppet"),
                    session,
                    _user(SecurityRoles.RUN_SCRIPT),
                )
        assert exc.value.status_code == 503
        assert env.enqueued == [], "nothing may be queued without a spec"

    @pytest.mark.asyncio
    async def test_a_free_engine_never_consults_the_pro_plus_module(self):
        # ansible-core is driven by the agent's own path; reaching for the
        # engine would make a free feature depend on a licensed module.
        session = _Session(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_runs.spec_shim.build_licensed_spec"
        ) as builder:
            await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook="- hosts: all"),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        builder.assert_not_called()
        assert "spec" not in env.enqueued[0]["message_data"]["data"]["parameters"]

    @pytest.mark.asyncio
    async def test_check_mode_and_timeout_reach_the_spec_builder(self):
        session = _Session(Host=[_host()])
        with _Env(), patch(
            "backend.api.config_mgmt_runs.require_module", return_value=None
        ), patch(
            "backend.api.config_mgmt_runs.spec_shim.build_licensed_spec",
            return_value={"engine": "salt", "argv": ["salt-call"]},
        ) as builder:
            await api.apply_config_profile(
                str(HOST_ID),
                _req(playbook="state:", engine="salt", check_mode=True, timeout=99),
                session,
                _user(SecurityRoles.RUN_SCRIPT),
            )
        builder.assert_called_once_with("salt", "state:", check_mode=True, timeout=99)
