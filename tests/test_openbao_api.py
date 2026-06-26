"""
Tests for backend.api.openbao.

Heavy I/O surface — file checks, subprocess, platform branching. All mocked
at the os/subprocess/platform boundary so tests don't touch the real
OpenBAO binary or filesystem.

Targets:
- _is_executable / find_bao_binary (env var, PATH, filesystem locations)
- get_openbao_status branches: no PID, invalid PID, dead process,
  alive process with bao status, sealed-detection, log file errors
- start_openbao, stop_openbao, seal_openbao, unseal_openbao orchestration
- The router endpoints (status/start/stop/seal/unseal/config) success + sanitization
"""

import os
import subprocess
from unittest.mock import MagicMock, mock_open, patch

import pytest

from backend.api import openbao as ob


def _completed(returncode=0, stdout="", stderr=""):
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def _selective_open(file_contents):
    """Build an `open` replacement that returns mock_open contents for files
    matching any of the given suffixes, and falls back to the real open() for
    everything else (so gettext, etc. still work)."""
    real_open = open

    def _opener(path, *args, **kwargs):
        path_str = str(path)
        for suffix, content in file_contents.items():
            if path_str.endswith(suffix):
                m = mock_open(read_data=content)
                return m()
        return real_open(path, *args, **kwargs)

    return _opener


# ---------------------------------------------------------------------------
# _is_executable
# ---------------------------------------------------------------------------


class TestIsExecutable:
    def test_returns_false_when_not_a_file(self):
        with patch("backend.api.openbao.os.path.isfile", return_value=False):
            assert ob._is_executable("/no/such/file") is False

    def test_returns_false_when_not_executable(self):
        with patch("backend.api.openbao.os.path.isfile", return_value=True), patch(
            "backend.api.openbao.os.access", return_value=False
        ):
            assert ob._is_executable("/some/path") is False

    def test_returns_true_when_file_and_executable(self):
        with patch("backend.api.openbao.os.path.isfile", return_value=True), patch(
            "backend.api.openbao.os.access", return_value=True
        ):
            assert ob._is_executable("/usr/local/bin/bao") is True


# ---------------------------------------------------------------------------
# find_bao_binary
# ---------------------------------------------------------------------------


class TestFindBaoBinary:
    def test_uses_openbao_bin_env_when_executable(self):
        with patch.dict(os.environ, {"OPENBAO_BIN": "/custom/bao"}, clear=False), patch(
            "backend.api.openbao._is_executable", return_value=True
        ):
            assert ob.find_bao_binary() == "/custom/bao"

    def test_warns_when_openbao_bin_set_but_not_executable(self, caplog):
        with patch.dict(os.environ, {"OPENBAO_BIN": "/bad/bao"}, clear=False), patch(
            "backend.api.openbao._is_executable", return_value=False
        ), patch("shutil.which", return_value=None):
            result = ob.find_bao_binary()
        # Falls through to PATH (returns None) — warning logged.
        assert result is None

    def test_returns_bao_when_in_path(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "shutil.which", return_value="/usr/bin/bao"
        ):
            assert ob.find_bao_binary() == "bao"

    def test_falls_back_to_filesystem_locations(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "shutil.which", return_value=None
        ), patch("backend.api.openbao._is_executable", side_effect=[False, True]):
            # Second-call True means /usr/local/bin/bao matched.
            result = ob.find_bao_binary()
        assert result == "/usr/local/bin/bao"

    def test_returns_none_when_nothing_found(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "shutil.which", return_value=None
        ), patch("backend.api.openbao._is_executable", return_value=False):
            assert ob.find_bao_binary() is None


# ---------------------------------------------------------------------------
# get_openbao_status
# ---------------------------------------------------------------------------


class TestGetOpenbaoStatus:
    def test_no_pid_file_returns_stopped(self):
        with patch("backend.api.openbao.os.path.exists", return_value=False):
            status = ob.get_openbao_status()
        assert status["running"] is False
        assert status["status"] == "stopped"
        assert status["pid"] is None

    def test_invalid_pid_file_returns_error(self):
        with patch("backend.api.openbao.os.path.exists", return_value=True), patch(
            "builtins.open", _selective_open({".openbao.pid": "not-a-number"})
        ):
            status = ob.get_openbao_status()
        assert status["status"] == "error"

    def test_pid_file_unreadable_returns_error(self):
        real_open = open

        def _opener(path, *args, **kwargs):
            if str(path).endswith(".openbao.pid"):
                raise IOError("denied")
            return real_open(path, *args, **kwargs)

        with patch("backend.api.openbao.os.path.exists", return_value=True), patch(
            "builtins.open", side_effect=_opener
        ):
            status = ob.get_openbao_status()
        assert status["status"] == "error"

    def test_dead_process_cleans_up_pid_file(self):
        # PID exists but os.kill(pid, 0) raises OSError → process not running.
        with patch("backend.api.openbao.os.path.exists", return_value=True), patch(
            "builtins.open", _selective_open({".openbao.pid": "12345"})
        ), patch("backend.api.openbao.platform.system", return_value="Linux"), patch(
            "backend.api.openbao.os.kill", side_effect=OSError("no process")
        ), patch(
            "backend.api.openbao.os.remove"
        ) as remove:
            status = ob.get_openbao_status()
        assert status["status"] == "stopped"
        remove.assert_called_once()

    def test_dead_process_swallows_remove_error(self):
        with patch("backend.api.openbao.os.path.exists", return_value=True), patch(
            "builtins.open", _selective_open({".openbao.pid": "12345"})
        ), patch("backend.api.openbao.platform.system", return_value="Linux"), patch(
            "backend.api.openbao.os.kill", side_effect=OSError("no process")
        ), patch(
            "backend.api.openbao.os.remove", side_effect=OSError("readonly")
        ):
            status = ob.get_openbao_status()
        # Should not raise — just returns stopped.
        assert status["status"] == "stopped"

    def test_alive_process_returns_running_with_bao_status(self):
        # pid file path exists, pid is read, process check passes.
        # Then bao status returns parseable output with sealed=false.
        bao_output = "Sealed: false\nVersion: 1.15.0\n"
        with patch(
            "backend.api.openbao.os.path.exists",
            side_effect=lambda p: True,  # pid file + log file both exist
        ), patch("builtins.open", _selective_open({".openbao.pid": "12345"})), patch(
            "backend.api.openbao.platform.system", return_value="Linux"
        ), patch(
            "backend.api.openbao.os.kill"
        ), patch(
            "backend.api.openbao.find_bao_binary", return_value="/usr/bin/bao"
        ), patch(
            "backend.api.openbao.subprocess.run",
            return_value=_completed(0, stdout=bao_output),
        ), patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={"url": "http://x", "token": "t"},
        ):
            status = ob.get_openbao_status()
        assert status["running"] is True
        assert status["status"] == "running"
        assert status["pid"] == 12345
        assert status["sealed"] is False

    def test_alive_process_sealed_extracted_from_status_output(self):
        bao_output = "Sealed: true\n"
        with patch(
            "backend.api.openbao.os.path.exists", side_effect=lambda p: True
        ), patch("builtins.open", _selective_open({".openbao.pid": "12345"})), patch(
            "backend.api.openbao.platform.system", return_value="Linux"
        ), patch(
            "backend.api.openbao.os.kill"
        ), patch(
            "backend.api.openbao.find_bao_binary", return_value="/usr/bin/bao"
        ), patch(
            "backend.api.openbao.subprocess.run",
            return_value=_completed(0, stdout=bao_output),
        ), patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={"url": "http://x", "token": "t"},
        ):
            status = ob.get_openbao_status()
        assert status["sealed"] is True

    def test_alive_process_bao_status_failure_marks_seal_via_stderr(self):
        # When bao status fails AND stderr mentions "sealed", we infer sealed=True.
        with patch(
            "backend.api.openbao.os.path.exists", side_effect=lambda p: True
        ), patch("builtins.open", _selective_open({".openbao.pid": "12345"})), patch(
            "backend.api.openbao.platform.system", return_value="Linux"
        ), patch(
            "backend.api.openbao.os.kill"
        ), patch(
            "backend.api.openbao.find_bao_binary", return_value="/usr/bin/bao"
        ), patch(
            "backend.api.openbao.subprocess.run",
            return_value=_completed(1, stderr="vault is sealed"),
        ), patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={"url": "http://x", "token": "t"},
        ):
            status = ob.get_openbao_status()
        assert status["sealed"] is True

    def test_subprocess_error_handled_gracefully(self):
        with patch(
            "backend.api.openbao.os.path.exists", side_effect=lambda p: True
        ), patch("builtins.open", _selective_open({".openbao.pid": "12345"})), patch(
            "backend.api.openbao.platform.system", return_value="Linux"
        ), patch(
            "backend.api.openbao.os.kill"
        ), patch(
            "backend.api.openbao.find_bao_binary", return_value="/usr/bin/bao"
        ), patch(
            "backend.api.openbao.subprocess.run",
            side_effect=subprocess.SubprocessError("died"),
        ), patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={"url": "http://x", "token": "t"},
        ):
            status = ob.get_openbao_status()
        assert status["health"] == {"error": "Unable to connect to OpenBAO server"}


# ---------------------------------------------------------------------------
# Router endpoints — minimal shape checks (status sanitisation + dispatch)
# ---------------------------------------------------------------------------


class TestRouterEndpoints:
    def test_get_status_endpoint_returns_status(self, client, auth_headers):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={
                "running": False,
                "status": "stopped",
                "message": "x",
                "pid": None,
                "server_url": None,
                "health": None,
                "sealed": None,
            },
        ):
            resp = client.get("/api/openbao/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    def test_get_config_returns_safe_subset(self, client, auth_headers):
        with patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={
                "enabled": True,
                "url": "http://localhost:8200",
                "mount_path": "secret",
                "timeout": 30,
                "verify_ssl": True,
                "dev_mode": False,
                "token": "shhh-secret",
            },
        ):
            resp = client.get("/api/openbao/config", headers=auth_headers)
        body = resp.json()
        # Token must NOT leak — has_token boolean only.
        assert "token" not in body
        assert body["has_token"] is True
        assert body["url"] == "http://localhost:8200"

    def test_start_endpoint_sanitises_response(self, client, auth_headers):
        with patch(
            "backend.api.openbao.start_openbao",
            return_value={
                "success": True,
                "message": "started",
                "status": {"running": True, "pid": 999, "server_url": "http://x"},
            },
        ):
            resp = client.post("/api/openbao/start", headers=auth_headers)
        body = resp.json()
        # The endpoint sanitises — only `success` is exposed on success.
        assert body == {"success": True}

    def test_start_endpoint_failure_returns_generic_error(self, client, auth_headers):
        with patch(
            "backend.api.openbao.start_openbao",
            return_value={
                "success": False,
                "message": "internal: leaked detail",
            },
        ):
            resp = client.post("/api/openbao/start", headers=auth_headers)
        body = resp.json()
        assert body["success"] is False
        assert "leaked" not in body["error"].lower()

    def test_start_endpoint_exception_returns_500(self, client, auth_headers):
        with patch(
            "backend.api.openbao.start_openbao",
            side_effect=RuntimeError("blew up"),
        ):
            resp = client.post("/api/openbao/start", headers=auth_headers)
        assert resp.status_code == 500
        assert "blew up" not in resp.text

    def test_stop_endpoint_sanitises(self, client, auth_headers):
        with patch(
            "backend.api.openbao.stop_openbao",
            return_value={"success": False, "message": "secret detail"},
        ):
            resp = client.post("/api/openbao/stop", headers=auth_headers)
        body = resp.json()
        assert body["success"] is False
        assert "secret detail" not in str(body)

    def test_seal_endpoint_sanitises(self, client, auth_headers):
        with patch(
            "backend.api.openbao.seal_openbao",
            return_value={"success": True, "message": "sealed"},
        ):
            resp = client.post("/api/openbao/seal", headers=auth_headers)
        assert resp.json() == {"success": True}

    def test_unseal_endpoint_sanitises(self, client, auth_headers):
        with patch(
            "backend.api.openbao.unseal_openbao",
            return_value={"success": True, "message": "unsealed"},
        ):
            resp = client.post("/api/openbao/unseal", headers=auth_headers)
        assert resp.json() == {"success": True}

    def test_seal_endpoint_exception_returns_500(self, client, auth_headers):
        with patch(
            "backend.api.openbao.seal_openbao",
            side_effect=RuntimeError("internal"),
        ):
            resp = client.post("/api/openbao/seal", headers=auth_headers)
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# start_openbao orchestration
# ---------------------------------------------------------------------------


class TestStartOpenbao:
    def test_already_running_short_circuits(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": True, "status": "running"},
        ):
            result = ob.start_openbao()
        assert result["success"] is True
        assert "already" in result["message"].lower()

    def test_missing_script_raises_500(self):
        # status says not running, but script doesn't exist on disk.
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": False},
        ), patch("backend.api.openbao.platform.system", return_value="Linux"), patch(
            "backend.api.openbao.os.path.exists", return_value=False
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc:
                ob.start_openbao()
            assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# stop_openbao orchestration
# ---------------------------------------------------------------------------


class TestStopOpenbao:
    def test_not_running_short_circuits(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": False, "status": "stopped"},
        ):
            result = ob.stop_openbao()
        assert result["success"] is True

    def test_timeout_returns_failure(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            side_effect=[
                {"running": True},  # initial check
                {"running": True},  # post-timeout status
            ],
        ), patch("backend.api.openbao.platform.system", return_value="Linux"), patch(
            "backend.api.openbao.os.path.exists", return_value=True
        ), patch(
            "backend.api.openbao.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="stop", timeout=15),
        ):
            result = ob.stop_openbao()
        assert result["success"] is False
        assert "timeout" in result["message"].lower()


# ---------------------------------------------------------------------------
# start_openbao — happy path + Linux script branch
# ---------------------------------------------------------------------------


class TestStartOpenbaoHappyPath:
    def test_linux_success(self):
        # Initial status: not running. Subprocess runs OK. Final status: running.
        with patch(
            "backend.api.openbao.get_openbao_status",
            side_effect=[
                {"running": False},
                {"running": True, "pid": 4321},
            ],
        ), patch("backend.api.openbao.platform.system", return_value="Linux"), patch(
            "backend.api.openbao.os.path.exists", return_value=True
        ), patch(
            "backend.api.openbao.subprocess.run",
            return_value=_completed(0, stdout="OpenBAO started"),
        ), patch(
            "time.sleep"
        ):
            result = ob.start_openbao()
        assert result["success"] is True
        assert result["status"]["running"] is True

    def test_linux_script_failure_returns_stderr(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            side_effect=[
                {"running": False},
                {"running": False},
            ],
        ), patch("backend.api.openbao.platform.system", return_value="Linux"), patch(
            "backend.api.openbao.os.path.exists", return_value=True
        ), patch(
            "backend.api.openbao.subprocess.run",
            return_value=_completed(2, stderr="bind: address in use"),
        ), patch(
            "time.sleep"
        ):
            result = ob.start_openbao()
        assert result["success"] is False
        assert "bind: address in use" in result["error"]

    def test_linux_timeout_returns_failure(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            side_effect=[
                {"running": False},
                {"running": False},
            ],
        ), patch("backend.api.openbao.platform.system", return_value="Linux"), patch(
            "backend.api.openbao.os.path.exists", return_value=True
        ), patch(
            "backend.api.openbao.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="start", timeout=30),
        ), patch(
            "time.sleep"
        ):
            result = ob.start_openbao()
        assert result["success"] is False
        assert "timeout" in result["message"].lower()

    def test_linux_unexpected_exception_returns_generic_failure(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            side_effect=[
                {"running": False},
                {"running": False},
            ],
        ), patch("backend.api.openbao.platform.system", return_value="Linux"), patch(
            "backend.api.openbao.os.path.exists", return_value=True
        ), patch(
            "backend.api.openbao.subprocess.run",
            side_effect=RuntimeError("unexpected"),
        ):
            result = ob.start_openbao()
        assert result["success"] is False


# ---------------------------------------------------------------------------
# stop_openbao — successful Linux path
# ---------------------------------------------------------------------------


class TestStopOpenbaoSuccess:
    def test_linux_success(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            side_effect=[
                {"running": True},
                {"running": False, "status": "stopped"},
            ],
        ), patch("backend.api.openbao.platform.system", return_value="Linux"), patch(
            "backend.api.openbao.os.path.exists", return_value=True
        ), patch(
            "backend.api.openbao.subprocess.run",
            return_value=_completed(0, stdout="stopped"),
        ), patch(
            "time.sleep"
        ):
            result = ob.stop_openbao()
        assert result["success"] is True
        assert result["status"]["running"] is False


# ---------------------------------------------------------------------------
# seal_openbao + unseal_openbao orchestration
# ---------------------------------------------------------------------------


class TestSealOpenbao:
    def test_short_circuits_when_not_running(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": False},
        ):
            result = ob.seal_openbao()
        assert result["success"] is False
        # Returns failure but with a clear "not running" error.

    def test_seal_success(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": True, "server_url": "http://x"},
        ), patch(
            "backend.api.openbao.find_bao_binary", return_value="/usr/bin/bao"
        ), patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={"url": "http://x", "token": "t"},
        ), patch(
            "backend.api.openbao.subprocess.run",
            return_value=_completed(0, stdout="Sealed"),
        ):
            result = ob.seal_openbao()
        assert result["success"] is True

    def test_seal_failure_returns_stderr(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": True, "server_url": "http://x"},
        ), patch(
            "backend.api.openbao.find_bao_binary", return_value="/usr/bin/bao"
        ), patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={"url": "http://x", "token": "t"},
        ), patch(
            "backend.api.openbao.subprocess.run",
            return_value=_completed(1, stderr="permission denied"),
        ):
            result = ob.seal_openbao()
        assert result["success"] is False

    def test_seal_no_binary_returns_failure(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": True, "server_url": "http://x"},
        ), patch("backend.api.openbao.find_bao_binary", return_value=None), patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={"url": "http://x", "token": "t"},
        ):
            result = ob.seal_openbao()
        assert result["success"] is False

    def test_seal_unexpected_exception_returns_failure(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": True, "server_url": "http://x"},
        ), patch(
            "backend.api.openbao.find_bao_binary", return_value="/usr/bin/bao"
        ), patch(
            "backend.api.openbao.config.get_vault_config",
            side_effect=RuntimeError("config broken"),
        ):
            result = ob.seal_openbao()
        assert result["success"] is False


class TestUnsealOpenbao:
    def test_short_circuits_when_not_running(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": False},
        ):
            result = ob.unseal_openbao()
        assert result["success"] is False

    def test_unseal_no_keys_in_config_returns_failure(self):
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": True, "server_url": "http://x"},
        ), patch(
            "backend.api.openbao.find_bao_binary", return_value="/usr/bin/bao"
        ), patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={
                "url": "http://x",
                "token": "t",
                # No unseal_keys → unseal can't proceed.
            },
        ):
            result = ob.unseal_openbao()
        assert result["success"] is False

    def test_unseal_unexpected_exception_returns_failure(self):
        # The exception must originate inside the try-block (after the
        # get_vault_config / find_bao_binary checks).  Make subprocess.run
        # raise something that isn't TimeoutExpired.
        with patch(
            "backend.api.openbao.get_openbao_status",
            return_value={"running": True, "server_url": "http://x", "sealed": True},
        ), patch(
            "backend.api.openbao.find_bao_binary", return_value="/usr/bin/bao"
        ), patch(
            "backend.api.openbao.config.get_vault_config",
            return_value={"url": "http://x", "token": "t", "dev_mode": True},
        ), patch(
            "backend.api.openbao.subprocess.run",
            side_effect=RuntimeError("blew up"),
        ):
            result = ob.unseal_openbao()
        assert result["success"] is False
