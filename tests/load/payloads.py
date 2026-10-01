# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Synthetic agent payloads for the fleet simulator (Phase 22).

Shapes follow what the real agent sends (sysmanage-agent collection/*), sized
like a typical Linux server: hundreds of packages, dozens of users and groups,
a few hundred processes.  What costs the server at scale is mostly the SIZE
and FREQUENCY of these, so the size is a knob (``packages``) and the big lists
are serialized ONCE and spliced into every agent's message -- 10k agents must
not each spend CPU building the same 300 KB of JSON, or the harness measures
itself instead of the server.
"""

import json
import random
import uuid
from datetime import datetime, timezone

PLATFORM = {
    "platform": "Linux",
    "platform_release": "Ubuntu 24.04",
    "platform_version": "#41-Ubuntu SMP PREEMPT_DYNAMIC",
    "architecture": "x86_64",
    "processor": "x86_64",
    "machine_architecture": "x86_64",
    "timezone": "UTC",
    "python_version": "3.12.3",
    "os_info": {"distribution": "Ubuntu", "distribution_version": "24.04",
                "distribution_codename": "noble", "machine": "x86_64"},
}  # fmt: skip

AGENT_VERSION = "3.9.0.0"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Payloads:
    """The large, shared parts of an agent's reports, serialized once."""

    def __init__(self, packages=600, seed=22):
        rng = random.Random(seed)
        self.packages = packages
        self.software = json.dumps([
            {"package_name": f"pkg-{i:04d}", "version": f"{rng.randint(0, 9)}.{rng.randint(0, 40)}.{rng.randint(0, 99)}-1ubuntu1",
             "architecture": "amd64", "description": f"Synthetic package number {i} for load testing",
             "package_manager": "apt", "source": "ubuntu", "is_system_package": i % 3 == 0,
             "is_user_installed": i % 3 != 0, "size_bytes": rng.randint(10_000, 50_000_000)}
            for i in range(packages)
        ])  # fmt: skip
        self.users = json.dumps([
            {"username": f"user{i}", "uid": 1000 + i if i > 20 else i,
             "home_directory": f"/home/user{i}", "shell": "/bin/bash",
             "is_system_user": i <= 20, "groups": ["users"]}
            for i in range(45)
        ])  # fmt: skip
        self.groups = json.dumps([
            {"group_name": f"group{i}", "gid": 1000 + i, "is_system_group": i < 40}
            for i in range(60)
        ])  # fmt: skip
        self.processes = json.dumps([
            {"pid": 100 + i, "name": f"proc-{i}", "user": "root" if i % 4 else "app",
             "cpu_percent": round(rng.random() * 3, 2), "memory_percent": round(rng.random() * 2, 2),
             "command": f"/usr/sbin/proc-{i} --flag"}
            for i in range(220)
        ])  # fmt: skip
        self.updates = json.dumps([
            {"package_name": f"pkg-{i:04d}", "current_version": "1.0.0-1", "available_version": "1.0.1-1",
             "package_manager": "apt", "is_security_update": i % 4 == 0, "is_system_update": i % 2 == 0}
            for i in range(0, min(packages, 600), 25)
        ])  # fmt: skip
        self.hardware = {
            "cpu_vendor": "GenuineIntel", "cpu_model": "Intel(R) Xeon(R) Gold 6338", "cpu_cores": 8,
            "cpu_threads": 16, "cpu_frequency_mhz": 2000, "memory_total_mb": 32768,
            "memory_available_mb": 20480,
            "hardware_details": json.dumps({"vendor": "QEMU", "product": "Standard PC"}),
            "storage_details": json.dumps([
                {"name": "/dev/sda1", "size": 107374182400, "type": "ext4", "mount_point": "/",
                 "file_system": "ext4", "is_physical": False}]),
            "network_details": json.dumps([
                {"name": "eth0", "mac_address": "52:54:00:00:00:01", "is_active": True,
                 "ipv4_address": "10.0.0.10", "ipv6_address": None, "subnet_mask": "255.255.255.0",
                 "speed_mbps": 10000}]),
        }  # fmt: skip


def envelope(message_type, data, spliced=None):
    """One agent message as a JSON string.

    ``spliced`` maps field name -> already-serialized JSON, appended to the
    data object without re-encoding it (the shared large lists)."""
    body = json.dumps(data)
    if spliced:
        extra = ", ".join(f'"{k}": {v}' for k, v in spliced.items())
        body = body[:-1] + (", " if data else "") + extra + "}"
    head = json.dumps({"message_type": message_type, "message_id": str(uuid.uuid4()),
                       "timestamp": now_iso()})  # fmt: skip
    return head[:-1] + ', "data": ' + body + "}"


def registration_body(agent):
    """POST /api/host/register -- a flat object, not an envelope."""
    return {
        "message_type": "registration_request", "message_id": str(uuid.uuid4()),
        "timestamp": now_iso(), "hostname": agent.hostname, "fqdn": agent.hostname,
        "ipv4": agent.ipv4, "ipv6": None, "active": True, "script_execution_enabled": False,
        "is_privileged": True, "enabled_shells": ["bash", "sh"], "agent_version": AGENT_VERSION,
    }  # fmt: skip


def system_info(agent):
    data = registration_body(agent)
    data.update(PLATFORM)
    return envelope("system_info", agent.identify(data))


def heartbeat(agent):
    return envelope("heartbeat", agent.identify({
        "agent_status": "healthy", "timestamp": now_iso(), "hostname": agent.hostname,
        "ipv4": agent.ipv4, "ipv6": None, "is_privileged": True,
        "script_execution_enabled": False, "enabled_shells": ["bash", "sh"],
        "agent_version": AGENT_VERSION,
    }))  # fmt: skip


def _base(agent, **extra):
    data = {"hostname": agent.hostname}
    data.update(extra)
    return agent.identify(data)


def periodic_set(agent, p):
    """The 14-step collection the agent sends on connect and every 5 min
    (data_collector.py), in the agent's order."""
    return [
        envelope("software_inventory_update",
                 _base(agent, collection_timestamp=now_iso(), platform="Linux", total_packages=p.packages),
                 {"software_packages": p.software}),
        envelope("user_access_update", _base(agent, platform="Linux", total_users=45, total_groups=60,
                                             system_users=21, regular_users=24, system_groups=40, regular_groups=20),
                 {"users": p.users, "groups": p.groups}),
        envelope("hardware_update", _base(agent, **p.hardware)),
        envelope("os_version_update", _base(agent, **PLATFORM)),
        envelope("reboot_status_update", _base(agent, reboot_required=False, timestamp=now_iso())),
        envelope("third_party_repository_update", _base(agent, repositories=[], count=0)),
        envelope("antivirus_status_update", _base(agent, software_name="clamav",
                                                  install_path="/usr/bin", version="1.4.3", enabled=True)),
        envelope("firewall_status_update", _base(agent, firewall_name="ufw", enabled=True,
                                                 tcp_open_ports="22", udp_open_ports="",
                                                 ipv4_ports="22", ipv6_ports="")),
        envelope("graylog_status_update", _base(agent, is_attached=False, target_hostname=None,
                                                target_ip=None, mechanism=None, port=None)),
        envelope("process_status_update", _base(agent, process_count=220, truncated=False,
                                                collected_at=now_iso()),
                 {"processes": p.processes}),
        envelope("host_metrics", agent.identify({"collected_at": now_iso(), "metrics": {
            "host.cpu_percent": 12.5, "host.memory_used_percent": 41.0, "host.swap_used_percent": 0.0,
            "host.load_1m": 0.8, "host.disk_used_percent_max": 55.0}})),
        envelope("child_host_list_update", _base(agent, success=True, child_hosts=[], count=0)),
    ]  # fmt: skip


def initial_burst(agent, p):
    """What registration_success(approved) triggers, in order, with the 2 s
    pauses the agent takes (data_collector.py _send_initial_data)."""
    return [
        (envelope("os_version_update", _base(agent, **PLATFORM)), 0),
        (envelope("fips_compliance_update", _base(agent, status="not_enabled", enabled=False,
                                                  available=True, kernel_enforced=False,
                                                  vendor="Canonical", package_version=None)), 0),
        (envelope("hardware_update", _base(agent, **p.hardware)), 2),
        (envelope("user_access_update", _base(agent, platform="Linux", total_users=45, total_groups=60),
                  {"users": p.users, "groups": p.groups}), 2),
        (envelope("software_inventory_update",
                  _base(agent, collection_timestamp=now_iso(), platform="Linux", total_packages=p.packages),
                  {"software_packages": p.software}), 0),
        (envelope("package_updates_update",
                  _base(agent, detection_timestamp=now_iso(), platform="Linux", total_updates=24,
                        security_updates=6, system_updates=12, application_updates=12, requires_reboot=False),
                  {"available_updates": p.updates}), 2),
        (envelope("host_certificates_update", _base(agent, certificates=[], collected_at=now_iso())), 0),
        (envelope("role_data", _base(agent, roles=[], role_count=0, collection_timestamp=now_iso())), 0),
        (envelope("third_party_repository_update", _base(agent, repositories=[], count=0)), 0),
        (envelope("firewall_status_update", _base(agent, firewall_name="ufw", enabled=True,
                                                  tcp_open_ports="22", udp_open_ports="",
                                                  ipv4_ports="22", ipv6_ports="")), 0),
        (envelope("graylog_status_update", _base(agent, is_attached=False)), 0),
        (envelope("process_status_update", _base(agent, process_count=220, truncated=False,
                                                 collected_at=now_iso()),
                  {"processes": p.processes}), 0),
        (envelope("child_host_list_update", _base(agent, success=True, child_hosts=[], count=0)), 0),
    ]  # fmt: skip


def package_updates(agent, p):
    return envelope("package_updates_update",
                    _base(agent, detection_timestamp=now_iso(), platform="Linux", total_updates=24,
                          security_updates=6, system_updates=12, application_updates=12,
                          requires_reboot=False),
                    {"available_updates": p.updates})  # fmt: skip


def child_hosts(agent):
    return envelope(
        "child_host_list_update", _base(agent, success=True, child_hosts=[], count=0)
    )


def command_ack(message_id):
    """command_acknowledgment carries no data (message_handler.py:206)."""
    return json.dumps({"message_type": "command_acknowledgment", "message_id": message_id,
                       "timestamp": now_iso()})  # fmt: skip


def command_result(agent, command_id, command_type):
    return envelope("command_result", agent.identify({
        "command_id": command_id, "command_type": command_type, "success": True,
        "result": "simulated", "error": None, "exit_code": 0}))  # fmt: skip


def pong(ping_id):
    return envelope("pong", {"ping_id": ping_id})
