"""
Free-tier (open-source) firewall plan builder.

Generates declarative firewall deployment plans for the 6 basic operations
the open-source server supports: enable, disable, restart, deploy, apply
role ports, remove role ports.

Plans use the same shape that the Pro+ firewall_orchestration_engine emits:
    {
        "flavor": "ufw" | "firewalld" | "pf" | "ipfw" | "npf" | "windows" | "macos",
        "files":            [...],
        "commands":         [...],
        "service_actions":  [...],
        "preserved_ports":  [...],
    }

The agent receives one of these via the generic `apply_deployment_plan`
handler and runs it in order: files → commands → service_actions.

Pro+ licensees get the richer engine in
sysmanage-professional-plus/module-source/firewall_orchestration_engine
which adds source-restricted rules, role assignments, conflict detection
and policy deployment.
"""

from typing import Any, Dict, List, Optional

# Ports that must always remain reachable on a managed host. SSH (22) for
# operator access, DNS (53) and DHCP (67) so containerised hosts keep
# basic networking even after a firewall sync.
DEFAULT_PRESERVED_PORTS = (22, 53, 67)


def detect_firewall_flavor(
    host_platform: Optional[str], host_release: Optional[str]
) -> str:
    """
    Pick the canonical firewall name for a host.

    Returns: ufw | firewalld | pf | ipfw | npf | windows | macos.
    Defaults to ufw for unknown Linux distros so the agent at least gets
    a runnable plan; the operator can override by switching distros.
    """
    plat = (host_platform or "").lower()
    release = (host_release or "").lower()

    if plat == "linux":
        if any(d in release for d in ("ubuntu", "debian")):
            return "ufw"
        if any(
            d in release
            for d in ("rhel", "centos", "fedora", "rocky", "alma", "oracle", "amazon")
        ):
            return "firewalld"
        return "ufw"
    if plat == "openbsd":
        return "pf"
    if plat == "freebsd":
        return "pf"
    if plat == "netbsd":
        return "npf"
    if plat == "windows":
        return "windows"
    if plat in ("darwin", "macos"):
        return "macos"
    # Unknown — fall back to ufw so we still produce a runnable plan.
    return "ufw"


def _preserved_ports(extra: Optional[List[int]] = None) -> List[int]:
    s = set(DEFAULT_PRESERVED_PORTS)
    if extra:
        for p in extra:
            if isinstance(p, int):
                s.add(p)
    return sorted(s)


# ---------------------------------------------------------------------------
# UFW (Ubuntu / Debian)
# ---------------------------------------------------------------------------


def _ufw_enable_plan(agent_ports: Optional[List[int]] = None) -> Dict[str, Any]:
    preserved = _preserved_ports(agent_ports)
    commands = []
    for port in preserved:
        commands.append(
            {
                "argv": ["ufw", "allow", f"{port}/tcp"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": True,
                "description": f"preserve management port {port}/tcp",
            }
        )
    commands.append(
        {
            "argv": ["ufw", "--force", "enable"],
            "sudo": True,
            "timeout": 10,
            "ignore_errors": False,
            "description": "enable ufw",
        }
    )
    return {
        "flavor": "ufw",
        "files": [],
        "commands": commands,
        "service_actions": [{"service": "ufw", "action": "enable"}],
        "preserved_ports": preserved,
    }


def _ufw_disable_plan() -> Dict[str, Any]:
    return {
        "flavor": "ufw",
        "files": [],
        "commands": [
            {
                "argv": ["ufw", "disable"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": False,
                "description": "disable ufw",
            },
        ],
        "service_actions": [{"service": "ufw", "action": "stop"}],
        "preserved_ports": [],
    }


def _ufw_restart_plan() -> Dict[str, Any]:
    return {
        "flavor": "ufw",
        "files": [],
        "commands": [
            {
                "argv": ["ufw", "reload"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": False,
                "description": "reload ufw",
            },
        ],
        "service_actions": [],
        "preserved_ports": [],
    }


def _ufw_apply_role_ports(
    ipv4_ports: List[Dict], ipv6_ports: List[Dict]
) -> Dict[str, Any]:
    commands = []
    for spec in (ipv4_ports or []) + (ipv6_ports or []):
        port = spec.get("port")
        if spec.get("tcp"):
            commands.append(
                {
                    "argv": ["ufw", "allow", f"{port}/tcp"],
                    "sudo": True,
                    "timeout": 10,
                    "ignore_errors": True,
                    "description": f"allow {port}/tcp",
                }
            )
        if spec.get("udp"):
            commands.append(
                {
                    "argv": ["ufw", "allow", f"{port}/udp"],
                    "sudo": True,
                    "timeout": 10,
                    "ignore_errors": True,
                    "description": f"allow {port}/udp",
                }
            )
    commands.append(
        {
            "argv": ["ufw", "reload"],
            "sudo": True,
            "timeout": 10,
            "ignore_errors": True,
            "description": "reload ufw",
        }
    )
    return {
        "flavor": "ufw",
        "files": [],
        "commands": commands,
        "service_actions": [],
        "preserved_ports": [],
    }


def _ufw_remove_role_ports(
    ipv4_ports: List[Dict],
    ipv6_ports: List[Dict],
    agent_ports: Optional[List[int]] = None,
) -> Dict[str, Any]:
    preserved = set(_preserved_ports(agent_ports))
    commands = []
    skipped = []
    for spec in (ipv4_ports or []) + (ipv6_ports or []):
        port = spec.get("port")
        if port in preserved:
            skipped.append(port)
            continue
        if spec.get("tcp"):
            commands.append(
                {
                    "argv": ["ufw", "delete", "allow", f"{port}/tcp"],
                    "sudo": True,
                    "timeout": 10,
                    "ignore_errors": True,
                    "description": f"remove {port}/tcp",
                }
            )
        if spec.get("udp"):
            commands.append(
                {
                    "argv": ["ufw", "delete", "allow", f"{port}/udp"],
                    "sudo": True,
                    "timeout": 10,
                    "ignore_errors": True,
                    "description": f"remove {port}/udp",
                }
            )
    commands.append(
        {
            "argv": ["ufw", "reload"],
            "sudo": True,
            "timeout": 10,
            "ignore_errors": True,
            "description": "reload ufw",
        }
    )
    return {
        "flavor": "ufw",
        "files": [],
        "commands": commands,
        "service_actions": [],
        "skipped_preserved_ports": sorted(set(skipped)),
    }


# ---------------------------------------------------------------------------
# firewalld (RHEL / CentOS / Fedora / Rocky)
# ---------------------------------------------------------------------------


def _firewalld_enable_plan(agent_ports: Optional[List[int]] = None) -> Dict[str, Any]:
    preserved = _preserved_ports(agent_ports)
    commands = []
    for port in preserved:
        commands.append(
            {
                "argv": [
                    "firewall-cmd",
                    "--permanent",
                    "--zone=public",
                    f"--add-port={port}/tcp",
                ],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": True,
                "description": f"preserve management port {port}/tcp",
            }
        )
    commands.append(
        {
            "argv": ["firewall-cmd", "--reload"],
            "sudo": True,
            "timeout": 10,
            "ignore_errors": False,
            "description": "reload firewalld",
        }
    )
    return {
        "flavor": "firewalld",
        "files": [],
        "commands": commands,
        "service_actions": [
            {"service": "firewalld", "action": "enable"},
            {"service": "firewalld", "action": "start"},
        ],
        "preserved_ports": preserved,
    }


def _firewalld_disable_plan() -> Dict[str, Any]:
    return {
        "flavor": "firewalld",
        "files": [],
        "commands": [],
        "service_actions": [
            {"service": "firewalld", "action": "stop"},
            {"service": "firewalld", "action": "disable"},
        ],
    }


def _firewalld_restart_plan() -> Dict[str, Any]:
    return {
        "flavor": "firewalld",
        "files": [],
        "commands": [
            {
                "argv": ["firewall-cmd", "--reload"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": False,
                "description": "reload firewalld",
            },
        ],
        "service_actions": [{"service": "firewalld", "action": "restart"}],
    }


def _firewalld_apply_role_ports(
    ipv4_ports: List[Dict], ipv6_ports: List[Dict]
) -> Dict[str, Any]:
    commands = []
    for spec in (ipv4_ports or []) + (ipv6_ports or []):
        port = spec.get("port")
        if spec.get("tcp"):
            commands.append(
                {
                    "argv": [
                        "firewall-cmd",
                        "--permanent",
                        "--zone=public",
                        f"--add-port={port}/tcp",
                    ],
                    "sudo": True,
                    "timeout": 10,
                    "ignore_errors": True,
                    "description": f"allow {port}/tcp",
                }
            )
        if spec.get("udp"):
            commands.append(
                {
                    "argv": [
                        "firewall-cmd",
                        "--permanent",
                        "--zone=public",
                        f"--add-port={port}/udp",
                    ],
                    "sudo": True,
                    "timeout": 10,
                    "ignore_errors": True,
                    "description": f"allow {port}/udp",
                }
            )
    commands.append(
        {
            "argv": ["firewall-cmd", "--reload"],
            "sudo": True,
            "timeout": 10,
            "ignore_errors": False,
            "description": "reload firewalld",
        }
    )
    return {
        "flavor": "firewalld",
        "files": [],
        "commands": commands,
        "service_actions": [],
    }


def _firewalld_remove_role_ports(
    ipv4_ports: List[Dict],
    ipv6_ports: List[Dict],
    agent_ports: Optional[List[int]] = None,
) -> Dict[str, Any]:
    preserved = set(_preserved_ports(agent_ports))
    commands = []
    skipped = []
    for spec in (ipv4_ports or []) + (ipv6_ports or []):
        port = spec.get("port")
        if port in preserved:
            skipped.append(port)
            continue
        if spec.get("tcp"):
            commands.append(
                {
                    "argv": [
                        "firewall-cmd",
                        "--permanent",
                        "--zone=public",
                        f"--remove-port={port}/tcp",
                    ],
                    "sudo": True,
                    "timeout": 10,
                    "ignore_errors": True,
                    "description": f"remove {port}/tcp",
                }
            )
        if spec.get("udp"):
            commands.append(
                {
                    "argv": [
                        "firewall-cmd",
                        "--permanent",
                        "--zone=public",
                        f"--remove-port={port}/udp",
                    ],
                    "sudo": True,
                    "timeout": 10,
                    "ignore_errors": True,
                    "description": f"remove {port}/udp",
                }
            )
    commands.append(
        {
            "argv": ["firewall-cmd", "--reload"],
            "sudo": True,
            "timeout": 10,
            "ignore_errors": False,
            "description": "reload firewalld",
        }
    )
    return {
        "flavor": "firewalld",
        "files": [],
        "commands": commands,
        "service_actions": [],
        "skipped_preserved_ports": sorted(set(skipped)),
    }


# ---------------------------------------------------------------------------
# Windows Firewall (netsh advfirewall)
# ---------------------------------------------------------------------------


def _windows_enable_plan(agent_ports: Optional[List[int]] = None) -> Dict[str, Any]:
    preserved_set = {3389}  # RDP
    for p in DEFAULT_PRESERVED_PORTS:
        preserved_set.add(p)
    if agent_ports:
        for p in agent_ports:
            if isinstance(p, int):
                preserved_set.add(p)
    preserved = sorted(preserved_set)
    commands = []
    for port in preserved:
        commands.append(
            {
                "argv": [
                    "netsh",
                    "advfirewall",
                    "firewall",
                    "add",
                    "rule",
                    f"name=SysManage Preserve {port}/TCP",
                    "dir=in",
                    "action=allow",
                    "protocol=TCP",
                    f"localport={port}",
                ],
                "sudo": False,
                "elevated": True,
                "timeout": 10,
                "ignore_errors": True,
                "description": f"preserve management port {port}/tcp",
            }
        )
    commands.append(
        {
            "argv": ["netsh", "advfirewall", "set", "allprofiles", "state", "on"],
            "sudo": False,
            "elevated": True,
            "timeout": 10,
            "ignore_errors": False,
            "description": "enable Windows Firewall (all profiles)",
        }
    )
    return {
        "flavor": "windows",
        "files": [],
        "commands": commands,
        "service_actions": [{"service": "MpsSvc", "action": "start"}],
        "preserved_ports": preserved,
    }


def _windows_disable_plan() -> Dict[str, Any]:
    return {
        "flavor": "windows",
        "files": [],
        "commands": [
            {
                "argv": ["netsh", "advfirewall", "set", "allprofiles", "state", "off"],
                "sudo": False,
                "elevated": True,
                "timeout": 10,
                "ignore_errors": False,
                "description": "disable Windows Firewall",
            },
        ],
        "service_actions": [],
    }


def _windows_restart_plan() -> Dict[str, Any]:
    return {
        "flavor": "windows",
        "files": [],
        "commands": [],
        "service_actions": [{"service": "MpsSvc", "action": "restart"}],
    }


def _windows_apply_role_ports(
    ipv4_ports: List[Dict], ipv6_ports: List[Dict]
) -> Dict[str, Any]:
    commands = []
    for spec in (ipv4_ports or []) + (ipv6_ports or []):
        port = spec.get("port")
        for proto_name, key in (("TCP", "tcp"), ("UDP", "udp")):
            if spec.get(key):
                commands.append(
                    {
                        "argv": [
                            "netsh",
                            "advfirewall",
                            "firewall",
                            "add",
                            "rule",
                            f"name=SysManage Port {port}/{proto_name}",
                            "dir=in",
                            "action=allow",
                            f"protocol={proto_name}",
                            f"localport={port}",
                        ],
                        "sudo": False,
                        "elevated": True,
                        "timeout": 10,
                        "ignore_errors": True,
                        "description": f"allow {port}/{key}",
                    }
                )
    return {
        "flavor": "windows",
        "files": [],
        "commands": commands,
        "service_actions": [],
    }


def _windows_remove_role_ports(
    ipv4_ports: List[Dict], ipv6_ports: List[Dict]
) -> Dict[str, Any]:
    commands = []
    for spec in (ipv4_ports or []) + (ipv6_ports or []):
        port = spec.get("port")
        for proto_name, key in (("TCP", "tcp"), ("UDP", "udp")):
            if spec.get(key):
                commands.append(
                    {
                        "argv": [
                            "netsh",
                            "advfirewall",
                            "firewall",
                            "delete",
                            "rule",
                            f"name=SysManage Port {port}/{proto_name}",
                        ],
                        "sudo": False,
                        "elevated": True,
                        "timeout": 10,
                        "ignore_errors": True,
                        "description": f"remove {port}/{key}",
                    }
                )
    return {
        "flavor": "windows",
        "files": [],
        "commands": commands,
        "service_actions": [],
    }


# ---------------------------------------------------------------------------
# macOS Application Firewall (socketfilterfw — port-based ops are no-ops here)
# ---------------------------------------------------------------------------


_SOCKETFILTERFW = "/usr/libexec/ApplicationFirewall/socketfilterfw"


def _macos_enable_plan() -> Dict[str, Any]:
    return {
        "flavor": "macos",
        "files": [],
        "commands": [
            {
                "argv": [_SOCKETFILTERFW, "--setglobalstate", "on"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": False,
                "description": "enable macOS Application Firewall",
            },
        ],
        "service_actions": [],
    }


def _macos_disable_plan() -> Dict[str, Any]:
    return {
        "flavor": "macos",
        "files": [],
        "commands": [
            {
                "argv": [_SOCKETFILTERFW, "--setglobalstate", "off"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": False,
                "description": "disable macOS Application Firewall",
            },
        ],
        "service_actions": [],
    }


def _macos_restart_plan() -> Dict[str, Any]:
    # No discrete restart for socketfilterfw; toggle off+on.
    return {
        "flavor": "macos",
        "files": [],
        "commands": [
            {
                "argv": [_SOCKETFILTERFW, "--setglobalstate", "off"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": True,
                "description": "toggle macOS firewall off",
            },
            {
                "argv": [_SOCKETFILTERFW, "--setglobalstate", "on"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": False,
                "description": "toggle macOS firewall on",
            },
        ],
        "service_actions": [],
    }


def _macos_noop_role_ports() -> Dict[str, Any]:
    # macOS Application Firewall is app-based, not port-based. Open source
    # treats role-port apply/remove as a no-op (Pro+ engine handles app
    # rules properly via app_path).
    return {
        "flavor": "macos",
        "files": [],
        "commands": [],
        "service_actions": [],
        "note": (
            "macOS Application Firewall is application-based; port-only "
            "rules are a no-op. Use the Pro+ engine for app-path rules."
        ),
    }


# ---------------------------------------------------------------------------
# BSD pf (OpenBSD / FreeBSD) — basic on/off via pfctl
# ---------------------------------------------------------------------------


def _pf_enable_plan() -> Dict[str, Any]:
    return {
        "flavor": "pf",
        "files": [],
        "commands": [
            {
                "argv": ["pfctl", "-e"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": True,
                "description": "enable pf",
            },
        ],
        "service_actions": [
            {"service": "pf", "action": "enable"},
            {"service": "pf", "action": "start"},
        ],
    }


def _pf_disable_plan() -> Dict[str, Any]:
    return {
        "flavor": "pf",
        "files": [],
        "commands": [
            {
                "argv": ["pfctl", "-d"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": True,
                "description": "disable pf",
            },
        ],
        "service_actions": [
            {"service": "pf", "action": "stop"},
            {"service": "pf", "action": "disable"},
        ],
    }


def _pf_restart_plan() -> Dict[str, Any]:
    return {
        "flavor": "pf",
        "files": [],
        "commands": [
            {
                "argv": ["pfctl", "-d"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": True,
                "description": "stop pf",
            },
            {
                "argv": ["pfctl", "-e"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": False,
                "description": "start pf",
            },
        ],
        "service_actions": [],
    }


def _pf_role_ports_unsupported() -> Dict[str, Any]:
    # Open source emits no port commands for pf — pf needs a full pf.conf
    # rewrite which only the Pro+ engine knows how to do safely.
    return {
        "flavor": "pf",
        "files": [],
        "commands": [],
        "service_actions": [],
        "note": (
            "pf role-port management requires regenerating /etc/pf.conf; "
            "use the Pro+ firewall_orchestration_engine for this."
        ),
    }


# ---------------------------------------------------------------------------
# NPF (NetBSD) — basic on/off
# ---------------------------------------------------------------------------


def _npf_enable_plan() -> Dict[str, Any]:
    return {
        "flavor": "npf",
        "files": [],
        "commands": [
            {
                "argv": ["npfctl", "start"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": True,
                "description": "start npf",
            },
        ],
        "service_actions": [
            {"service": "npf", "action": "enable"},
            {"service": "npf", "action": "start"},
        ],
    }


def _npf_disable_plan() -> Dict[str, Any]:
    return {
        "flavor": "npf",
        "files": [],
        "commands": [
            {
                "argv": ["npfctl", "stop"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": True,
                "description": "stop npf",
            },
        ],
        "service_actions": [
            {"service": "npf", "action": "stop"},
            {"service": "npf", "action": "disable"},
        ],
    }


def _npf_restart_plan() -> Dict[str, Any]:
    return {
        "flavor": "npf",
        "files": [],
        "commands": [
            {
                "argv": ["npfctl", "reload"],
                "sudo": True,
                "timeout": 10,
                "ignore_errors": False,
                "description": "reload npf",
            },
        ],
        "service_actions": [],
    }


def _npf_role_ports_unsupported() -> Dict[str, Any]:
    return {
        "flavor": "npf",
        "files": [],
        "commands": [],
        "service_actions": [],
        "note": (
            "npf role-port management requires regenerating /etc/npf.conf; "
            "use the Pro+ firewall_orchestration_engine for this."
        ),
    }


# ---------------------------------------------------------------------------
# Per-flavor dispatch tables
# ---------------------------------------------------------------------------


_ENABLE_BY_FLAVOR = {
    "ufw": lambda host_info: _ufw_enable_plan(host_info.get("agent_ports")),
    "firewalld": lambda host_info: _firewalld_enable_plan(host_info.get("agent_ports")),
    "windows": lambda host_info: _windows_enable_plan(host_info.get("agent_ports")),
    "macos": lambda host_info: _macos_enable_plan(),
    "pf": lambda host_info: _pf_enable_plan(),
    "npf": lambda host_info: _npf_enable_plan(),
}

_DISABLE_BY_FLAVOR = {
    "ufw": lambda host_info: _ufw_disable_plan(),
    "firewalld": lambda host_info: _firewalld_disable_plan(),
    "windows": lambda host_info: _windows_disable_plan(),
    "macos": lambda host_info: _macos_disable_plan(),
    "pf": lambda host_info: _pf_disable_plan(),
    "npf": lambda host_info: _npf_disable_plan(),
}

_RESTART_BY_FLAVOR = {
    "ufw": lambda host_info: _ufw_restart_plan(),
    "firewalld": lambda host_info: _firewalld_restart_plan(),
    "windows": lambda host_info: _windows_restart_plan(),
    "macos": lambda host_info: _macos_restart_plan(),
    "pf": lambda host_info: _pf_restart_plan(),
    "npf": lambda host_info: _npf_restart_plan(),
}

_APPLY_BY_FLAVOR = {
    "ufw": lambda host_info, v4, v6: _ufw_apply_role_ports(v4, v6),
    "firewalld": lambda host_info, v4, v6: _firewalld_apply_role_ports(v4, v6),
    "windows": lambda host_info, v4, v6: _windows_apply_role_ports(v4, v6),
    "macos": lambda host_info, v4, v6: _macos_noop_role_ports(),
    "pf": lambda host_info, v4, v6: _pf_role_ports_unsupported(),
    "npf": lambda host_info, v4, v6: _npf_role_ports_unsupported(),
}

_REMOVE_BY_FLAVOR = {
    "ufw": lambda host_info, v4, v6: _ufw_remove_role_ports(
        v4, v6, host_info.get("agent_ports")
    ),
    "firewalld": lambda host_info, v4, v6: _firewalld_remove_role_ports(
        v4, v6, host_info.get("agent_ports")
    ),
    "windows": lambda host_info, v4, v6: _windows_remove_role_ports(v4, v6),
    "macos": lambda host_info, v4, v6: _macos_noop_role_ports(),
    "pf": lambda host_info, v4, v6: _pf_role_ports_unsupported(),
    "npf": lambda host_info, v4, v6: _npf_role_ports_unsupported(),
}


# ---------------------------------------------------------------------------
# Public API: 6 builder entry points used by the API endpoints
# ---------------------------------------------------------------------------


def build_enable_plan(host_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a plan that turns the host's firewall on with management ports preserved."""
    flavor = detect_firewall_flavor(
        host_info.get("platform"), host_info.get("platform_release")
    )
    return _ENABLE_BY_FLAVOR[flavor](host_info)


def build_disable_plan(host_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a plan that turns the host's firewall off."""
    flavor = detect_firewall_flavor(
        host_info.get("platform"), host_info.get("platform_release")
    )
    return _DISABLE_BY_FLAVOR[flavor](host_info)


def build_restart_plan(host_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a plan that reloads/restarts the host's firewall."""
    flavor = detect_firewall_flavor(
        host_info.get("platform"), host_info.get("platform_release")
    )
    return _RESTART_BY_FLAVOR[flavor](host_info)


def build_deploy_plan(host_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a plan that brings the firewall up. (Same as enable for the basic tier.)"""
    return build_enable_plan(host_info)


def build_apply_role_ports_plan(
    host_info: Dict[str, Any],
    ipv4_ports: List[Dict],
    ipv6_ports: List[Dict],
) -> Dict[str, Any]:
    """Build a plan that adds the given role's port-permits."""
    flavor = detect_firewall_flavor(
        host_info.get("platform"), host_info.get("platform_release")
    )
    return _APPLY_BY_FLAVOR[flavor](host_info, ipv4_ports, ipv6_ports)


def build_remove_role_ports_plan(
    host_info: Dict[str, Any],
    ipv4_ports: List[Dict],
    ipv6_ports: List[Dict],
) -> Dict[str, Any]:
    """Build a plan that removes the given role's port-permits (preserved ports skipped)."""
    flavor = detect_firewall_flavor(
        host_info.get("platform"), host_info.get("platform_release")
    )
    return _REMOVE_BY_FLAVOR[flavor](host_info, ipv4_ports, ipv6_ports)
