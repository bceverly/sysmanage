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


def test_detect_firewall_flavor_unknown_linux_distro_defaults_to_ufw():
    """A Linux host whose release string isn't ubuntu/debian/rhel-family
    should still get a runnable plan (ufw)."""
    assert detect_firewall_flavor("Linux", "Gentoo 23") == "ufw"
    assert detect_firewall_flavor("Linux", "") == "ufw"


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


# ---------------------------------------------------------------------------
# Phase 4: extra coverage on disable / restart / role-removal edge cases
# ---------------------------------------------------------------------------


def test_firewalld_disable_stops_and_disables_service():
    plan = build_disable_plan({"platform": "Linux", "platform_release": "Rocky 9"})
    assert plan["flavor"] == "firewalld"
    actions = [(a["service"], a["action"]) for a in plan["service_actions"]]
    assert ("firewalld", "stop") in actions
    assert ("firewalld", "disable") in actions


def test_firewalld_restart_emits_reload_then_service_restart():
    plan = build_restart_plan({"platform": "Linux", "platform_release": "Fedora 41"})
    assert plan["commands"][0]["argv"] == ["firewall-cmd", "--reload"]
    assert {"service": "firewalld", "action": "restart"} in plan["service_actions"]


def test_pf_disable_stops_and_disables():
    plan = build_disable_plan({"platform": "OpenBSD"})
    assert plan["flavor"] == "pf"
    assert plan["commands"][0]["argv"] == ["pfctl", "-d"]
    actions = [(a["service"], a["action"]) for a in plan["service_actions"]]
    assert ("pf", "stop") in actions
    assert ("pf", "disable") in actions


def test_pf_restart_toggles_off_then_on():
    plan = build_restart_plan({"platform": "FreeBSD"})
    argvs = [c["argv"] for c in plan["commands"]]
    assert ["pfctl", "-d"] in argvs
    assert ["pfctl", "-e"] in argvs


def test_npf_restart_uses_reload():
    plan = build_restart_plan({"platform": "NetBSD"})
    assert plan["commands"][0]["argv"] == ["npfctl", "reload"]


def test_npf_disable_stops_and_disables():
    plan = build_disable_plan({"platform": "NetBSD"})
    actions = [(a["service"], a["action"]) for a in plan["service_actions"]]
    assert ("npf", "stop") in actions
    assert ("npf", "disable") in actions


def test_macos_restart_toggles_global_state_off_then_on():
    plan = build_restart_plan({"platform": "Darwin"})
    cmds = [c["argv"] for c in plan["commands"]]
    assert any(a[-2:] == ["--setglobalstate", "off"] for a in cmds)
    assert any(a[-2:] == ["--setglobalstate", "on"] for a in cmds)


def test_macos_disable_uses_socketfilterfw_off():
    plan = build_disable_plan({"platform": "Darwin"})
    assert plan["commands"][0]["argv"][-2:] == ["--setglobalstate", "off"]


def test_windows_restart_only_uses_service_action():
    # netsh has no atomic restart; we just bounce the MpsSvc service.
    plan = build_restart_plan({"platform": "Windows"})
    assert plan["commands"] == []
    assert {"service": "MpsSvc", "action": "restart"} in plan["service_actions"]


def test_ufw_apply_with_both_tcp_and_udp_emits_two_rules_per_port():
    plan = build_apply_role_ports_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        ipv4_ports=[{"port": 53, "tcp": True, "udp": True}],
        ipv6_ports=[],
    )
    argvs = [c["argv"] for c in plan["commands"]]
    assert ["ufw", "allow", "53/tcp"] in argvs
    assert ["ufw", "allow", "53/udp"] in argvs


def test_ufw_remove_role_ports_skips_dns_dhcp_too():
    # DEFAULT_PRESERVED_PORTS is (22, 53, 67); a request to remove 67 is a no-op.
    plan = build_remove_role_ports_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        ipv4_ports=[{"port": 67, "tcp": True, "udp": True}],
        ipv6_ports=[],
    )
    deletes = [c for c in plan["commands"] if "delete" in c["argv"]]
    assert deletes == []
    assert 67 in plan["skipped_preserved_ports"]


def test_firewalld_apply_role_with_only_udp_does_not_emit_tcp():
    plan = build_apply_role_ports_plan(
        {"platform": "Linux", "platform_release": "Rocky 9"},
        ipv4_ports=[{"port": 514, "tcp": False, "udp": True}],
        ipv6_ports=[],
    )
    add_cmds = [
        c for c in plan["commands"] if any("--add-port=" in a for a in c["argv"])
    ]
    assert len(add_cmds) == 1
    assert "514/udp" in " ".join(add_cmds[0]["argv"])


def test_pf_role_ports_returns_unsupported_note_for_apply_and_remove():
    apply_plan = build_apply_role_ports_plan(
        {"platform": "OpenBSD"},
        ipv4_ports=[{"port": 80, "tcp": True}],
        ipv6_ports=[],
    )
    remove_plan = build_remove_role_ports_plan(
        {"platform": "OpenBSD"},
        ipv4_ports=[{"port": 80, "tcp": True}],
        ipv6_ports=[],
    )
    assert apply_plan["commands"] == [] and "Pro+" in apply_plan["note"]
    assert remove_plan["commands"] == [] and "Pro+" in remove_plan["note"]


def test_npf_role_ports_returns_unsupported_note():
    plan = build_apply_role_ports_plan(
        {"platform": "NetBSD"},
        ipv4_ports=[{"port": 80, "tcp": True}],
        ipv6_ports=[],
    )
    assert plan["commands"] == []
    assert "Pro+" in plan["note"]


def test_unknown_platform_falls_back_to_ufw_for_enable():
    plan = build_enable_plan({"platform": "Plan9", "platform_release": "4ed"})
    assert plan["flavor"] == "ufw"


# Catch ports that are NOT in any preserved set — to make sure removal
# actually emits delete commands when the port isn't preserved.
def test_ufw_remove_role_ports_actually_emits_for_non_preserved():
    plan = build_remove_role_ports_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        ipv4_ports=[
            {"port": 8080, "tcp": True, "udp": False},
            {"port": 8443, "tcp": True, "udp": True},
        ],
        ipv6_ports=[],
    )
    deletes = [c["argv"] for c in plan["commands"] if "delete" in c["argv"]]
    # 8080/tcp + 8443/tcp + 8443/udp = 3 deletes
    assert len(deletes) == 3


# ---------------------------------------------------------------------------
# Coverage of remaining edge branches
# ---------------------------------------------------------------------------


def test_firewalld_remove_role_with_only_udp_emits_one_remove_command():
    """The firewalld remove path has separate tcp / udp branches; the udp arm
    is otherwise only hit when a removal request specifies udp without tcp."""
    plan = build_remove_role_ports_plan(
        {"platform": "Linux", "platform_release": "Rocky 9"},
        ipv4_ports=[{"port": 514, "tcp": False, "udp": True}],
        ipv6_ports=[],
    )
    remove_cmds = [
        c for c in plan["commands"] if any("--remove-port=" in a for a in c["argv"])
    ]
    assert len(remove_cmds) == 1
    assert "514/udp" in " ".join(remove_cmds[0]["argv"])


def test_windows_enable_includes_agent_ports_in_preserved_rules():
    plan = build_enable_plan({"platform": "Windows", "agent_ports": [9443, 9444]})
    # Each preserved port produces a "name=SysManage Preserve {port}/TCP" rule;
    # check both agent ports are reflected.
    rule_names = [
        a for c in plan["commands"] for a in c["argv"] if a.startswith("name=")
    ]
    assert any("9443/TCP" in n for n in rule_names)
    assert any("9444/TCP" in n for n in rule_names)


def test_windows_enable_ignores_non_int_agent_port_entries():
    """The enable plan filters out non-int agent_ports defensively (e.g. if
    a future config schema lets them through as strings)."""
    plan = build_enable_plan(
        {"platform": "Windows", "agent_ports": [9443, "bogus", None]}
    )
    rule_names = [
        a for c in plan["commands"] for a in c["argv"] if a.startswith("name=")
    ]
    # "bogus"/None must NOT appear as preserved ports.
    assert all("bogus" not in n for n in rule_names)
    assert any("9443/TCP" in n for n in rule_names)
