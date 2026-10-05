# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2 (pulled forward): database pool sizing.

The scale-harness baseline stalled at every size from 50 agents because the
pool was SQLAlchemy's default everywhere and agent connections pinned it.
These pin the sizing rules, the startup fit against PostgreSQL and the
install-time write that must never touch an administrator's own settings.
"""

from unittest.mock import patch

import pytest
import yaml

from backend.persistence import pool_sizing as ps


def test_scales_with_cpus_within_bounds():
    assert ps.recommend(1, 64)["size"] == ps.MIN_SIZE
    assert ps.recommend(8, 64)["size"] == 24
    assert ps.recommend(64, 256)["size"] == ps.MAX_SIZE
    assert ps.recommend(8, 64)["max_overflow"] == 24


def test_a_small_machine_is_capped_by_its_memory():
    """A 1 GB droplet shares RAM with PostgreSQL: ~25 connections total."""
    pool = ps.recommend(4, 1.0)
    assert pool["size"] + pool["max_overflow"] <= 25
    assert pool["size"] >= ps.MIN_SIZE // 2


def test_unknown_memory_does_not_cap():
    assert ps.recommend(8, None)["max_overflow"] == 24


def test_configured_keys_win_and_bad_ones_fall_back():
    with patch.object(ps, "machine_capacity", return_value=(8, 32.0)):
        pool = ps.settings({"database_pool": {"size": 50, "max_overflow": "lots"}})
    assert pool["size"] == 50
    assert pool["max_overflow"] == 24  # unusable value -> computed
    assert pool["timeout"] == ps.DEFAULT_TIMEOUT


def test_a_non_mapping_block_is_ignored():
    with patch.object(ps, "machine_capacity", return_value=(8, 32.0)):
        assert ps.settings({"database_pool": "big"})["size"] == 24


def test_fit_leaves_a_pool_that_fits_alone():
    pool = ps.recommend(8, 32.0)
    assert ps.fit(pool, 200, 1) == (pool, None)


def test_fit_trims_overflow_first_then_size():
    pool = {"size": 24, "max_overflow": 24, "timeout": 30, "recycle": 1800,
            "tenant_size": 2, "tenant_max_overflow": 6}  # fmt: skip
    fitted, reason = ps.fit(pool, 100, 2)  # 45 per worker
    assert (fitted["size"], fitted["max_overflow"]) == (24, 21)
    assert "max_connections is 100" in reason
    fitted, _ = ps.fit(pool, 30, 2)  # 10 per worker
    assert (fitted["size"], fitted["max_overflow"]) == (10, 0)


def test_apply_appends_once_and_keeps_the_file(tmp_path):
    config = tmp_path / "sysmanage.yaml"
    config.write_text("# my notes\napi:\n  port: 8080\n", encoding="utf-8")
    message = ps.apply_to_file(str(config))
    text = config.read_text(encoding="utf-8")
    assert "added database_pool" in message
    assert text.startswith("# my notes\napi:\n  port: 8080\n")
    parsed = yaml.safe_load(text)
    assert parsed["api"]["port"] == 8080
    assert parsed["database_pool"]["size"] >= ps.MIN_SIZE // 2
    # Never twice, and never over an administrator's own block.
    assert "left unchanged" in ps.apply_to_file(str(config))
    assert config.read_text(encoding="utf-8") == text


def test_apply_respects_an_existing_block(tmp_path):
    config = tmp_path / "sysmanage.yaml"
    config.write_text("database_pool:\n  size: 7\n", encoding="utf-8")
    ps.apply_to_file(str(config))
    assert yaml.safe_load(config.read_text(encoding="utf-8")) == {
        "database_pool": {"size": 7}
    }


def test_tenant_engine_kwargs_use_the_tenant_keys():
    with patch.object(ps, "machine_capacity", return_value=(8, 32.0)):
        kwargs = ps.tenant_engine_kwargs({"database_pool": {"tenant_size": 4}})
    assert kwargs == {"pool_size": 4, "max_overflow": 6, "pool_timeout": 30}


def test_the_cli_prints_valid_yaml(capsys):
    assert ps.main(["--print"]) == 0
    assert "size" in yaml.safe_load(capsys.readouterr().out)["database_pool"]


# -- tenant databases share the server (2026-10-05) ------------------------------


@pytest.fixture(autouse=True)
def _no_tenant_budget():
    ps.set_tenant_budget(None)
    yield
    ps.set_tenant_budget(None)


def _pool(size=32, overflow=32):
    return {"size": size, "max_overflow": overflow, "timeout": 30, "recycle": 1800,
            "tenant_size": 2, "tenant_max_overflow": 6}  # fmt: skip


def test_tenant_pools_count_against_the_server():
    """The t14 storm: 8 workers, 20 tenants, max_connections 500 -- the old
    check fitted the bootstrap pool alone and planned ~1,500 connections."""
    fitted, reason = ps.fit(_pool(), 500, 8, tenants=20)
    allowed = (500 - ps.RESERVED_CONNECTIONS) // 8
    bootstrap = fitted["size"] + fitted["max_overflow"]
    assert bootstrap <= allowed * ps.BOOTSTRAP_SHARE_WITH_TENANTS + 1
    assert (
        bootstrap + ps._tenant_budget["per_worker"] <= allowed
    )  # pylint: disable=protected-access
    assert "20 tenant database(s)" in reason
    with patch.object(ps, "tenant_count", return_value=20), patch.object(
        ps, "machine_capacity", return_value=(12, 29.0)
    ):
        kwargs = ps.tenant_engine_kwargs({})
    total = 8 * (bootstrap + 20 * (kwargs["pool_size"] + kwargs["max_overflow"]))
    assert total <= 500 - ps.RESERVED_CONNECTIONS
    assert kwargs["pool_size"] >= 1


def test_tenants_added_after_startup_still_fit():
    ps.fit(_pool(10, 10), 1000, 2, tenants=1)  # fits: room is recorded
    budget = ps._tenant_budget["per_worker"]  # pylint: disable=protected-access
    assert budget == (1000 - ps.RESERVED_CONNECTIONS) // 2 - 20
    with patch.object(ps, "machine_capacity", return_value=(4, 8.0)):
        with patch.object(ps, "tenant_count", return_value=1):
            assert ps.tenant_engine_kwargs({})["pool_size"] == 2  # configured
        with patch.object(ps, "tenant_count", return_value=200):
            kwargs = ps.tenant_engine_kwargs({})
    assert 200 * (kwargs["pool_size"] + kwargs["max_overflow"]) <= budget
    assert (kwargs["pool_size"], kwargs["max_overflow"]) == (2, 0)  # 475 // 200


def test_every_tenant_keeps_at_least_one_connection():
    ps.fit(_pool(), 60, 4, tenants=50)
    with patch.object(ps, "tenant_count", return_value=50), patch.object(
        ps, "machine_capacity", return_value=(4, 8.0)
    ):
        kwargs = ps.tenant_engine_kwargs({})
    assert kwargs["pool_size"] == 1 and kwargs["max_overflow"] == 0


def test_single_tenant_servers_are_unchanged():
    pool = _pool(10, 10)
    assert ps.fit(pool, 200, 1) == (pool, None)
    assert ps._tenant_budget["per_worker"] is None  # pylint: disable=protected-access


def test_tenant_count_is_zero_without_a_registry():
    from sqlalchemy import create_engine  # pylint: disable=import-outside-toplevel

    engine = create_engine("sqlite://")
    try:
        assert ps.tenant_count(engine) == 0
    finally:
        engine.dispose()


def test_a_server_started_before_its_tenants_leaves_them_room():
    """2026-10-05 on t14: the server started with 1 tenant, kept 46 of each
    worker's 54 connections, and the 20 tenants added next got 1 each."""
    ps.fit(_pool(), 500, 9, tenants=1)
    allowed = (500 - ps.RESERVED_CONNECTIONS) // 9
    budget = ps._tenant_budget["per_worker"]  # pylint: disable=protected-access
    assert budget >= allowed // 2
    # With a database sized for 20 tenants the configured pools fit as is.
    ps.fit(_pool(), 3000, 9, tenants=1)
    with patch.object(ps, "tenant_count", return_value=20), patch.object(
        ps, "machine_capacity", return_value=(12, 29.0)
    ):
        assert ps.tenant_engine_kwargs({}) == {
            "pool_size": 2,
            "max_overflow": 6,
            "pool_timeout": 30,
        }
