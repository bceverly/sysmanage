# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22: the startup log names the PostgreSQL driver implementation, and
warns about the slow pure-Python one (the BSD default before psycopg-c)."""

import logging
from types import SimpleNamespace
from unittest.mock import patch

from backend.persistence import driver_info


def _engine(dialect):
    return SimpleNamespace(dialect=SimpleNamespace(name=dialect))


def test_the_slow_driver_is_a_warning(caplog):
    with (
        patch.object(driver_info, "psycopg_implementation", return_value="python"),
        caplog.at_level(logging.INFO, logger=driver_info.logger.name),
    ):
        assert driver_info.log_postgres_driver(_engine("postgresql")) == "python"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "psycopg-c" in warnings[0].getMessage()


def test_the_compiled_drivers_are_info(caplog):
    for impl in ("c", "binary"):
        caplog.clear()
        with (
            patch.object(driver_info, "psycopg_implementation", return_value=impl),
            caplog.at_level(logging.INFO, logger=driver_info.logger.name),
        ):
            assert driver_info.log_postgres_driver(_engine("postgresql")) == impl
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert f"{impl} implementation" in caplog.text


def test_sqlite_says_nothing(caplog):
    with caplog.at_level(logging.INFO, logger=driver_info.logger.name):
        assert driver_info.log_postgres_driver(_engine("sqlite")) is None
    assert "PostgreSQL driver" not in caplog.text


def test_the_installed_implementation_is_reported():
    assert driver_info.psycopg_implementation() in ("c", "binary", "python")
