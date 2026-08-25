# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Diagnostic collection request, retrieval, and result ingestion.

The host carries a ``diagnostics_request_status`` flag that drives a spinner
in the UI, and only three places ever clear it: the list route (when a request
produced nothing), the delete route (when the last report goes), and the
result handler.  Each of those is a branch that leaves the fleet view stuck on
"pending" for ever if it stops firing, with no error and no log line to point
at -- so each is asserted directly.

Timestamps are the other quiet hazard.  Columns are stored naive and every
route re-stamps them UTC on the way out; a route that forgets renders in the
browser's local zone and a collection appears to have finished before it
started.

The DB is faked: these are branch and shape tests, not persistence tests.
"""

import json
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import diagnostics as diag

MOD = "backend.api.diagnostics"
HOST_ID = "33333333-3333-4333-8333-333333333333"
DIAG_ID = "44444444-4444-4444-8444-444444444444"


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def offset(self, n):
        return _FakeQuery(self._rows[n:])

    def limit(self, n):
        return _FakeQuery(self._rows[:n])

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def count(self):
        return len(self._rows)


class _FakeSession:
    def __init__(self, **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self.added = []
        self.deleted = []
        self.executed = []
        self.commits = 0

    def query(self, model):
        return _FakeQuery(self._by_model.get(model.__name__, []))

    def add(self, row):
        self.added.append(row)

    def delete(self, row):
        self.deleted.append(row)
        for rows in self._by_model.values():
            if row in rows:
                rows.remove(row)

    def execute(self, stmt):
        self.executed.append(stmt)

    def commit(self):
        self.commits += 1

    def refresh(self, row):
        if getattr(row, "id", None) is None:
            row.id = uuid.uuid4()

    def __call__(self, *_a, **_k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    @property
    def status_updates(self):
        """The values every ``update(Host)`` statement set."""
        return [dict(s.compile().params) for s in self.executed]


def _host(**overrides):
    host = SimpleNamespace(
        id=HOST_ID,
        fqdn="host.invalid",
        approval_status="approved",
        diagnostics_request_status=None,
        diagnostics_requested_at=None,
    )
    for key, value in overrides.items():
        setattr(host, key, value)
    return host


def _report(**overrides):
    report = SimpleNamespace(
        id=DIAG_ID,
        host_id=HOST_ID,
        collection_id="col-1",
        collection_status="completed",
        requested_by="system",
        requested_at=datetime(2026, 1, 1, 12, 0),
        started_at=datetime(2026, 1, 1, 12, 1),
        completed_at=datetime(2026, 1, 1, 12, 5),
        collection_size_bytes=1024,
        files_collected=7,
        error_message=None,
        system_logs=None,
        configuration_files=None,
        network_information=None,
        process_list=None,
        disk_usage=None,
        environment_variables=None,
        agent_logs=None,
        system_information=None,
        updated_at=None,
    )
    for key, value in overrides.items():
        setattr(report, key, value)
    return report


def _user():
    return SimpleNamespace(id="u1", userid="admin@invalid")


class _Env:
    """Binds both sessionmakers and captures the queue + audit trail."""

    def __init__(self, session):
        self.session = session
        self.queued = []
        self.audits = []

    def __enter__(self):
        self._patches = [
            patch(f"{MOD}.sessionmaker", return_value=self.session),
            patch(f"{MOD}.get_request_engine"),
            patch(f"{MOD}.db_module.get_engine"),
            patch(f"{MOD}.validate_host_approval_status"),
            patch(
                f"{MOD}.queue_ops.enqueue_message",
                side_effect=lambda **kw: self.queued.append(kw) or "msg-1",
            ),
            patch(
                f"{MOD}.AuditService.log",
                side_effect=lambda **kw: self.audits.append(kw),
            ),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *_exc):
        for p in self._patches:
            p.stop()
        return False


class TestCollectDiagnostics:
    async def _collect(self, session, host_id=HOST_ID, request=None):
        env = _Env(session)
        with env:
            out = await diag.collect_diagnostics(
                host_id, request=request, current_user=_user()
            )
        return out, env

    @pytest.mark.asyncio
    async def test_a_request_creates_a_report_and_queues_the_command(self):
        session = _FakeSession(Host=[_host()])
        out, env = await self._collect(session)
        assert out["result"] is True
        assert out["collection_id"]
        report = session.added[0]
        # The report row must exist before the command ships: the result
        # handler finds it by collection_id, and a result that arrives first
        # would 404 and the collected data be dropped.
        assert report.collection_id == out["collection_id"]
        assert env.queued[0]["host_id"] == HOST_ID

    @pytest.mark.asyncio
    async def test_the_report_ends_at_collecting_not_pending(self):
        session = _FakeSession(Host=[_host()])
        await self._collect(session)
        # "pending" means queued-but-not-sent; leaving it there after a
        # successful enqueue makes the UI show the wrong phase.
        assert session.added[0].collection_status == "collecting"
        assert session.added[0].started_at is not None

    @pytest.mark.asyncio
    async def test_the_hosts_pending_flag_is_stamped(self):
        session = _FakeSession(Host=[_host()])
        await self._collect(session)
        params = session.status_updates[0]
        assert params["diagnostics_request_status"] == "pending"
        assert params["diagnostics_requested_at"] is not None

    @pytest.mark.asyncio
    async def test_the_default_collection_types_are_sent_when_no_body_arrives(self):
        session = _FakeSession(Host=[_host()])
        _, env = await self._collect(session)
        types = env.queued[0]["message_data"]["data"]["parameters"]["collection_types"]
        assert "system_logs" in types
        assert "agent_logs" in types
        assert len(types) == 8

    @pytest.mark.asyncio
    async def test_an_explicit_collection_type_list_is_honoured(self):
        session = _FakeSession(Host=[_host()])
        request = diag.DiagnosticRequest(collection_types=["network_info"])
        _, env = await self._collect(session, request=request)
        params = env.queued[0]["message_data"]["data"]["parameters"]
        assert params["collection_types"] == ["network_info"]
        assert env.audits[0]["details"]["collection_types"] == ["network_info"]

    @pytest.mark.asyncio
    async def test_an_unknown_host_is_a_404(self):
        env = _Env(_FakeSession())
        with env:
            with pytest.raises(HTTPException) as exc:
                await diag.collect_diagnostics(HOST_ID, current_user=_user())
        assert exc.value.status_code == 404
        assert env.queued == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("host_id", ["not-a-uuid", "", "12ab"])
    async def test_a_malformed_host_id_is_a_422(self, host_id):
        with pytest.raises(HTTPException) as exc:
            await diag.collect_diagnostics(host_id, current_user=_user())
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_an_integer_host_id_is_accepted_for_compatibility(self):
        session = _FakeSession(Host=[_host()])
        out, _ = await self._collect(session, host_id="42")
        assert out["result"] is True

    @pytest.mark.asyncio
    async def test_an_unapproved_host_is_refused_before_anything_is_written(self):
        session = _FakeSession(Host=[_host(approval_status="pending")])
        env = _Env(session)
        with env:
            with patch(
                f"{MOD}.validate_host_approval_status",
                side_effect=HTTPException(status_code=400, detail="not approved"),
            ):
                with pytest.raises(HTTPException) as exc:
                    await diag.collect_diagnostics(HOST_ID, current_user=_user())
        assert exc.value.status_code == 400
        assert session.added == []


class TestGetHostDiagnostics:
    async def _list(self, session, **kwargs):
        env = _Env(session)
        with env:
            return await diag.get_host_diagnostics(HOST_ID, **kwargs), env

    @pytest.mark.asyncio
    async def test_reports_are_serialized_with_utc_timestamps(self):
        session = _FakeSession(Host=[_host()], DiagnosticReport=[_report()])
        out, _ = await self._list(session, limit=10, offset=0)
        row = out["diagnostics"][0]
        assert row["status"] == "completed"
        assert row["requested_at"].endswith("+00:00")
        assert row["started_at"].endswith("+00:00")
        assert row["files_collected"] == 7

    @pytest.mark.asyncio
    async def test_unfinished_timestamps_serialize_as_null(self):
        report = _report(started_at=None, completed_at=None)
        session = _FakeSession(Host=[_host()], DiagnosticReport=[report])
        out, _ = await self._list(session, limit=10, offset=0)
        assert out["diagnostics"][0]["started_at"] is None
        assert out["diagnostics"][0]["completed_at"] is None

    @pytest.mark.asyncio
    async def test_a_stuck_pending_flag_is_cleared_when_nothing_arrived(self):
        # Otherwise the host shows a diagnostics spinner for ever after a
        # collection that produced no report.
        session = _FakeSession(Host=[_host(diagnostics_request_status="pending")])
        out, _ = await self._list(session, limit=10, offset=0)
        assert out["diagnostics"] == []
        assert session.status_updates[0]["diagnostics_request_status"] is None

    @pytest.mark.asyncio
    async def test_an_idle_host_with_no_reports_is_left_alone(self):
        session = _FakeSession(Host=[_host()])
        await self._list(session, limit=10, offset=0)
        assert session.executed == []

    @pytest.mark.asyncio
    async def test_a_host_with_reports_keeps_its_flag(self):
        session = _FakeSession(
            Host=[_host(diagnostics_request_status="pending")],
            DiagnosticReport=[_report()],
        )
        await self._list(session, limit=10, offset=0)
        assert session.executed == []

    @pytest.mark.asyncio
    async def test_paging_slices_the_result_set(self):
        reports = [_report(collection_id=f"col-{i}") for i in range(5)]
        session = _FakeSession(Host=[_host()], DiagnosticReport=reports)
        out, _ = await self._list(session, limit=2, offset=1)
        assert [r["collection_id"] for r in out["diagnostics"]] == ["col-1", "col-2"]

    @pytest.mark.asyncio
    async def test_an_unknown_host_is_a_404(self):
        env = _Env(_FakeSession())
        with env:
            with pytest.raises(HTTPException) as exc:
                await diag.get_host_diagnostics(HOST_ID, limit=10, offset=0)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_malformed_host_id_is_a_422(self):
        with pytest.raises(HTTPException) as exc:
            await diag.get_host_diagnostics("not-a-uuid", limit=10, offset=0)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_an_integer_host_id_is_accepted(self):
        session = _FakeSession(Host=[_host()])
        env = _Env(session)
        with env:
            out = await diag.get_host_diagnostics("42", limit=10, offset=0)
        assert out["host_id"] == "42"


class TestGetDiagnosticReport:
    async def _get(self, session, diagnostic_id=DIAG_ID):
        env = _Env(session)
        with env:
            return await diag.get_diagnostic_report(diagnostic_id)

    @pytest.mark.asyncio
    async def test_the_full_report_includes_every_data_section(self):
        report = _report(
            system_logs=json.dumps(["line"]),
            network_information={"iface": "eth0"},
        )
        out = await self._get(_FakeSession(DiagnosticReport=[report]))
        data = out["diagnostic_data"]
        assert data["system_logs"] == ["line"]
        # Already-decoded columns pass straight through.
        assert data["network_info"] == {"iface": "eth0"}
        assert set(data) == {
            "system_logs",
            "configuration_files",
            "network_info",
            "process_info",
            "disk_usage",
            "environment_variables",
            "agent_logs",
            "system_information",
        }

    @pytest.mark.asyncio
    async def test_a_corrupt_json_column_reads_as_null_rather_than_500ing(self):
        # An agent that truncated its upload must not make the whole report
        # unviewable -- the other sections are still useful.
        report = _report(system_logs="{not json", disk_usage=json.dumps({"/": "90%"}))
        out = await self._get(_FakeSession(DiagnosticReport=[report]))
        assert out["diagnostic_data"]["system_logs"] is None
        assert out["diagnostic_data"]["disk_usage"] == {"/": "90%"}

    @pytest.mark.asyncio
    async def test_absent_sections_read_as_null(self):
        out = await self._get(_FakeSession(DiagnosticReport=[_report()]))
        assert all(v is None for v in out["diagnostic_data"].values())

    @pytest.mark.asyncio
    async def test_an_unknown_report_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await self._get(_FakeSession())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_malformed_id_is_a_422(self):
        with pytest.raises(HTTPException) as exc:
            await diag.get_diagnostic_report("not-a-uuid")
        assert exc.value.status_code == 422


class TestGetDiagnosticStatus:
    @pytest.mark.asyncio
    async def test_the_status_view_omits_the_payload(self):
        report = _report(system_logs=json.dumps(["huge"]))
        env = _Env(_FakeSession(DiagnosticReport=[report]))
        with env:
            out = await diag.get_diagnostic_status(DIAG_ID)
        # This is polled while a collection runs; shipping the payload with
        # every poll would move megabytes per second.
        assert "diagnostic_data" not in out
        assert out["status"] == "completed"
        assert out["requested_at"].endswith("+00:00")

    @pytest.mark.asyncio
    async def test_an_in_flight_collection_reports_null_completion(self):
        report = _report(collection_status="collecting", completed_at=None)
        env = _Env(_FakeSession(DiagnosticReport=[report]))
        with env:
            out = await diag.get_diagnostic_status(DIAG_ID)
        assert out["status"] == "collecting"
        assert out["completed_at"] is None

    @pytest.mark.asyncio
    async def test_an_unknown_report_is_a_404(self):
        env = _Env(_FakeSession())
        with env:
            with pytest.raises(HTTPException) as exc:
                await diag.get_diagnostic_status(DIAG_ID)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_malformed_id_is_a_422(self):
        with pytest.raises(HTTPException) as exc:
            await diag.get_diagnostic_status("not-a-uuid")
        assert exc.value.status_code == 422


class TestDeleteDiagnosticReport:
    @pytest.mark.asyncio
    async def test_deleting_the_last_report_clears_the_hosts_flag(self):
        report = _report()
        session = _FakeSession(DiagnosticReport=[report])
        env = _Env(session)
        with env:
            out = await diag.delete_diagnostic_report(DIAG_ID)
        assert out["result"] is True
        assert session.deleted == [report]
        # A host with no reports but a live flag shows a spinner nothing will
        # ever clear.
        assert session.status_updates[0]["diagnostics_request_status"] is None

    @pytest.mark.asyncio
    async def test_deleting_one_of_several_leaves_the_flag_alone(self):
        keep = _report(collection_id="col-2")
        session = _FakeSession(DiagnosticReport=[_report(), keep])
        env = _Env(session)
        with env:
            await diag.delete_diagnostic_report(DIAG_ID)
        assert session.executed == []

    @pytest.mark.asyncio
    async def test_an_unknown_report_is_a_404(self):
        env = _Env(_FakeSession())
        with env:
            with pytest.raises(HTTPException) as exc:
                await diag.delete_diagnostic_report(DIAG_ID)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_malformed_id_is_a_422(self):
        with pytest.raises(HTTPException) as exc:
            await diag.delete_diagnostic_report("not-a-uuid")
        assert exc.value.status_code == 422


class TestProcessDiagnosticResult:
    async def _process(self, result_data, report=None):
        session = _FakeSession(DiagnosticReport=[report] if report else [])
        out = await diag.process_diagnostic_result(session, result_data)
        return out, session

    @pytest.mark.asyncio
    async def test_a_successful_result_completes_the_report(self):
        report = _report(collection_status="collecting", completed_at=None)
        out, session = await self._process(
            {"collection_id": "col-1", "success": True}, report
        )
        assert out["result"] is True
        assert report.collection_status == "completed"
        assert report.completed_at is not None
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_an_unsuccessful_result_fails_the_report_with_its_error(self):
        report = _report(collection_status="collecting")
        await self._process(
            {"collection_id": "col-1", "success": False, "error": "sudo denied"},
            report,
        )
        assert report.collection_status == "failed"
        assert report.error_message == "sudo denied"

    @pytest.mark.asyncio
    async def test_a_result_with_no_success_key_is_treated_as_failed(self):
        # Defaulting to success would mark a truncated upload complete and the
        # operator would never know the collection did not finish.
        report = _report(collection_status="collecting")
        await self._process({"collection_id": "col-1"}, report)
        assert report.collection_status == "failed"

    @pytest.mark.asyncio
    async def test_each_payload_section_lands_on_its_own_column(self):
        report = _report()
        await self._process(
            {
                "collection_id": "col-1",
                "success": True,
                "system_logs": ["a"],
                "configuration_files": {"f": "x"},
                "network_info": {"iface": "eth0"},
                "process_info": ["init"],
                "disk_usage": {"/": "50%"},
                "environment_variables": {"PATH": "/bin"},
                "agent_logs": ["boot"],
                "system_information": {"os": "Linux"},
            },
            report,
        )
        # network_info -> network_information and process_info -> process_list
        # are renamed on the way in; a mix-up silently blanks both.
        assert json.loads(report.network_information) == {"iface": "eth0"}
        assert json.loads(report.process_list) == ["init"]
        assert json.loads(report.system_information) == {"os": "Linux"}
        assert json.loads(report.agent_logs) == ["boot"]

    @pytest.mark.asyncio
    async def test_an_already_serialized_section_is_not_double_encoded(self):
        report = _report()
        await self._process(
            {"collection_id": "col-1", "success": True, "system_logs": '["a"]'}, report
        )
        assert json.loads(report.system_logs) == ["a"]

    @pytest.mark.asyncio
    async def test_an_unserializable_section_is_stored_as_null(self):
        report = _report()
        await self._process(
            {"collection_id": "col-1", "success": True, "disk_usage": {1, 2}}, report
        )
        # A set is not JSON; raising here would reject the whole result and
        # lose the sections that WERE valid.
        assert report.disk_usage is None

    @pytest.mark.asyncio
    async def test_an_explicitly_null_section_is_stored_as_null(self):
        # The agent sends null for a section it was asked for but could not
        # read (no permission on /var/log, say).  That is different from
        # omitting the key, which means "not requested".
        report = _report(agent_logs="previous")
        await self._process(
            {"collection_id": "col-1", "success": True, "agent_logs": None}, report
        )
        assert report.agent_logs is None

    @pytest.mark.asyncio
    async def test_an_omitted_section_is_left_untouched(self):
        report = _report(system_logs="previous")
        await self._process({"collection_id": "col-1", "success": True}, report)
        assert report.system_logs == "previous"

    @pytest.mark.asyncio
    async def test_the_size_and_file_count_are_recorded(self):
        report = _report(collection_size_bytes=None, files_collected=None)
        await self._process(
            {
                "collection_id": "col-1",
                "success": True,
                "collection_size_bytes": 4096,
                "files_collected": 12,
            },
            report,
        )
        assert report.collection_size_bytes == 4096
        assert report.files_collected == 12

    @pytest.mark.asyncio
    async def test_a_result_with_no_collection_id_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await self._process({"success": True})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_result_for_an_unknown_collection_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await self._process({"collection_id": "gone", "success": True})
        assert exc.value.status_code == 404
