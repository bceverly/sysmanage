#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 23.2 proof: several operating systems on ONE machine share one machine
record and one asset tag.

The case this exists for is a multi-boot laptop -- the T480 with Windows,
Ubuntu and OpenBSD.  Boot it into each OS once so each agent registers and
sends its hardware report, approve the three hosts, then run this against the
server.  It reads back exactly what the UI shows (``GET /host/{id}/machine``)
and asserts:

  1. every host reported a usable hardware identity and is linked to a
     machine (no conflict held, no unreadable identity);
  2. all of them are linked to the SAME machine -- although OpenBSD prints the
     SMBIOS UUID with its first three fields byte-swapped;
  3. each host lists every other one under "other operating systems";
  4. they show the same asset tag (``--expect-tag`` to pin which).

Run it a second time after reinstalling one of the OSes (a new host) to prove
a reinstall lands on the same machine and keeps the tag.

UUIDs and serials are MASKED in the output unless ``--show-ids``: these are
real machines' identities, and the output is meant to be pasted into notes.

Usage:
    python3 scripts/machine_identity_proof.py --server https://sysmanage.lan \\
        --hosts t480-win,t480-ubuntu,t480-openbsd [--expect-tag GDR-000042]

Credentials: ``--token`` (or SYSMANAGE_TOKEN; a session or ``smk_`` API key),
or SYSMANAGE_USER + SYSMANAGE_PASSWORD for a login without MFA.  ``--insecure``
skips TLS verification for a lab server with a self-signed certificate.
Exit status: 0 proven, 1 not proven, 2 could not ask.
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

_CONTEXT = None


def _request(server, method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        f"{server.rstrip('/')}/api/v1{path}", data=data, method=method
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(
            req, timeout=30, context=_CONTEXT
        ) as resp:  # nosec B310
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _login(server):
    user, password = os.environ.get("SYSMANAGE_USER"), os.environ.get(
        "SYSMANAGE_PASSWORD"
    )
    if not (user and password):
        sys.exit(
            "Give --token (or SYSMANAGE_TOKEN), or SYSMANAGE_USER + SYSMANAGE_PASSWORD."
        )
    status, body = _request(
        server, "POST", "/login", body={"userid": user, "password": password}
    )
    token = (body or {}).get("Authorization") or (body or {}).get("access_token")
    if status != 200 or not token:
        print(
            f"Login failed (HTTP {status}); with MFA on, use --token.", file=sys.stderr
        )
        sys.exit(2)
    return token.replace("Bearer ", "")


def _mask(value, show):
    if not value or show:
        return value or "-"
    return f"{value[:4]}...{value[-2:]}" if len(value) > 8 else "***"


def _find_hosts(server, token, names):
    status, hosts = _request(server, "GET", "/hosts", token)
    if status != 200 or not isinstance(hosts, list):
        print(f"Could not list hosts (HTTP {status}).", file=sys.stderr)
        sys.exit(2)
    found = {}
    for name in names:
        matches = [
            h
            for h in hosts
            if h.get("fqdn") == name or (h.get("fqdn") or "").split(".")[0] == name
        ]
        if len(matches) != 1:
            print(
                f"Host {name!r}: {len(matches)} matches -- use the full FQDN.",
                file=sys.stderr,
            )
            sys.exit(2)
        found[name] = matches[0]
    return found


def _check(name, host, info, others, show):
    """Problems for one host, printing what it reported."""
    identity, machine = info.get("identity") or {}, info.get("machine")
    print(f"\n{host['fqdn']}")
    print(f"  system UUID   {_mask(identity.get('system_uuid'), show)}")
    print(f"  system serial {_mask(identity.get('system_serial'), show)}")
    print(f"  sources       {identity.get('status') or {}}")
    problems = []
    if info.get("conflict"):
        problems.append(
            f"{name}: link held for an admin ({info['conflict'].get('reason')})"
        )
    if machine is None:
        problems.append(f"{name}: not linked to a machine (see the sources above)")
        return problems, None
    print(
        f"  machine       {machine['id']}  {machine.get('vendor')} {machine.get('model')}"
    )
    print(f"  asset tag     {machine.get('asset_tag') or '(none)'}")
    listed = {h["id"] for h in info.get("other_hosts") or []}
    missing = sorted(others[i] for i in set(others) - listed)
    if missing:
        problems.append(f"{name}: does not list {', '.join(missing)} on its machine")
    return problems, machine


def main():
    global _CONTEXT  # pylint: disable=global-statement
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", required=True)
    parser.add_argument(
        "--hosts", required=True, help="comma-separated FQDNs or short names"
    )
    parser.add_argument("--expect-tag")
    parser.add_argument("--token", default=os.environ.get("SYSMANAGE_TOKEN"))
    parser.add_argument("--show-ids", action="store_true")
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()
    if not args.server.lower().startswith(("https://", "http://")):
        sys.exit("--server must be an http:// or https:// URL.")
    if args.insecure:
        # Lab servers with a self-signed certificate only; opt-in.
        # nosemgrep
        _CONTEXT = ssl._create_unverified_context()  # nosec B323
    names = [n.strip() for n in args.hosts.split(",") if n.strip()]
    if len(names) < 2:
        sys.exit("Name at least two hosts on the same machine.")
    token = args.token or _login(args.server)
    hosts = _find_hosts(args.server, token, names)

    problems, machines = [], {}
    for name, host in hosts.items():
        status, info = _request(
            args.server, "GET", f"/host/{host['id']}/machine", token
        )
        if status != 200 or not isinstance(info, dict):
            print(f"Could not read {name}'s machine (HTTP {status}).", file=sys.stderr)
            sys.exit(2)
        others = {h["id"]: h["fqdn"] for n, h in hosts.items() if n != name}
        found, machine = _check(name, host, info, others, args.show_ids)
        problems += found
        if machine is not None:
            machines[name] = machine

    if len({m["id"] for m in machines.values()}) > 1:
        problems.append("the hosts are linked to DIFFERENT machines")
    tags = {m.get("asset_tag") for m in machines.values()}
    if args.expect_tag and tags != {args.expect_tag}:
        problems.append(
            f"expected asset tag {args.expect_tag}, found {sorted(map(str, tags))}"
        )

    print()
    if problems:
        print("NOT PROVEN:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        f"PROVEN: {len(hosts)} operating systems, one machine, one asset tag "
        f"({next(iter(tags)) or 'none set yet'})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
