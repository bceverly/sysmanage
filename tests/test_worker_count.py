# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: the server sizes its worker count for the machine it runs on.

One worker uses at most about one core; the count was an environment
variable defaulting to 1, so a stock install used one core however big the
machine.  Now: computed, overridable in sysmanage.yaml, and the environment
variable (CI, the load harness) still wins.
"""

from unittest.mock import patch

import pytest

from backend.startup import workers as w


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv(w.ENV_VAR, raising=False)


@pytest.mark.parametrize("cpus,memory_gb,expected", [
    (1, 1.0, 1), (2, 4.0, 1), (4, 8.0, 3), (8, 16.0, 6), (8, 32.0, 6),
    (16, 64.0, 12), (64, 256.0, 16),
    (8, 4.0, 2),     # memory-bound: a small droplet with many vCPUs
    (8, None, 6),    # memory unknown: CPUs decide
])  # fmt: skip
def test_the_default_follows_the_machine(cpus, memory_gb, expected):
    assert w.recommend(cpus, memory_gb) == expected


def _resolve(config, sqlite=False, cpus=8, memory_gb=32.0):
    with patch.object(
        w.pool_sizing, "machine_capacity", return_value=(cpus, memory_gb)
    ):
        return w.resolve(config, sqlite)


def test_auto_is_the_default():
    assert _resolve({})[0] == 6
    assert _resolve({"api": {"workers": "auto"}})[0] == 6
    assert "auto: 8 CPUs" in _resolve({})[1]


def test_sysmanage_yaml_overrides_the_default():
    assert _resolve({"api": {"workers": 3}}) == (3, "api.workers=3")


def test_the_environment_overrides_sysmanage_yaml(monkeypatch):
    monkeypatch.setenv(w.ENV_VAR, "2")
    assert _resolve({"api": {"workers": 3}})[0] == 2


def test_nonsense_falls_back_to_auto(monkeypatch):
    assert _resolve({"api": {"workers": "lots"}})[0] == 6
    assert _resolve({"api": {"workers": 0}})[0] == 6
    monkeypatch.setenv(w.ENV_VAR, "-1")
    assert _resolve({})[0] == 6


def test_sqlite_always_gets_one():
    count, why = _resolve({"api": {"workers": 4}}, sqlite=True)
    assert count == 1 and "SQLite" in why
    assert _resolve({}, sqlite=True)[0] == 1
