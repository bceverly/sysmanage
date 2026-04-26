"""Tests for the open-source firewall plan builder."""

import pytest

from backend.services.firewall_plan_builder import (
    build_apply_role_ports_plan,
    build_deploy_plan,
    build_disable_plan,
    build_enable_plan,
    build_remove_role_ports_plan,
    build_restart_plan,
    detect_firewall_flavor,
)

# ---------------------------------------------------------------------------
# Flavor detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "platform,release,expected",
    [
        ("Linux", "Ubuntu 24.04", "ufw"),
        ("Linux", "Debian 12", "ufw"),
        ("Linux", "Rocky 9", "firewalld"),
        ("Linux", "CentOS Stream 9", "firewalld"),
        ("Linux", "Fedora 41", "firewalld"),
        ("Linux", "AmazonLinux 2023", "firewalld"),
        ("OpenBSD", "7.6", "pf"),
        ("FreeBSD", "14.2", "pf"),
        ("NetBSD", "10.1", "npf"),
        ("Windows", "11", "windows"),
        ("Darwin", "15", "macos"),
    ],
)
def test_detect_firewall_flavor(platform, release, expected):
    assert detect_firewall_flavor(platform, release) == expected


def test_detect_firewall_flavor_unknown_platform_falls_back_to_ufw():
    assert detect_firewall_flavor("Plan9", "4ed") == "ufw"


# ---------------------------------------------------------------------------
# UFW
# ---------------------------------------------------------------------------


def test_ufw_enable_preserves_ssh_and_agent_ports():
    plan = build_enable_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04", "agent_ports": [8443]}
    )
    assert plan["flavor"] == "ufw"
    assert 22 in plan["preserved_ports"]
    assert 8443 in plan["preserved_ports"]
    # Final command turns ufw on.
    assert plan["commands"][-1]["argv"] == ["ufw", "--force", "enable"]
    # service_action enables the unit at boot.
    assert {"service": "ufw", "action": "enable"} in plan["service_actions"]


def test_ufw_disable_emits_disable_and_service_stop():
    plan = build_disable_plan({"platform": "Linux", "platform_release": "Ubuntu 24.04"})
    assert plan["flavor"] == "ufw"
    assert plan["commands"][0]["argv"] == ["ufw", "disable"]
    assert {"service": "ufw", "action": "stop"} in plan["service_actions"]


def test_ufw_restart_reloads():
    plan = build_restart_plan({"platform": "Linux", "platform_release": "Ubuntu 24.04"})
    assert plan["commands"] == [
        {
            "argv": ["ufw", "reload"],
            "sudo": True,
            "timeout": 10,
            "ignore_errors": False,
            "description": "reload ufw",
        }
    ]


def test_ufw_deploy_is_same_as_enable():
    a = build_deploy_plan({"platform": "Linux", "platform_release": "Ubuntu 24.04"})
    b = build_enable_plan({"platform": "Linux", "platform_release": "Ubuntu 24.04"})
    assert a == b


def test_ufw_apply_role_ports_emits_per_proto_allow():
    plan = build_apply_role_ports_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        ipv4_ports=[{"port": 80, "tcp": True, "udp": False}],
        ipv6_ports=[{"port": 53, "tcp": False, "udp": True}],
    )
    argvs = [c["argv"] for c in plan["commands"]]
    assert ["ufw", "allow", "80/tcp"] in argvs
    assert ["ufw", "allow", "53/udp"] in argvs
    assert ["ufw", "reload"] in argvs


def test_ufw_remove_role_ports_skips_preserved():
    plan = build_remove_role_ports_plan(
        {
            "platform": "Linux",
            "platform_release": "Ubuntu 24.04",
            "agent_ports": [8443],
        },
        ipv4_ports=[
            {"port": 22, "tcp": True, "udp": False},
            {"port": 8443, "tcp": True, "udp": False},
            {"port": 9000, "tcp": True, "udp": False},
        ],
        ipv6_ports=[],
    )
    deletes = [c for c in plan["commands"] if "delete" in c["argv"]]
    assert len(deletes) == 1
    assert "9000/tcp" in " ".join(deletes[0]["argv"])
    assert 22 in plan["skipped_preserved_ports"]
    assert 8443 in plan["skipped_preserved_ports"]


# ---------------------------------------------------------------------------
# firewalld
# ---------------------------------------------------------------------------


def test_firewalld_enable_uses_firewall_cmd_and_starts_service():
    plan = build_enable_plan({"platform": "Linux", "platform_release": "Rocky 9"})
    assert plan["flavor"] == "firewalld"
    assert plan["commands"][-1]["argv"] == ["firewall-cmd", "--reload"]
    services = [a for a in plan["service_actions"]]
    assert {"service": "firewalld", "action": "start"} in services


def test_firewalld_apply_role_ports_uses_add_port():
    plan = build_apply_role_ports_plan(
        {"platform": "Linux", "platform_release": "Rocky 9"},
        ipv4_ports=[{"port": 5432, "tcp": True, "udp": False}],
        ipv6_ports=[],
    )
    add_port_cmds = [
        c
        for c in plan["commands"]
        if any("--add-port=5432/tcp" in a for a in c["argv"])
    ]
    assert len(add_port_cmds) == 1


def test_firewalld_remove_role_ports_skips_preserved():
    plan = build_remove_role_ports_plan(
        {"platform": "Linux", "platform_release": "Rocky 9"},
        ipv4_ports=[
            {"port": 22, "tcp": True, "udp": False},
            {"port": 9000, "tcp": True, "udp": False},
        ],
        ipv6_ports=[],
    )
    rm_cmds = [
        c for c in plan["commands"] if any("--remove-port" in a for a in c["argv"])
    ]
    # Only port 9000 removed; 22 is preserved.
    assert len(rm_cmds) == 1
    assert "9000/tcp" in " ".join(rm_cmds[0]["argv"])
    assert 22 in plan["skipped_preserved_ports"]


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------


def test_windows_enable_preserves_rdp_and_ssh():
    plan = build_enable_plan({"platform": "Windows", "platform_release": "11"})
    assert plan["flavor"] == "windows"
    assert 3389 in plan["preserved_ports"]
    assert 22 in plan["preserved_ports"]
    # Last command turns the firewall on.
    assert plan["commands"][-1]["argv"][-3:] == ["allprofiles", "state", "on"]


def test_windows_disable_turns_state_off():
    plan = build_disable_plan({"platform": "Windows"})
    assert plan["commands"][0]["argv"][-3:] == ["allprofiles", "state", "off"]


def test_windows_apply_role_ports_emits_add_rule():
    plan = build_apply_role_ports_plan(
        {"platform": "Windows"},
        ipv4_ports=[{"port": 80, "tcp": True, "udp": False}],
        ipv6_ports=[],
    )
    user_rules = [c for c in plan["commands"] if "localport=80" in c["argv"]]
    assert len(user_rules) == 1
    assert "protocol=TCP" in user_rules[0]["argv"]


def test_windows_remove_role_ports_emits_delete_rule():
    plan = build_remove_role_ports_plan(
        {"platform": "Windows"},
        ipv4_ports=[{"port": 9000, "tcp": True, "udp": False}],
        ipv6_ports=[],
    )
    deletes = [c for c in plan["commands"] if "delete" in c["argv"]]
    assert len(deletes) == 1


# ---------------------------------------------------------------------------
# macOS / BSD
# ---------------------------------------------------------------------------


def test_macos_enable_uses_socketfilterfw():
    plan = build_enable_plan({"platform": "Darwin"})
    assert plan["flavor"] == "macos"
    assert plan["commands"][0]["argv"][-2:] == ["--setglobalstate", "on"]


def test_macos_role_ports_are_a_noop_with_explanatory_note():
    plan = build_apply_role_ports_plan(
        {"platform": "Darwin"},
        ipv4_ports=[{"port": 80, "tcp": True}],
        ipv6_ports=[],
    )
    assert plan["commands"] == []
    assert "Pro+" in plan["note"]


def test_pf_enable_uses_pfctl_e():
    plan = build_enable_plan({"platform": "OpenBSD"})
    assert plan["flavor"] == "pf"
    assert plan["commands"][0]["argv"] == ["pfctl", "-e"]


def test_pf_role_ports_unsupported_in_oss():
    plan = build_apply_role_ports_plan(
        {"platform": "FreeBSD"}, ipv4_ports=[{"port": 80, "tcp": True}], ipv6_ports=[]
    )
    assert plan["commands"] == []
    assert "Pro+" in plan["note"]


def test_npf_enable_uses_npfctl_start():
    plan = build_enable_plan({"platform": "NetBSD"})
    assert plan["commands"][0]["argv"] == ["npfctl", "start"]
