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
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import config_mgmt_runs as api

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

    def query(self, entity):
        q = _Query(self._by_name.get(entity.__name__, []))
        self.queries.append(q)
        return q


def run(**over):
    base = dict(
        id=RUN_ID,
        host_id=HOST_ID,
        profile_id=None,
        profile_name="baseline",
        executor="ansible-core",
        check_mode=False,
        success=True,
        changed=False,
        exit_code=0,
        tasks_ok=3,
        tasks_changed=0,
        tasks_failed=0,
        tasks_skipped=1,
        tasks_unreachable=0,
        reason=None,
        task_detail=None,
        error_output=None,
        completed_at=datetime(2026, 8, 26, 12, 0, 0),
    )
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
