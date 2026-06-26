"""
Tests for the open-source bulk operation planner.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import pytest

from backend.services.bulk_op_planner import (
    OPEN_SOURCE_OP_TYPES,
    expand_bulk_operation,
)


class TestExpandBulkOperation:
    def test_empty_host_list_returns_empty(self):
        assert expand_bulk_operation("reboot", []) == []

    def test_one_plan_per_host_in_order(self):
        out = expand_bulk_operation("reboot", ["a", "b", "c"])
        assert [hid for hid, _ in out] == ["a", "b", "c"]

    def test_reboot_plan_shape(self):
        _, plan = expand_bulk_operation("reboot", ["a"])[0]
        assert plan["commands"][0]["argv"] == ["reboot"]

    def test_shutdown_plan_shape(self):
        _, plan = expand_bulk_operation("shutdown", ["a"])[0]
        assert plan["commands"][0]["argv"] == ["shutdown", "-h", "now"]

    def test_run_script_delegates(self):
        _, plan = expand_bulk_operation(
            "run_script",
            ["a"],
            {"content": "echo hi", "shell": "bash"},
        )[0]
        # Should have files + commands like the script plan builder produces
        assert plan["files"][0]["content"] == "echo hi"
        assert plan["commands"][0]["argv"][0] == "/bin/bash"

    def test_deploy_file_plan(self):
        _, plan = expand_bulk_operation(
            "deploy_file",
            ["a"],
            {"path": "/etc/foo", "content": "bar", "mode": 0o600},
        )[0]
        assert plan["files"][0]["path"] == "/etc/foo"
        assert plan["files"][0]["mode"] == 0o600

    def test_service_control_plan(self):
        _, plan = expand_bulk_operation(
            "service_control",
            ["a"],
            {"action": "restart", "services": ["nginx", "redis"]},
        )[0]
        assert plan["service_actions"] == [
            {"service": "nginx", "action": "restart"},
            {"service": "redis", "action": "restart"},
        ]

    def test_install_package_plan(self):
        _, plan = expand_bulk_operation(
            "install_package", ["a"], {"packages": ["htop", "vim"]}
        )[0]
        assert plan["packages"] == ["htop", "vim"]

    def test_remove_package_plan(self):
        _, plan = expand_bulk_operation(
            "remove_package", ["a"], {"packages": ["broken-pkg"]}
        )[0]
        assert plan["packages_to_remove"] == ["broken-pkg"]

    def test_unsupported_op_rejected(self):
        with pytest.raises(ValueError):
            expand_bulk_operation("apply_deployment_plan", ["a"], {})

    def test_all_documented_ops_accepted(self):
        # Each supported op should produce a valid plan with at least
        # the empty default keys.
        for op in OPEN_SOURCE_OP_TYPES:
            params = {}
            if op == "run_script":
                params = {"content": "echo"}
            elif op == "deploy_file":
                params = {"path": "/tmp/x", "content": "y"}
            elif op == "service_control":
                params = {"service": "x"}
            elif op in ("install_package", "remove_package"):
                params = {"package": "x"}
            out = expand_bulk_operation(op, ["host1"], params)
            assert len(out) == 1
