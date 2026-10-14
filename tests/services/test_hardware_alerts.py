# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Hardware alerts on arrival (Phase 23.1 S5): the handler hands a host whose
report changed something to the alerting engine at once -- and never fails
the report when the engine is absent or broken."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from backend.services import hardware_alerts


class _Engine:
    def __init__(self, fired=1, error=None):
        self.calls, self.fired, self.error = [], fired, error

    def evaluate_host_now(self, session, host_id, conditions):
        self.calls.append((host_id, conditions))
        if self.error:
            raise self.error
        return self.fired


def _run(session, events, engine):
    host = SimpleNamespace(id="h1", fqdn="freebsd.lab")
    with patch.object(hardware_alerts.module_loader, "get_module", return_value=engine):
        asyncio.run(hardware_alerts.on_report(session, host, events))


def test_a_change_is_evaluated_at_once(session):
    engine = _Engine()
    _run(session, ["an event"], engine)
    assert engine.calls == [("h1", ("hardware_health",))]


def test_nothing_changed_nothing_evaluated(session):
    engine = _Engine()
    _run(session, [], engine)
    assert not engine.calls


def test_no_engine_or_a_broken_one_is_quiet(session):
    _run(session, ["an event"], None)  # no Pro+ engine loaded
    engine = _Engine(error=RuntimeError("kaboom"))
    _run(session, ["an event"], engine)  # logged, not raised
    assert engine.calls == [("h1", ("hardware_health",))]
