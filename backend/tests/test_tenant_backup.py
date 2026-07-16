# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 13.1.F — OSS backup orchestration helpers (``tenant_backup``).

The engine runs the actual per-tenant backup commands; the pure schedule math,
config reading, and command templating live here so they are unit-testable
without the licensed engine or a live PostgreSQL.
"""

from datetime import datetime, timedelta

from backend.services import tenant_backup as tb

# --- rpo_status ----------------------------------------------------------------

NOW = datetime(2026, 6, 25, 12, 0, 0)


def test_rpo_status_unknown_without_target():
    assert tb.rpo_status(None, NOW, NOW) == tb.RPO_UNKNOWN
    assert tb.rpo_status(0, NOW, NOW) == tb.RPO_UNKNOWN


def test_rpo_status_breached_when_never_backed_up():
    assert tb.rpo_status(3600, None, NOW) == tb.RPO_BREACHED


def test_rpo_status_compliant_when_fresh():
    last = NOW - timedelta(seconds=600)  # well inside a 1h target
    assert tb.rpo_status(3600, last, NOW) == tb.RPO_COMPLIANT


def test_rpo_status_at_risk_near_target():
    last = NOW - timedelta(seconds=3000)  # 83% of a 1h target
    assert tb.rpo_status(3600, last, NOW) == tb.RPO_AT_RISK


def test_rpo_status_breached_when_stale():
    last = NOW - timedelta(seconds=4000)  # past a 1h target
    assert tb.rpo_status(3600, last, NOW) == tb.RPO_BREACHED


# --- get_backup_config ---------------------------------------------------------


def test_get_backup_config_disabled_when_no_command(monkeypatch):
    monkeypatch.setattr(tb.app_config, "config", {}, raising=False)
    cfg = tb.get_backup_config()
    assert cfg.enabled is False
    assert cfg.default_rpo_seconds == tb.DEFAULT_RPO_SECONDS


def test_get_backup_config_reads_section(monkeypatch):
    monkeypatch.setattr(
        tb.app_config,
        "config",
        {
            "backup": {
                "command": "pgbackrest --stanza={slug} backup",
                "verify_command": "pgbackrest --stanza={slug} verify",
                "default_rpo_seconds": "7200",
                "tick_interval_seconds": 60,
            }
        },
        raising=False,
    )
    cfg = tb.get_backup_config()
    assert cfg.enabled is True
    assert cfg.default_rpo_seconds == 7200  # coerced from str
    assert cfg.tick_interval_seconds == 60
    assert cfg.full_verify_interval_seconds == tb.DEFAULT_FULL_VERIFY_INTERVAL


def test_get_backup_config_tolerates_bad_ints(monkeypatch):
    monkeypatch.setattr(
        tb.app_config,
        "config",
        {"backup": {"command": "x", "default_rpo_seconds": "not-a-number"}},
        raising=False,
    )
    assert tb.get_backup_config().default_rpo_seconds == tb.DEFAULT_RPO_SECONDS


# --- render_backup_command -----------------------------------------------------


def test_render_substitutes_whitelisted_keys():
    argv = tb.render_backup_command(
        "pg_dump -h {host} -p {port} -d {dbname} -f /b/{slug}.dump",
        {"host": "db1", "port": 5432, "dbname": "tenant_acme", "slug": "acme"},
    )
    assert argv == [
        "pg_dump",
        "-h",
        "db1",
        "-p",
        "5432",
        "-d",
        "tenant_acme",
        "-f",
        "/b/acme.dump",
    ]


def test_render_leaves_unknown_placeholders_literal():
    # A typo'd placeholder isn't substituted (and doesn't raise) — it surfaces at
    # exec time rather than crashing the orchestrator tick.
    argv = tb.render_backup_command("backup {bogus}", {})
    assert argv == ["backup", "{bogus}"]


def test_render_no_shell_interpretation():
    # Values are not shell-interpreted: a malicious-looking dbname is a single arg.
    argv = tb.render_backup_command("pg_dump -d {dbname}", {"dbname": "a; rm -rf /"})
    assert argv == ["pg_dump", "-d", "a; rm -rf /"]


# --- tenant_rpo_seconds --------------------------------------------------------


def test_tenant_rpo_seconds_disabled(monkeypatch):
    monkeypatch.setattr(tb, "get_tenant_setting", lambda t, k, default=None: False)
    assert tb.tenant_rpo_seconds("t1") is None


def test_tenant_rpo_seconds_falls_back_to_default(monkeypatch):
    def fake_get(tenant_id, key, default=None):
        if key == tb.SETTING_ENABLED:
            return True
        return default  # no explicit RPO set

    monkeypatch.setattr(tb, "get_tenant_setting", fake_get)
    monkeypatch.setattr(
        tb, "get_backup_config", lambda: tb.BackupConfig("x", None, None, 999, 1, 1)
    )
    assert tb.tenant_rpo_seconds("t1") == 999


def test_tenant_rpo_seconds_explicit(monkeypatch):
    def fake_get(tenant_id, key, default=None):
        return True if key == tb.SETTING_ENABLED else 1800

    monkeypatch.setattr(tb, "get_tenant_setting", fake_get)
    assert tb.tenant_rpo_seconds("t1") == 1800
