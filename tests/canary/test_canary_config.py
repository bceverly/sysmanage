# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.9: the canary's configuration is checked as a whole -- every
problem listed, a bad file never half-applied."""

import copy
import os
import sys

import pytest
import yaml

from sysmanage_canary import config as cfg

EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "..", "canary",
                       "sysmanage-canary.yaml.example")  # fmt: skip


def _example():
    with open(EXAMPLE, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _problems(raw):
    with pytest.raises(cfg.ConfigError) as caught:
        cfg.validate(raw)
    return caught.value.problems


def test_the_shipped_example_is_valid():
    config = cfg.validate(_example())
    assert all(config["checks"][n]["enabled"] for n in cfg.CHECKS)


def test_defaults_fill_what_is_left_out():
    raw = {"email": {"host": "h", "from": "a@b", "to": ["c@d"]},
           "checks": {"backend": {"enabled": True, "url": "https://x/api/health"}}}  # fmt: skip
    config = cfg.validate(raw)
    backend = config["checks"]["backend"]
    assert backend["interval_seconds"] == 60 and backend["failures_before_alert"] == 3
    assert config["email"]["port"] == 587 and config["language"] == "en"
    assert config["checks"]["database"]["enabled"] is False


def test_every_problem_is_listed_at_once():
    raw = _example()
    raw["typo_section"] = 1
    raw["email"]["port"] = "587"  # a string
    raw["checks"]["backend"]["intervall_seconds"] = 60  # misspelled
    del raw["checks"]["web_ui"]["url"]
    problems = _problems(raw)
    assert "typo_section: unknown setting" in problems
    assert any(p.startswith("email.port: must be int") for p in problems)
    assert "checks.backend.intervall_seconds: unknown setting" in problems
    assert "checks.web_ui.url: required" in problems


def test_a_boolean_is_not_a_number():
    raw = _example()
    raw["checks"]["backend"]["timeout_seconds"] = True
    assert any("timeout_seconds: must be int" in p for p in _problems(raw))


def test_a_disabled_check_needs_none_of_its_fields():
    raw = _example()
    raw["checks"]["database"] = {"enabled": False}
    raw["checks"]["inbound_silence"]["dsn"] = "postgresql://x/y"
    assert cfg.validate(raw)["checks"]["database"]["enabled"] is False


@pytest.mark.parametrize("path, value, message", [
    (("email", "security"), "ssl", "email.security"),
    (("email", "port"), 70000, "email.port"),
    (("heartbeat", "daily_email_hour"), 24, "daily_email_hour"),
    (("checks", "backend", "interval_seconds"), 5, "interval_seconds: at least 10"),
    (("checks", "backend", "timeout_seconds"), 0, "timeout_seconds: must be 1-300"),
    (("checks", "network", "connect"), ["no-port-here"], "is not host:port"),
])  # fmt: skip
def test_out_of_range_values_are_refused(path, value, message):
    raw = _example()
    node = raw
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    assert any(message in p for p in _problems(raw))


def test_at_least_one_check_must_be_on():
    raw = _example()
    for check in raw["checks"].values():
        check["enabled"] = False
    assert "checks: enable at least one check" in _problems(raw)


def test_silence_needs_a_database():
    raw = _example()
    raw["checks"]["database"] = {"enabled": False}
    assert any("inbound_silence.dsn" in p for p in _problems(raw))


def test_unreadable_and_invalid_files(tmp_path):
    with pytest.raises(cfg.ConfigError) as missing:
        cfg.load(str(tmp_path / "absent.yaml"))
    assert "cannot read" in missing.value.problems[0]
    bad = tmp_path / "bad.yaml"
    bad.write_text("email: [unclosed", encoding="utf-8")
    with pytest.raises(cfg.ConfigError) as invalid:
        cfg.load(str(bad))
    assert "not valid YAML" in invalid.value.problems[0]


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX mode bits; on Windows the MSI sets the ACL and the check is off",
)
def test_a_world_readable_file_is_warned_about(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("x: 1", encoding="utf-8")
    os.chmod(path, 0o644)
    assert "0600" in cfg.permission_warning(str(path))
    os.chmod(path, 0o600)
    assert cfg.permission_warning(str(path)) is None


def test_host_port_parsing():
    assert cfg.host_port("license.sysmanage.org:443") == ("license.sysmanage.org", 443)
    assert cfg.host_port("[2001:db8::1]:53") == ("2001:db8::1", 53)
    with pytest.raises(ValueError):
        cfg.host_port("nope")
    assert copy.deepcopy(cfg.CHECKS) == cfg.CHECKS
