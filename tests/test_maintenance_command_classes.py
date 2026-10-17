# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Every command the server sends is classified: held by a maintenance
window (it changes the host) or exempt (it only reads or reports).  A new
command in neither list fails here instead of silently defaulting."""

import json
import re
from pathlib import Path

import pytest

from backend.services.maintenance_command_classes import (
    WINDOW_EXEMPT_COMMANDS,
    WINDOW_GATED_COMMANDS,
    is_window_gated,
)
from backend.websocket.messages import CommandType

BACKEND = Path(__file__).resolve().parents[1] / "backend"
# The shapes the server uses to name a command it enqueues.
_LITERAL = re.compile(
    r'"command_type"\s*:\s*"([a-z_0-9]+)"'
    r'|command_type\s*=\s*"([a-z_0-9]+)"'
    r'|create_command_message\(\s*"([a-z_0-9]+)"'
)


def _sent_literals():
    found = set()
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts:
            continue
        for match in _LITERAL.finditer(path.read_text(encoding="utf-8")):
            found.add(next(group for group in match.groups() if group))
    return found


def _command(command_type, **parameters):
    return json.dumps(
        {"data": {"command_type": command_type, "parameters": parameters}}
    )


def test_no_command_is_both():
    assert not WINDOW_EXEMPT_COMMANDS & WINDOW_GATED_COMMANDS


def test_every_command_type_is_classified():
    every = {member.value for member in CommandType}
    unclassified = every - WINDOW_EXEMPT_COMMANDS - WINDOW_GATED_COMMANDS
    assert not unclassified, (
        f"classify {sorted(unclassified)} in maintenance_command_classes: "
        "does it change the host (gated) or only read/report (exempt)?"
    )


def test_every_command_the_server_names_is_classified():
    unclassified = _sent_literals() - WINDOW_EXEMPT_COMMANDS - WINDOW_GATED_COMMANDS
    assert not unclassified, f"classify {sorted(unclassified)}"


@pytest.mark.parametrize(
    "command_type",
    ["run_query_pack", "collect_available_packages", "configure_network_discovery"],
)
def test_the_reads_production_held_are_exempt(command_type):
    assert not is_window_gated("command", _command(command_type))


@pytest.mark.parametrize(
    "command_type",
    ["apply_updates", "reboot_system", "execute_script", "ubuntu_pro_attach"],
)
def test_changes_are_held(command_type):
    assert is_window_gated("command", _command(command_type))


def test_an_unknown_or_unreadable_command_is_held():
    assert is_window_gated("command", _command("brand_new_command"))
    assert is_window_gated("command", "not json")
    assert is_window_gated("command", None)


def test_a_check_mode_config_run_is_a_read():
    assert not is_window_gated(
        "command", _command("apply_config_profile", check_mode=True)
    )
    assert is_window_gated(
        "command", _command("apply_config_profile", check_mode=False)
    )


def test_update_requests_are_held_and_control_pushes_are_not():
    assert is_window_gated("update_request", "{}")
    assert not is_window_gated("logging_config_update", "{}")
    assert not is_window_gated("host_approved", "{}")
