# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Ingesting config-profile results (Phase 20.1).

Two properties carry the weight.

**A no-op run must still be recorded.** Idempotency reporting is a claim about
history -- "the last three runs changed nothing" -- and dropping unchanged runs
as uninteresting is exactly what makes that unanswerable.

**A malformed result must not stall the queue.** These arrive on the shared
queue processor, so an exception here would block every other host's messages
behind one bad payload. Every failure path returns a value instead.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.api.handlers import config_mgmt_handlers as handler
from backend.api.message_handlers import command_type_of

HOST_ID = "11111111-1111-4111-8111-111111111111"


class FakeSession:
    def __init__(self, host=None, explode=False):
        self._host = host
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self._explode = explode

    def query(self, *_a):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._host

    def add(self, obj):
        if self._explode:
            raise RuntimeError("db is down")
        self.added.append(obj)

    def flush(self):
        """The real Session has this; the handler needs it.

        Column defaults (including the run's own id) are applied by SQLAlchemy
        at FLUSH time, not on construction -- so drift findings, which
        reference the run id, cannot be written before one.
        """
        if self._explode:
            raise RuntimeError("db is down")
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def all(self):
        # Drift reconciliation queries existing findings; there are none in
        # these tests, which exercise the run-recording path.
        return []

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def conn(host_id=HOST_ID, hostname="host.invalid"):
    return SimpleNamespace(host_id=host_id, hostname=hostname)


def message(result, **extra):
    payload = {"command_type": "apply_config_profile", "result": result}
    payload.update(extra)
    return payload


GOOD = {
    "success": True,
    "changed": True,
    "executor": "ansible-core",
    "check_mode": False,
    "exit_code": 0,
    "recap": {"ok": 2, "changed": 1, "failed": 0, "skipped": 1, "unreachable": 0},
    "tasks": [{"host": "localhost", "task": "t", "status": "changed", "changed": True}],
}


class TestRouting:
    def test_routes_on_command_type_from_either_placement(self):
        # A refused run is just {"success": false, "reason": ...} -- it shares
        # no field with a successful one, so shape sniffing would drop every
        # failure silently.
        assert command_type_of({"command_type": "apply_config_profile"})
        assert command_type_of({"data": {"command_type": "apply_config_profile"}})
        assert command_type_of({}) is None


class TestRecording:
    @pytest.mark.asyncio
    async def test_a_successful_run_is_recorded_with_its_recap(self):
        db = FakeSession()
        out = await handler.handle_config_profile_result(db, conn(), message(GOOD))
        assert out["success"] is True
        row = db.added[0]
        assert row.host_id == HOST_ID
        assert row.success is True and row.changed is True
        assert (row.tasks_ok, row.tasks_changed, row.tasks_skipped) == (2, 1, 1)
        assert row.executor == "ansible-core"
        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_success_is_read_from_the_envelope_where_agents_put_it(self):
        # THE REAL WIRE SHAPE, captured from live ansible-core, puppet, chef
        # and salt results on 2026-08-28: `success` and `exit_code` sit on the
        # ENVELOPE next to command_id, and appear nowhere inside `result`.
        #
        # This suite's GOOD fixture had them nested, so every test passed while
        # production recorded all four engines' successful runs as FAILURES --
        # a history panel showing a fleet-wide outage that never happened.
        db = FakeSession()
        wire = {
            "changed": True,
            "executor": "puppet",
            "recap": {"ok": 1, "changed": 1, "failed": 0},
            "tasks": [],
        }
        await handler.handle_config_profile_result(
            db, conn(), message(wire, success=True, exit_code=0)
        )
        row = db.added[0]
        assert (
            row.success is True
        ), "envelope success must win over its absence in result"
        assert row.exit_code == 0

    @pytest.mark.asyncio
    async def test_an_envelope_failure_is_recorded_as_a_failure(self):
        db = FakeSession()
        wire = {"changed": False, "executor": "chef", "tasks": []}
        await handler.handle_config_profile_result(
            db, conn(), message(wire, success=False, exit_code=1)
        )
        assert db.added[0].success is False
        assert db.added[0].exit_code == 1

    @pytest.mark.asyncio
    async def test_a_nested_success_still_counts_for_older_agents(self):
        # The envelope is preferred, not required: an agent that reports the
        # old way must not start recording every run as failed.
        db = FakeSession()
        await handler.handle_config_profile_result(db, conn(), message(GOOD))
        assert db.added[0].success is True

    @pytest.mark.asyncio
    async def test_an_unchanged_run_is_still_recorded(self):
        # The whole point of idempotency reporting; dropping these as boring
        # makes "nothing changed for three runs" unanswerable.
        db = FakeSession()
        quiet = dict(GOOD, changed=False, recap={"ok": 3, "changed": 0})
        await handler.handle_config_profile_result(db, conn(), message(quiet))
        assert db.added and db.added[0].changed is False
        assert db.added[0].tasks_changed == 0

    @pytest.mark.asyncio
    async def test_a_failed_run_is_recorded_with_its_reason(self):
        db = FakeSession()
        bad = {"success": False, "reason": "executor_missing", "changed": False}
        await handler.handle_config_profile_result(db, conn(), message(bad))
        row = db.added[0]
        assert row.success is False
        assert row.reason == "executor_missing"

    @pytest.mark.asyncio
    async def test_check_mode_is_never_confused_with_an_applied_change(self):
        db = FakeSession()
        dry = dict(GOOD, check_mode=True)
        await handler.handle_config_profile_result(db, conn(), message(dry))
        assert db.added[0].check_mode is True

    @pytest.mark.asyncio
    async def test_task_detail_is_stored_as_json(self):
        db = FakeSession()
        await handler.handle_config_profile_result(db, conn(), message(GOOD))
        assert json.loads(db.added[0].task_detail)[0]["status"] == "changed"


class TestResilience:
    @pytest.mark.asyncio
    async def test_an_enormous_task_list_is_truncated_not_stored_whole(self):
        # An unbounded Text column filled by a remote host is a disk-exhaustion
        # path, not merely untidy.
        db = FakeSession()
        huge = dict(GOOD, tasks=[{"task": "x" * 200, "status": "ok"}] * 2000)
        await handler.handle_config_profile_result(db, conn(), message(huge))
        detail = db.added[0].task_detail
        assert len(detail) <= handler.MAX_TASK_DETAIL_CHARS + 32
        assert detail.endswith("[truncated]")

    @pytest.mark.asyncio
    async def test_stderr_is_truncated_too(self):
        db = FakeSession()
        noisy = dict(GOOD, success=False, stderr="e" * 50000)
        await handler.handle_config_profile_result(db, conn(), message(noisy))
        assert len(db.added[0].error_output) <= handler.MAX_ERROR_CHARS + 32

    @pytest.mark.asyncio
    async def test_a_non_object_result_is_ignored_rather_than_raising(self):
        db = FakeSession()
        out = await handler.handle_config_profile_result(
            db, conn(), {"command_type": "apply_config_profile", "result": "oops"}
        )
        assert out["success"] is False
        assert db.added == []

    @pytest.mark.asyncio
    async def test_an_unidentifiable_host_is_ignored_rather_than_raising(self):
        db = FakeSession(host=None)
        out = await handler.handle_config_profile_result(
            db, SimpleNamespace(host_id=None, hostname=None), message(GOOD)
        )
        assert out["success"] is False
        assert out["error"] == "unknown_host"

    @pytest.mark.asyncio
    async def test_hostname_falls_back_to_a_host_lookup(self):
        db = FakeSession(host=SimpleNamespace(id="looked-up"))
        await handler.handle_config_profile_result(
            db, SimpleNamespace(host_id=None, hostname="host.invalid"), message(GOOD)
        )
        assert db.added[0].host_id == "looked-up"

    @pytest.mark.asyncio
    async def test_a_malformed_profile_id_does_not_lose_the_run(self):
        # The result is still worth recording; only the association is lost.
        db = FakeSession()
        out = await handler.handle_config_profile_result(
            db, conn(), message(dict(GOOD, profile_id="not-a-uuid"))
        )
        assert out["success"] is True
        assert db.added[0].profile_id is None

    @pytest.mark.asyncio
    async def test_a_database_failure_rolls_back_and_returns(self):
        # Raising here would stall every other host's messages behind this one.
        db = FakeSession(explode=True)
        out = await handler.handle_config_profile_result(db, conn(), message(GOOD))
        assert out["success"] is False
        assert db.rollbacks == 1
