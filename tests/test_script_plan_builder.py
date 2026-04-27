"""
Tests for the open-source script plan builder.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import pytest

from backend.services.script_plan_builder import (
    SUPPORTED_SHELLS,
    build_adhoc_script_plan,
)


class TestBuildAdhocScriptPlan:
    def test_bash_default_plan_shape(self):
        plan = build_adhoc_script_plan("echo hi")
        assert "files" in plan and "commands" in plan
        assert plan["files"][0]["mode"] == 0o700
        assert plan["files"][0]["path"].startswith("/tmp/sysmanage_script_")
        assert plan["files"][0]["path"].endswith(".sh")
        assert plan["files"][0]["content"] == "echo hi"
        # First command runs the interpreter, second cleans up.
        assert plan["commands"][0]["argv"][0] == "/bin/bash"
        assert plan["commands"][1]["argv"][0] == "rm"

    def test_powershell_plan(self):
        plan = build_adhoc_script_plan("Write-Host hi", shell="powershell")
        assert plan["files"][0]["path"].endswith(".ps1")
        assert plan["files"][0]["path"].startswith("C:/Windows/Temp/")
        assert plan["commands"][0]["argv"][0] == "powershell"
        assert "Bypass" in plan["commands"][0]["argv"]

    def test_cmd_plan(self):
        plan = build_adhoc_script_plan("echo hi", shell="cmd")
        assert plan["files"][0]["path"].endswith(".bat")
        assert plan["commands"][0]["argv"][0] == "cmd.exe"

    def test_param_substitution(self):
        plan = build_adhoc_script_plan(
            "echo ${who}",
            parameter_values={"who": "alice"},
        )
        assert plan["files"][0]["content"] == "echo alice"

    def test_unknown_placeholder_left_alone(self):
        plan = build_adhoc_script_plan("echo ${unset}")
        assert plan["files"][0]["content"] == "echo ${unset}"

    def test_timeout_passed_through(self):
        plan = build_adhoc_script_plan("echo hi", timeout_seconds=42)
        assert plan["commands"][0]["timeout"] == 42

    def test_unsupported_shell_rejected(self):
        with pytest.raises(ValueError):
            build_adhoc_script_plan("echo hi", shell="fish")

    def test_all_documented_shells_accepted(self):
        for shell in SUPPORTED_SHELLS:
            # Should not raise — each supported shell produces a valid plan
            plan = build_adhoc_script_plan("noop", shell=shell)
            assert "commands" in plan and "files" in plan
