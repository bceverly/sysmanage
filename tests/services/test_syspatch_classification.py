# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""OpenBSD syspatches are classified from the errata catalog, not guessed.

The agent labeled every syspatch "security"; on OpenBSD 7.8 that was wrong
for 27 of 57 errata. Now a security erratum is ``security`` and anything else
is ``system`` -- never a guess in either direction.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.services import syspatch_classification as sc

UPDATES = [
    {"package_name": "001_xserver", "package_manager": "syspatch"},
    {"package_name": "002_kernel", "package_manager": "syspatch"},
    {"package_name": "curl", "package_manager": "pkg"},
]


def _db(release="7.9"):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        platform_release=release
    )
    return db


def _shared(rows):
    @contextmanager
    def _session(_partition):
        session = MagicMock()
        chain = session.query.return_value.join.return_value.filter.return_value
        chain.all.return_value = rows
        yield session

    return _session


def test_security_errata_are_security_and_the_rest_are_system():
    with patch.object(sc, "partition_session", _shared([("001_xserver",)])):
        types = sc.syspatch_update_types(_db(), "h", UPDATES)
    assert types == {"001_xserver": "security", "002_kernel": "system"}


def test_non_syspatch_rows_are_untouched():
    with patch.object(sc, "partition_session", _shared([])):
        types = sc.syspatch_update_types(_db(), "h", UPDATES)
    assert "curl" not in types


def test_no_catalog_means_system_not_security():
    @contextmanager
    def _broken(_partition):
        raise RuntimeError("no shared_advisory table")
        yield  # pragma: no cover

    with patch.object(sc, "partition_session", _broken):
        types = sc.syspatch_update_types(_db(), "h", UPDATES)
    assert types == {"001_xserver": "system", "002_kernel": "system"}


def test_an_unknown_release_is_not_looked_up():
    with patch.object(sc, "partition_session") as session:
        types = sc.syspatch_update_types(_db(release=None), "h", UPDATES)
    session.assert_not_called()
    assert set(types.values()) == {"system"}


def test_no_syspatches_means_no_query():
    db = _db()
    assert sc.syspatch_update_types(db, "h", [UPDATES[2]]) == {}
    db.query.assert_not_called()


def test_the_handler_rows_are_classified_in_place():
    rows = [dict(u, is_security_update=True) for u in UPDATES]
    with patch.object(sc, "partition_session", _shared([("001_xserver",)])):
        sc.classify_syspatch_updates(_db(), "h", rows)
    by_name = {r["package_name"]: r for r in rows}
    assert by_name["001_xserver"]["is_security_update"] is True
    assert (
        by_name["002_kernel"]["is_security_update"] is False
    )  # the agent's guess, corrected
    assert by_name["curl"]["is_security_update"] is True  # not a syspatch: untouched
