# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the sysmanage-migrate CLI (production migration tool).
"""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sysmanage_migrate.py"


def _load():
    spec = importlib.util.spec_from_file_location("sysmanage_migrate", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_progress_bar_full_is_100_percent():
    mod = _load()
    assert "100%" in mod._progress_bar(3, 3)
    assert "0%" in mod._progress_bar(0, 3)
    assert mod._progress_bar(0, 0) == ""
    # n/n is reflected in the label.
    assert "5/5" in mod._progress_bar(5, 5)


def test_fan_out_noop_when_multitenancy_disabled():
    mod = _load()
    with patch.object(mod, "_placed_tenants") as placed:
        with patch("backend.config.config.is_multitenancy_enabled", return_value=False):
            assert mod.fan_out_tenants(dry_run=False) == 0
    placed.assert_not_called()


def test_fan_out_counts_failures_and_isolates():
    mod = _load()

    def fake_provision(tid):
        if tid == "t-bad":
            raise RuntimeError("boom")
        return "rev1"

    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch.object(
        mod, "_ensure_multitenancy_engine", return_value=True
    ), patch.object(
        mod,
        "_placed_tenants",
        return_value=[
            ("t-ok", "good", True),
            ("t-bad", "bad", True),
            ("t-x", "x", False),
        ],
    ), patch(
        "backend.services.tenant_provisioning.provision_tenant_database",
        side_effect=fake_provision,
    ) as prov:
        failures = mod.fan_out_tenants(dry_run=False)

    # The unplaced tenant ("x", no role) is skipped, not provisioned.
    assert prov.call_count == 2
    # One of the two migratable tenants failed; the other still ran.
    assert failures == 1


def test_fan_out_fails_loudly_when_engine_unavailable():
    """If MT is on but the licensed engine can't be loaded, the fan-out reports
    every placed tenant as failed (rather than emitting the shim's refusal per
    tenant) and never calls provisioning."""
    mod = _load()
    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch.object(
        mod, "_ensure_multitenancy_engine", return_value=False
    ), patch.object(
        mod,
        "_placed_tenants",
        return_value=[("t-ok", "good", True), ("t-two", "two", True)],
    ), patch(
        "backend.services.tenant_provisioning.provision_tenant_database"
    ) as prov:
        failures = mod.fan_out_tenants(dry_run=False)

    assert failures == 2  # both placed tenants counted as failed
    prov.assert_not_called()


def test_dry_run_does_not_provision():
    mod = _load()
    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch.object(mod, "_placed_tenants", return_value=[("t1", "acme", True)]), patch(
        "backend.services.tenant_provisioning.provision_tenant_database"
    ) as prov:
        assert mod.fan_out_tenants(dry_run=True) == 0
    prov.assert_not_called()


def test_main_status_returns_zero():
    mod = _load()
    with patch.object(mod, "show_status", return_value=0) as status:
        assert mod.main(["--status"]) == 0
    status.assert_called_once()


def test_system_python_without_alembic_is_told_which_command_to_use(
    monkeypatch, capsys
):
    """``sudo python3 scripts/sysmanage_migrate.py`` used to die with a bare
    ModuleNotFoundError; it now names the venv and the packaged command."""
    mod = _load()
    monkeypatch.setitem(__import__("sys").modules, "alembic.config", None)
    with patch.object(mod, "show_status") as status:
        assert mod.main(["--status"]) == 2
    status.assert_not_called()
    err = capsys.readouterr().err
    assert "has no alembic" in err
    assert "sudo sysmanage-migrate" in err
    assert ".venv/bin/python" in err


def test_the_venv_interpreter_passes_the_check():
    assert _load()._wrong_interpreter() == ""
