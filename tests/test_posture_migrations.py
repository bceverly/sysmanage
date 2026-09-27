# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""21.4 S2 migrations: shared s17threatq and tenant q11posture, for real.

Runs both chains on scratch SQLite, then checks the tables and a round trip
through the ORM (the models and the migrations must agree), and that each
migration is idempotent.
"""

import contextlib
import os
import sqlite3
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_TENANT_TABLES = {
    "threat_model",
    "posture_item",
    "posture_item_event",
    "posture_waiver",
}


def _alembic(args, db_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = None
    for _attempt in range(4):  # a negative rc is a signal-kill flake
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode >= 0:
            break
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stderr}"


def _tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()


def test_both_chains_create_the_posture_tables_and_the_orm_agrees():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["upgrade", "head"], db)
        tables = _tables(db)
        assert "shared_threat_questionnaire" in tables
        assert _TENANT_TABLES <= tables

        engine = create_engine(f"sqlite:///{db}")
        with sessionmaker(bind=engine)() as s:
            s.add(
                models.SharedThreatQuestionnaire(
                    slug="q",
                    version=1,
                    contract_version=1,
                    definition={},
                    source="engine",
                )
            )
            s.add(
                models.ThreatModel(
                    scope_kind="tenant",
                    scope_ref="",
                    model_version=1,
                    is_current=True,
                    questionnaire_slug="q",
                    questionnaire_version=1,
                    answers={},
                    attributes={},
                    digest="d",
                    complete=True,
                )
            )
            s.add(
                models.PostureItem(
                    rule_source="shared",
                    rule_key="PM-X",
                    state="open",
                    outcome="fires",
                    managed_by="tenant",
                )
            )
            s.add(
                models.PostureItemEvent(
                    rule_key="PM-X", to_state="open", cause="evaluation"
                )
            )
            s.add(
                models.PostureWaiver(
                    rule_key="PM-X", reason="accepted", granted_by="a@b"
                )
            )
            s.commit()
            assert s.query(models.PostureItem).one().scope_ref == ""
        engine.dispose()

        # Idempotent: re-running the migrations over existing tables is a no-op.
        _alembic(["--name", "shared", "stamp", "s16osfeeds"], db)
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["stamp", "q10advisorpack"], db)
        _alembic(["upgrade", "head"], db)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(db)
