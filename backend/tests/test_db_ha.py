# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 15.1: the bootstrap engine must be built HA-ready (pre-ping/recycle)."""

from sqlalchemy import create_engine

from backend.persistence import db


def test_ha_engine_kwargs_enable_pre_ping_and_recycle():
    assert db.HA_ENGINE_KWARGS["pool_pre_ping"] is True
    assert db.HA_ENGINE_KWARGS["pool_recycle"] > 0


def test_ha_kwargs_produce_a_pre_ping_engine():
    # Applying the kwargs to any engine must turn pre-ping on (guards against a
    # future refactor silently dropping them from the bootstrap engine).
    engine = create_engine("sqlite://", **db.HA_ENGINE_KWARGS)
    assert engine.pool._pre_ping is True  # pylint: disable=protected-access


def test_db_options_appended_for_multihost_dsn():
    # Phase 15.1: database.options (e.g. target_session_attrs) must reach the
    # DSN so a multi-host host list pins to the writable primary.
    base = "postgresql://u:p@h1,h2:5432/db"
    out = db._apply_db_options(base, "target_session_attrs=read-write")
    assert out == base + "?target_session_attrs=read-write"
    # And it composes with client_encoding via _psycopg_url (uses & separator).
    full = db._psycopg_url(out)
    assert full.startswith("postgresql+psycopg://")
    assert "target_session_attrs=read-write" in full
    assert "client_encoding=utf8" in full


def test_db_options_noop_when_absent():
    base = "postgresql://u:p@h:5432/db"
    assert db._apply_db_options(base, None) == base
    assert db._apply_db_options(base, "") == base
