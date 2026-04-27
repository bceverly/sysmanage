"""
Tests for backend.services.proplus_dispatch — the schedule-dispatch glue
between the Pro+ Cython engines and the OSS message queue.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.services import proplus_dispatch


@pytest.fixture
def stub_module_loader():
    """Patch module_loader.get_module to return a stub automation_engine."""
    with patch.object(proplus_dispatch, "module_loader") as ml:
        yield ml


class TestQueueAutomationExecution:
    def test_skips_when_engine_not_loaded(self, stub_module_loader):
        stub_module_loader.get_module.return_value = None
        execution = SimpleNamespace(id="e1", script_id="s1", host_results=[])
        schedule = SimpleNamespace(name="x")
        # Should not raise; just logs
        proplus_dispatch.queue_automation_execution(execution, schedule)

    def test_skips_when_script_unknown(self, stub_module_loader):
        engine = MagicMock()
        engine.get_script.return_value = None
        stub_module_loader.get_module.return_value = engine
        execution = SimpleNamespace(id="e1", script_id="missing", host_results=[])
        schedule = SimpleNamespace(name="x")
        proplus_dispatch.queue_automation_execution(execution, schedule)
        engine.build_script_command_plan.assert_not_called()

    def test_queues_one_message_per_host(self, stub_module_loader):
        engine = MagicMock()
        engine.get_script.return_value = SimpleNamespace(
            shell="bash",
            timeout_seconds=300,
        )
        engine.build_script_command_plan.return_value = {"files": [], "commands": []}
        stub_module_loader.get_module.return_value = engine

        execution = SimpleNamespace(
            id="e1",
            script_id="s1",
            rendered_content="echo hi",
            host_results=[
                SimpleNamespace(host_id="h1"),
                SimpleNamespace(host_id="h2"),
                SimpleNamespace(host_id="h3"),
            ],
        )
        schedule = SimpleNamespace(name="nightly")

        with patch.object(proplus_dispatch, "_enqueue_apply_plan") as enq:
            proplus_dispatch.queue_automation_execution(execution, schedule)

        assert enq.call_count == 3
        # Each call uses host_id as first arg
        host_ids = {c.args[0] for c in enq.call_args_list}
        assert host_ids == {"h1", "h2", "h3"}

    def test_individual_queue_failure_is_isolated(self, stub_module_loader):
        engine = MagicMock()
        engine.get_script.return_value = SimpleNamespace(
            shell="bash", timeout_seconds=60
        )
        engine.build_script_command_plan.return_value = {"files": [], "commands": []}
        stub_module_loader.get_module.return_value = engine

        execution = SimpleNamespace(
            id="e1",
            script_id="s1",
            rendered_content="echo",
            host_results=[
                SimpleNamespace(host_id="h1"),
                SimpleNamespace(host_id="h2"),  # this one will fail
                SimpleNamespace(host_id="h3"),
            ],
        )
        schedule = SimpleNamespace(name="x")

        def enq_with_failure(host_id, *_args, **_kw):
            if host_id == "h2":
                raise RuntimeError("queue is full")

        with patch.object(
            proplus_dispatch, "_enqueue_apply_plan", side_effect=enq_with_failure
        ) as enq:
            proplus_dispatch.queue_automation_execution(execution, schedule)
        # Tried all 3 despite middle failure
        assert enq.call_count == 3


class TestQueueFleetBulkOp:
    def test_skips_unsupported_op_type(self):
        op = SimpleNamespace(operation_type="apply_deployment_plan", id="o1")
        schedule = SimpleNamespace(name="x")
        with patch.object(proplus_dispatch, "_enqueue_apply_plan") as enq:
            proplus_dispatch.queue_fleet_bulk_op(op, schedule)
        enq.assert_not_called()

    def test_reboot_queues_per_host(self):
        op = SimpleNamespace(
            operation_type="reboot",
            id="o1",
            target_host_ids=["h1", "h2"],
            parameters={},
        )
        schedule = SimpleNamespace(name="nightly-reboot")
        with patch.object(proplus_dispatch, "_enqueue_apply_plan") as enq:
            proplus_dispatch.queue_fleet_bulk_op(op, schedule)
        assert enq.call_count == 2
        host_ids = {c.args[0] for c in enq.call_args_list}
        assert host_ids == {"h1", "h2"}

    def test_run_script_queues_per_host(self):
        op = SimpleNamespace(
            operation_type="run_script",
            id="o2",
            target_host_ids=["h1"],
            parameters={"content": "echo", "shell": "bash"},
        )
        schedule = SimpleNamespace(name="x")
        with patch.object(proplus_dispatch, "_enqueue_apply_plan") as enq:
            proplus_dispatch.queue_fleet_bulk_op(op, schedule)
        assert enq.call_count == 1


class TestRouteProplusCommandResult:
    def setup_method(self):
        # Clean correlation map between tests
        with proplus_dispatch._CORRELATIONS_LOCK:
            proplus_dispatch._CORRELATIONS.clear()

    def test_returns_false_when_no_correlation(self):
        # Unknown command_id → no Pro+ correlation, caller continues.
        out = proplus_dispatch.route_proplus_command_result(
            "unknown-msg-id", {"success": True}
        )
        assert out is False

    def test_consumes_correlation_on_first_match(self):
        proplus_dispatch._register_correlation("m1", "automation_engine", "exec1", "h1")
        with patch.object(
            proplus_dispatch.module_loader, "get_module", return_value=None
        ):
            # Engine not loaded — still routes (returns True), correlation consumed
            assert (
                proplus_dispatch.route_proplus_command_result("m1", {"success": True})
                is True
            )
        assert proplus_dispatch.correlation_count() == 0

    def test_routes_automation_success_to_engine(self):
        proplus_dispatch._register_correlation("m2", "automation_engine", "exec2", "h2")
        engine = MagicMock()
        with patch.object(
            proplus_dispatch.module_loader, "get_module", return_value=engine
        ):
            proplus_dispatch.route_proplus_command_result(
                "m2",
                {
                    "success": True,
                    "command_id": "m2",
                    "result": {
                        "success": True,
                        "results": {
                            "commands": [
                                {
                                    "success": True,
                                    "returncode": 0,
                                    "stdout": "ok",
                                    "stderr": "",
                                },
                            ]
                        },
                        "errors": [],
                    },
                },
            )
        engine.update_execution_host_result.assert_called_once()
        kwargs = engine.update_execution_host_result.call_args
        assert kwargs.args[0] == "exec2"
        assert kwargs.args[1] == "h2"
        assert kwargs.args[2] == "succeeded"

    def test_routes_automation_failure_with_error(self):
        proplus_dispatch._register_correlation("m3", "automation_engine", "exec3", "h3")
        engine = MagicMock()
        with patch.object(
            proplus_dispatch.module_loader, "get_module", return_value=engine
        ):
            proplus_dispatch.route_proplus_command_result(
                "m3",
                {
                    "success": False,
                    "command_id": "m3",
                    "error": "subprocess crashed",
                    "result": {
                        "success": False,
                        "results": {"commands": []},
                        "errors": [],
                    },
                },
            )
        engine.update_execution_host_result.assert_called_once()
        # Status should be 'failed'
        assert engine.update_execution_host_result.call_args.args[2] == "failed"

    def test_routes_fleet_success(self):
        proplus_dispatch._register_correlation("m4", "fleet_engine", "op4", "h4")
        engine = MagicMock()
        with patch.object(
            proplus_dispatch.module_loader, "get_module", return_value=engine
        ):
            proplus_dispatch.route_proplus_command_result(
                "m4",
                {
                    "success": True,
                    "command_id": "m4",
                    "result": {
                        "success": True,
                        "results": {"commands": [{"returncode": 0}]},
                    },
                },
            )
        engine.update_bulk_host_result.assert_called_once()
        assert engine.update_bulk_host_result.call_args.args[0] == "op4"
        assert engine.update_bulk_host_result.call_args.args[1] == "h4"
        assert engine.update_bulk_host_result.call_args.args[2] == "succeeded"


class TestBuildHostProvider:
    def test_provider_returns_hosts(self):
        # Stub db_maker that yields a mock session whose query returns a list.
        mock_session = MagicMock()
        mock_session.query.return_value.all.return_value = ["host1", "host2"]

        def fake_db_maker():
            yield mock_session

        provider = proplus_dispatch.build_host_provider(fake_db_maker)
        result = provider()
        assert result == ["host1", "host2"]

    def test_provider_returns_empty_on_no_session(self):
        def empty_maker():
            return  # not even a generator
            yield

        provider = proplus_dispatch.build_host_provider(empty_maker)
        # Empty maker yields nothing → provider returns []
        result = provider()
        assert result == []
