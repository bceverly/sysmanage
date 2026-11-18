# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""PostgreSQL connections SysManage does not own (2026-11-17).

On the dev server the workers' pools plus OpenBAO's took every connection
PostgreSQL allows, and nothing else could connect.  Two causes: the pool
budget left PostgreSQL's own reserved slots and OpenBAO's pools out of its
reserve, and a stopped worker never revoked its OpenBAO database leases (76
live where 12 were in use).
"""

# pylint: disable=protected-access

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine

from backend.multitenancy import bridge, seam
from backend.persistence import pool_sizing as ps


def _pool():
    return {"size": 20, "max_overflow": 30, "timeout": 30, "recycle": 1800,
            "tenant_size": 2, "tenant_max_overflow": 6}  # fmt: skip


# -- the budget ---------------------------------------------------------------


def test_held_back_connections_shrink_each_workers_share():
    _, before = ps.fit(_pool(), 200, 6, tenants=2)
    _, after = ps.fit(_pool(), 200, 6, tenants=2, held_back=11)
    assert "10 reserved, each worker may use 31" in before
    assert "21 reserved, each worker may use 29" in after


def test_held_back_counts_openbao_per_tenant_without_postgres():
    sqlite = create_engine("sqlite://")
    assert ps.held_back(sqlite, 0) == 0
    assert ps.held_back(sqlite, 3) == 3 * ps.OPENBAO_CONNECTIONS_PER_TENANT


def _postgres(values):
    """A PostgreSQL engine double answering SHOW queries from ``values``;
    a missing setting raises, as on PostgreSQL before 16."""
    engine = MagicMock()
    engine.dialect.name = "postgresql"

    def execute(query):
        name = str(query).split()[-1]
        if name not in values:
            raise RuntimeError(f"unrecognized configuration parameter {name}")
        return SimpleNamespace(scalar=lambda: values[name])

    conn = MagicMock()
    conn.execute.side_effect = execute
    engine.connect.return_value.__enter__.return_value = conn
    return engine


def test_postgres_reserved_slots_are_held_back():
    engine = _postgres({"superuser_reserved_connections": "3",
                        "reserved_connections": "2"})  # fmt: skip
    assert ps.held_back(engine, 2) == 3 + 2 + 2 * ps.OPENBAO_CONNECTIONS_PER_TENANT


def test_before_postgres_16_only_the_superuser_slots_count():
    engine = _postgres({"superuser_reserved_connections": "3"})
    assert ps.held_back(engine, 0) == 3


# -- leases released at shutdown -------------------------------------------------


def test_shutdown_revokes_the_engines_leases():
    manager = MagicMock()
    manager._entries = {"tenant-a": object(), "tenant-b": object()}
    module = SimpleNamespace(get_manager=lambda: manager)
    with patch.object(seam, "engine_module", return_value=module):
        assert bridge.release_tenant_engines() == 2
    manager.shutdown.assert_called_once()


def test_without_the_engine_shutdown_releases_nothing():
    with patch.object(seam, "engine_module", return_value=None):
        assert bridge.release_tenant_engines() == 0
    older = SimpleNamespace()  # an engine without get_manager
    with patch.object(seam, "engine_module", return_value=older):
        assert bridge.release_tenant_engines() == 0


def test_a_failing_release_never_stops_shutdown():
    manager = MagicMock()
    manager.shutdown.side_effect = RuntimeError("vault down")
    module = SimpleNamespace(get_manager=lambda: manager)
    with patch.object(seam, "engine_module", return_value=module):
        assert bridge.release_tenant_engines() == 0


def test_the_lifespan_releases_leases_after_its_tasks_stop():
    source = (
        Path(__file__).resolve().parents[1] / "backend/startup/lifecycle.py"
    ).read_text()
    shutdown = source[source.index("=== FASTAPI LIFESPAN SHUTDOWN BEGIN ===") :]
    assert shutdown.index("leadership.stop()") < shutdown.index(
        "bridge.release_tenant_engines()"
    )


# -- install time: the max_connections to set ----------------------------------


import pytest  # noqa: E402


@pytest.mark.parametrize("tenants", [0, 1, 2, 6, 20])
@pytest.mark.parametrize("workers", [1, 6, 16])
@pytest.mark.parametrize("size", [10, 24, 40])
def test_needed_max_connections_is_exactly_what_fit_accepts(tenants, workers, size):
    pool = dict(_pool(), size=size, max_overflow=size)
    needed = ps.needed_max_connections(pool, workers, tenants)
    held = ps.POSTGRES_SUPERUSER_SLOTS + ps.OPENBAO_CONNECTIONS_PER_TENANT * tenants
    assert ps.fit(pool, needed, workers, tenants, held_back=held) == (pool, None)
    _shrunk, reason = ps.fit(pool, needed - workers, workers, tenants, held_back=held)
    # One connection per worker fewer is too few: the server warns (and trims
    # the main pool or the tenant pools' share).
    assert reason


def test_the_installer_prints_the_number(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "machine_capacity", lambda: (8, 32.0))
    monkeypatch.setattr(ps, "resolve_config_target", lambda path: path)
    config = tmp_path / "sysmanage.yaml"
    config.write_text("api:\n  port: 8080\n")
    out = ps.apply_to_file(str(config))
    pool = ps.recommend(8, 32.0)
    needed = ps.needed_max_connections(pool, ps._install_workers(8, 32.0))
    assert f"max_connections to at least {needed}" in out
    assert f"at least {needed}" in config.read_text()  # and in the YAML comment


def test_print_sizes_for_tenant_databases(capsys, monkeypatch):
    monkeypatch.setattr(ps, "machine_capacity", lambda: (8, 32.0))
    assert ps.main(["--print", "--tenants", "2"]) == 0
    pool = ps.recommend(8, 32.0)
    needed = ps.needed_max_connections(pool, ps._install_workers(8, 32.0), 2)
    assert f"at least {needed}" in capsys.readouterr().out.replace("\n# ", " ")
