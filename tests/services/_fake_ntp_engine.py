# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A stand-in for config_management_engine's NTP functions (the real ones
are Pro+ and tested in their own repository): the same contract, minimal."""


def ntp_validate_servers(servers):
    if not servers:
        return ["no_servers"]
    return ["bad_server"] if any(" " in s or "\n" in s for s in servers) else []


def ntp_build_plan(host, servers):
    if host.get("service") in (None, "none"):
        return {"error": "no_time_service"}
    return {"plan": {"files": [{"path": "/etc/chrony.conf", "servers": servers}]}}


def ntp_compare(host, servers):
    if host.get("service") is None:
        return [{"code": "not_reported"}]
    findings = []
    actual = host.get("configured_servers")
    if actual is None:
        findings.append({"code": "servers_not_reported"})
    elif sorted(actual) != sorted(servers):
        findings.append(
            {"code": "servers_differ", "expected": servers, "actual": actual}
        )
    if host.get("enabled") is False:
        findings.append({"code": "not_enabled"})
    return findings
