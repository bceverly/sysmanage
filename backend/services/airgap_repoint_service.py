# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Auto-repoint managed agents at the local air-gap mirror.

When this server runs as an Air-Gap Repository, every agent that talks
to it should have its package manager pointed at this server's mirror
(and its online sources disabled) so it can never reach the internet.

This module is called from the inbound message path (see
``inbound_processor``) so the directive propagates on the very next
communication cycle after the server's role is set to ``repository`` --
even for agents that connected while the role was still ``standard``.

Efficiency: a naive "dispatch on every message" would run ``apt-get
update`` on every heartbeat.  Instead we track, in memory, the config
signature we last repointed each host with and only re-dispatch when it
*changes* (role flip, fresh ingest that moves the repo_url, etc.).  So
the steady state is zero traffic; a change reaches every connected agent
within one cycle.  The in-memory map resets on server restart, which
just causes one harmless idempotent re-dispatch per host.

The repoint plan is built here (not via the Pro+ engine's
``build_agent_repoint_plan``, which emits a *flat* ``deb URL ./`` repo
with ``[trusted=yes]`` and never disables online sources) so it matches
the validated apt-mirror layout: ``deb URL <suite> <components>`` (the
mirror's Ubuntu-signed InRelease verifies normally), upstream sources
disabled, then ``apt-get update``.  Dispatched via the same
``enqueue_apply_plan`` path the ingest mount/copy plans use -- the agent
already knows how to execute these command plans, so no agent change.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict, Optional
from urllib.parse import urlsplit

from backend.persistence import models
from backend.services import server_config_service

logger = logging.getLogger(__name__)

# host_id -> signature of the last repoint config we dispatched.
_LAST_REPOINT: Dict[str, str] = {}

# Default apt components.  Only ``main`` is mirrored today (the collector
# snapshot path), and the AirgapLocalRepository row doesn't persist the
# component set, so we default here.  TODO: thread components through the
# manifest target when multi-component mirrors land.
_DEFAULT_COMPONENTS = "main"

# Distro families we can repoint.  Maps a substring found in the repo /
# agent distro to the package-manager plan builder.
_APT_DISTROS = ("ubuntu", "debian")
_DNF_DISTROS = ("fedora", "rhel", "rocky", "alma", "centos")
_ZYPPER_DISTROS = ("opensuse", "sles")
_APK_DISTROS = ("alpine",)
_PKG_DISTROS = ("freebsd",)


def _cmd(argv, timeout, ignore_errors, description):
    return {
        "argv": argv,
        "timeout": timeout,
        "ignore_errors": ignore_errors,
        "description": description,
    }


def _build_apt_repoint_plan(repo_url: str, suite: str, components: str) -> dict:
    """Point apt at the local mirror and disable upstream sources.

    Writes the mirror's deb source via the plan's ``files`` mechanism
    (the agent's deploy_files → ``sudo install -D``) rather than
    ``sudo sh -c "printf > file"``: the agent sudoers deliberately does
    NOT authorize ``/bin/sh`` (blanket shell would defeat the
    constrained-sudo model), and a shell-wrapped write is denied with
    "user not allowed to run" -- silently leaving the agent unrepointed.
    ``files`` are deployed before ``commands`` run.

    Online sources are then disabled with ``sed`` (an authorized
    binary): comment the deb822 ``ubuntu.sources`` keys and any legacy
    ``sources.list`` deb lines.  Both steps ignore errors so a host that
    has only one of the two source styles still succeeds.  Finally
    ``apt-get update`` refreshes against the mirror; its Ubuntu-signed
    InRelease verifies against the host keyring (no ``[trusted=yes]``).
    """
    deb_line = f"deb {repo_url} {suite} {components}\n"
    list_path = "/etc/apt/sources.list.d/sysmanage-airgap.list"
    return {
        "files": [
            {
                "path": list_path,
                "content": deb_line,
                "permissions": "0644",
                "owner_uid": 0,
                "owner_gid": 0,
            },
        ],
        "commands": [
            # Disable the deb822 OS sources (resolute+) if present.  A
            # deb822 stanza must be disabled WHOLESALE -- commenting only
            # some fields (e.g. Types) leaves a stanza missing a required
            # field, which apt rejects with "Malformed stanza … (type)"
            # and then refuses to read ANY source.  So comment every
            # non-comment line: an all-commented file has zero stanzas
            # and apt ignores it cleanly.  sed -i errors if the file is
            # absent; ignore_errors handles that.
            _cmd(
                [
                    "sudo",
                    "sed",
                    "-i",
                    "s/^[^#]/#&/",
                    "/etc/apt/sources.list.d/ubuntu.sources",
                ],
                30,
                True,
                "disable upstream ubuntu.sources (comment all lines)",
            ),
            # Comment out any active deb lines in the legacy sources.list.
            _cmd(
                ["sudo", "sed", "-i", "s/^deb /#deb /", "/etc/apt/sources.list"],
                30,
                True,
                "disable legacy online sources.list",
            ),
            _cmd(
                ["sudo", "apt-get", "update"],
                600,
                False,
                "refresh apt against the local mirror",
            ),
        ],
    }


def _file(path: str, content: str) -> dict:
    return {"path": path, "content": content, "permissions": "0644",
            "owner_uid": 0, "owner_gid": 0}  # fmt: skip


def _build_dnf_repoint_plan(repo_url: str) -> dict:
    """Point dnf at the local mirror (Fedora, EL) and disable every other
    repository.  The mirror keeps the distribution's signed packages, so
    ``gpgcheck`` stays on.  Every repository is disabled with dnf's own
    command and then ours enabled again -- the file is deployed before the
    commands run, so the first would take ours too; dnf 4 and dnf 5 spell
    it differently, and each step ignores the other's error."""
    repo = (
        "[sysmanage-airgap]\n"
        "name=SysManage air-gap repository\n"
        f"baseurl={repo_url}\n"
        "enabled=1\n"
        "gpgcheck=1\n"
    )
    return {
        "files": [_file("/etc/yum.repos.d/sysmanage-airgap.repo", repo)],
        "commands": [
            _cmd(["sudo", "dnf", "config-manager", "--set-disabled", "*"], 60, True,
                 "disable every upstream repository (dnf 4)"),  # fmt: skip
            _cmd(["sudo", "dnf", "config-manager", "setopt", "*.enabled=0"], 60, True,
                 "disable every upstream repository (dnf 5)"),  # fmt: skip
            _cmd(["sudo", "dnf", "config-manager", "--set-enabled", "sysmanage-airgap"],
                 60, True, "enable the local mirror (dnf 4)"),  # fmt: skip
            _cmd(["sudo", "dnf", "config-manager", "setopt", "sysmanage-airgap.enabled=1"],
                 60, True, "enable the local mirror (dnf 5)"),  # fmt: skip
            _cmd(["sudo", "dnf", "makecache"], 600, False,
                 "refresh dnf against the local mirror"),  # fmt: skip
        ],
    }


def _build_zypper_repoint_plan(repo_url: str) -> dict:
    """Point zypper at the local mirror (openSUSE, SLES) and disable the rest."""
    repo = (
        "[sysmanage-airgap]\n"
        "name=SysManage air-gap repository\n"
        "enabled=1\n"
        "autorefresh=1\n"
        f"baseurl={repo_url}\n"
        "type=rpm-md\n"
        "gpgcheck=1\n"
    )
    return {
        "files": [_file("/etc/zypp/repos.d/sysmanage-airgap.repo", repo)],
        "commands": [
            _cmd(["sudo", "zypper", "--non-interactive", "modifyrepo", "--all",
                  "--disable"], 60, True, "disable every upstream repository"),  # fmt: skip
            _cmd(["sudo", "zypper", "--non-interactive", "modifyrepo", "--enable",
                  "sysmanage-airgap"], 60, False, "enable the local mirror"),  # fmt: skip
            _cmd(["sudo", "zypper", "--non-interactive", "refresh"], 600, False,
                 "refresh zypper against the local mirror"),  # fmt: skip
        ],
    }


def _build_apk_repoint_plan(repo_url: str) -> dict:
    """Point apk at the local mirror (Alpine): the mirror becomes the only
    line of /etc/apk/repositories, which every apk reads; the mirror keeps
    Alpine's signed indexes, checked against the keys the host has."""
    return {
        "files": [_file("/etc/apk/repositories", f"{repo_url}\n")],
        "commands": [
            _cmd(["sudo", "apk", "update"], 600, False,
                 "refresh apk against the local mirror"),  # fmt: skip
        ],
    }


def _build_pkg_repoint_plan(repo_url: str) -> dict:
    """Point pkg at the local mirror (FreeBSD) and switch the FreeBSD
    repositories off, the way pkg.conf(5) says: a file under
    /usr/local/etc/pkg/repos naming each with ``enabled: no``.  The mirror
    keeps the project's signed catalog, checked with its fingerprints."""
    ours = (
        "sysmanage-airgap: {\n"
        f'  url: "{repo_url}",\n'
        '  signature_type: "fingerprints",\n'
        '  fingerprints: "/usr/share/keys/pkg",\n'
        "  enabled: yes\n"
        "}\n"
    )
    off = "FreeBSD: { enabled: no }\nFreeBSD-kmods: { enabled: no }\n"
    return {
        "files": [
            _file("/usr/local/etc/pkg/repos/sysmanage-airgap.conf", ours),
            _file("/usr/local/etc/pkg/repos/FreeBSD.conf", off),
        ],
        "commands": [
            _cmd(["sudo", "pkg", "update"], 600, False,
                 "refresh pkg against the local mirror"),  # fmt: skip
        ],
    }


# The SysManage tools repository (services/airgap_tools.py, 25.9): the
# agent, restate and restate-proxy, signed with the site's own key.
TOOLS_APT_KEY = "/usr/share/keyrings/sysmanage-tools.asc"
TOOLS_RPM_KEY = "/etc/pki/rpm-gpg/RPM-GPG-KEY-sysmanage-tools"
TOOLS_PKG_KEY = "/usr/local/etc/pkg/keys/sysmanage-tools.pub"


def tools_url(repo_url: str, distro: str, version: str) -> str:
    """The tools repository beside a mirror: same server, /airgap-tools/."""
    parts = urlsplit(repo_url)
    return f"{parts.scheme}://{parts.netloc}/airgap-tools/{distro}/{version}"


def _with_tools(kind: str, plan: dict, url: str, key: str) -> dict:
    """``plan`` with the tools repository added beside the mirror: its key
    installed as a file, the repository checked against it (apt signed-by;
    dnf and zypper repo_gpgcheck -- the index is signed, its packages are
    checked through it), and enabled after the mirror's own steps switch
    the others off."""
    files = list(plan.get("files") or [])
    commands = list(plan.get("commands") or [])
    if kind == "apt":
        files += [_file(TOOLS_APT_KEY, key), _file(
            "/etc/apt/sources.list.d/sysmanage-tools.list",
            f"deb [signed-by={TOOLS_APT_KEY}] {url} ./\n")]  # fmt: skip
    elif kind in ("dnf", "zypper"):
        repo = ("[sysmanage-tools]\nname=SysManage tools\n"
                f"baseurl={url}\nenabled=1\ngpgcheck=0\nrepo_gpgcheck=1\n"
                f"gpgkey=file://{TOOLS_RPM_KEY}\n")  # fmt: skip
        folder = "/etc/yum.repos.d" if kind == "dnf" else "/etc/zypp/repos.d"
        files += [
            _file(TOOLS_RPM_KEY, key),
            _file(f"{folder}/sysmanage-tools.repo", repo),
        ]
        refresh = commands.pop() if commands else None
        if kind == "dnf":
            commands += [
                _cmd(["sudo", "dnf", "config-manager", "--set-enabled", "sysmanage-tools"],
                     60, True, "enable the SysManage tools repository (dnf 4)"),
                _cmd(["sudo", "dnf", "config-manager", "setopt", "sysmanage-tools.enabled=1"],
                     60, True, "enable the SysManage tools repository (dnf 5)"),
            ]  # fmt: skip
        else:
            commands += [
                _cmd(["sudo", "zypper", "--non-interactive", "modifyrepo", "--enable",
                      "sysmanage-tools"], 60, False, "enable the SysManage tools repository"),
            ]  # fmt: skip
            # zypper takes the key from the repository's own gpgkey= (the
            # file deployed above): sudoers grants it no ``rpm --import``.
            refresh = _cmd(["sudo", "zypper", "--non-interactive", "--gpg-auto-import-keys",
                            "refresh"], 600, False, "refresh zypper against the local mirror")  # fmt: skip
        if refresh:
            commands.append(refresh)
    elif kind == "apk":
        # apk reads one repositories file: the mirror's line, then ours; the
        # key goes by the name the index's signature names.
        name = _apk_key_name(key)
        files = [f for f in files if f["path"] != "/etc/apk/repositories"]
        mirror = next(
            f["content"] for f in plan["files"] if f["path"] == "/etc/apk/repositories"
        )
        files += [_file(f"/etc/apk/keys/{name}.rsa.pub", key),
                  _file("/etc/apk/repositories", mirror + f"{url}\n")]  # fmt: skip
    elif kind == "pkg":
        conf = ("sysmanage-tools: {\n"
                f'  url: "{url}",\n'
                '  signature_type: "pubkey",\n'
                f'  pubkey: "{TOOLS_PKG_KEY}",\n'
                "  enabled: yes\n}\n")  # fmt: skip
        files += [_file(TOOLS_PKG_KEY, key),
                  _file("/usr/local/etc/pkg/repos/sysmanage-tools.conf", conf)]  # fmt: skip
    else:
        return plan
    return {**plan, "files": files, "commands": commands}


def _apk_key_name(public_pem: str) -> str:
    # pylint: disable-next=import-outside-toplevel
    from backend.services.airgap_tools_formats import key_name  # noqa: PLC0415

    return key_name(public_pem.encode("ascii"))


def repoint_plan(distro: str, repo_url: str, suite: str) -> Optional[tuple]:
    """``(kind, plan)`` for the mirror's distribution, or None where there
    is no package manager to point."""
    distro = (distro or "").lower()
    if any(d in distro for d in _APT_DISTROS):
        return "apt", _build_apt_repoint_plan(repo_url, suite, _DEFAULT_COMPONENTS)
    if any(d in distro for d in _DNF_DISTROS):
        return "dnf", _build_dnf_repoint_plan(repo_url)
    if any(d in distro for d in _ZYPPER_DISTROS):
        return "zypper", _build_zypper_repoint_plan(repo_url)
    if any(d in distro for d in _APK_DISTROS):
        return "apk", _build_apk_repoint_plan(repo_url)
    if any(d in distro for d in _PKG_DISTROS):
        return "pkg", _build_pkg_repoint_plan(repo_url)
    return None


def _agent_distro_hint(host) -> str:
    """Lowercased blob of the host's OS fields, for substring matching."""
    parts = [
        getattr(host, "platform", "") or "",
        getattr(host, "platform_release", "") or "",
        getattr(host, "platform_version", "") or "",
        getattr(host, "os_details", "") or "",
    ]
    return " ".join(parts).lower()


def _pick_repo(db, host) -> Optional["models.AirgapLocalRepository"]:
    """Choose which mirror repo to point this agent at.

    Single repo → use it (the common single-distro air-gap enclave).
    Multiple → match the agent's OS string against a repo's distro.
    None match → None (skip; don't push a wrong-distro source).
    """
    rows = db.query(models.AirgapLocalRepository).all()
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    hint = _agent_distro_hint(host)
    for row in rows:
        if row.distro and row.distro.lower() in hint:
            return row
    return None


def _tools_for(repo) -> Optional[tuple]:
    """``(url, public key)`` of the signed tools repository for this mirror's
    distribution and release, when the last ingest built one."""
    # pylint: disable=import-outside-toplevel
    from backend.services import airgap_tools  # noqa: PLC0415
    from backend.services.airgap_ingest_tick import REPO_ROOT  # noqa: PLC0415

    if not airgap_tools.served(REPO_ROOT, repo.distro, repo.version):
        return None
    key = airgap_tools.public_key(REPO_ROOT, airgap_tools.family(repo.distro) or "apt")
    if not key:
        return None
    return tools_url(repo.repo_url, repo.distro, repo.version), key


def maybe_repoint(db, host, _connection_send=None) -> None:
    """Repoint ``host`` at the mirror if needed.  Best-effort; never raises.

    Called for every inbound agent message.  No-ops unless this server is
    a repository, the agent is an apt-family distro, and the config it
    would push differs from what we last pushed this host.
    """
    try:
        if server_config_service.get_server_role() != "repository":
            return
        repo = _pick_repo(db, host)
        if repo is None or not repo.repo_url:
            return

        distro = (repo.distro or "").lower()
        suite = repo.version
        components = _DEFAULT_COMPONENTS
        found = repoint_plan(distro, repo.repo_url, suite)
        if found is None:
            return
        kind, plan = found
        tools = _tools_for(repo)
        if tools:
            plan = _with_tools(kind, plan, *tools)

        host_id = str(host.id)
        signature = hashlib.sha256(
            f"{kind}|{repo.repo_url}|{suite}|{components}|{tools}".encode("utf-8")
        ).hexdigest()
        if _LAST_REPOINT.get(host_id) == signature:
            return  # already repointed with this exact config

        from backend.services.proplus_dispatch import (
            enqueue_apply_plan,
        )  # pylint: disable=import-outside-toplevel

        enqueue_apply_plan(host_id=host_id, plan=plan, timeout=600)
        _LAST_REPOINT[host_id] = signature
        logger.info(
            "Repointed agent %s (%s) at mirror %s", host_id, distro, repo.repo_url
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # Repoint must never disrupt inbound message processing.
        logger.warning("maybe_repoint failed for host", exc_info=True)
