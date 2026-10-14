# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The hardware tick (Phase 23.1 S6): every host database, one failure
never stops the others, and nothing starts unlicensed."""

from unittest.mock import MagicMock, patch

from backend.services import hardware_tick


def test_every_database_and_a_failure_is_contained():
    good, bad = MagicMock(), MagicMock()
    databases = [("bootstrap", None, good), ("tenant a", "t1", bad)]

    def reconcile(db, tenant_id, _label):
        if db is bad:
            raise RuntimeError("tenant database down")
        assert tenant_id is None
        return 2

    with patch.object(
        hardware_tick, "iter_host_databases", return_value=iter(databases)
    ), patch.object(
        hardware_tick.smartmontools_install, "reconcile", side_effect=reconcile
    ):
        assert hardware_tick.run_one_tick() == 2
    good.commit.assert_called_once()
    bad.rollback.assert_called_once()
    assert good.close.called and bad.close.called


def test_not_started_unlicensed():
    with patch.object(
        hardware_tick.smartmontools_install, "licensed", return_value=False
    ):
        assert hardware_tick.start_if_licensed() is None
