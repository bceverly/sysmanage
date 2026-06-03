"""Auto-repoint managed agents at the local air-gap mirror.

When this server runs as an Air-Gap Repository, every agent that talks
to it should have its package manager pointed at this server's mirror
(and its online sources disabled) so it can never reach the internet.

This module is called from the inbound message path (see
``inbound_processor``) so the directive propagates on the very next
communication cycle after the server's role is set to ``repository`` —
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
``enqueue_apply_plan`` path the ingest mount/copy plans use — the agent
already knows how to execute these command plans, so no agent change.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict, Optional

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


def _cmd(argv, timeout, ignore_errors, description):
    return {
        "argv": argv,
        "timeout": timeout,
        "ignore_errors": ignore_errors,
        "description": description,
    }


def _build_apt_repoint_plan(repo_url: str, suite: str, components: str) -> dict:
    """Point apt at the local mirror and disable upstream sources.

    Mirrors the validated repoint flow: write a single deb source for
    the mirror, disable the (unreachable) online sources, then refresh.
    The mirror's InRelease is the genuine Ubuntu-signed metadata copied
    verbatim, so apt verifies it against the host keyring — no
    ``[trusted=yes]`` needed.
    """
    deb_line = f"deb {repo_url} {suite} {components}\n"
    list_path = "/etc/apt/sources.list.d/sysmanage-airgap.list"
    return {
        "commands": [
            _cmd(
                ["sudo", "sh", "-c", f"printf %s {_shq(deb_line)} > {list_path}"],
                30,
                False,
                "write sysmanage-airgap apt source",
            ),
            # Disable the deb822 OS sources (resolute+) if present.
            _cmd(
                [
                    "sudo",
                    "sh",
                    "-c",
                    "test -f /etc/apt/sources.list.d/ubuntu.sources && "
                    "mv /etc/apt/sources.list.d/ubuntu.sources "
                    "/etc/apt/sources.list.d/ubuntu.sources.disabled || true",
                ],
                30,
                True,
                "disable upstream ubuntu.sources",
            ),
            # Comment out any active deb lines in the legacy sources.list.
            _cmd(
                [
                    "sudo",
                    "sh",
                    "-c",
                    "test -f /etc/apt/sources.list && "
                    "sed -i 's/^deb /#deb /' /etc/apt/sources.list || true",
                ],
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
        ]
    }


def _shq(value: str) -> str:
    """Minimal single-quote shell-quote for embedding in sh -c."""
    return "'" + value.replace("'", "'\\''") + "'"


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


def maybe_repoint(db, host, connection_send=None) -> None:
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
        if distro in _APT_DISTROS:
            suite = repo.version
            components = _DEFAULT_COMPONENTS
            plan = _build_apt_repoint_plan(repo.repo_url, suite, components)
            kind = "apt"
        else:
            # Other package managers (dnf/zypper/apk/pkg) not wired yet —
            # the device/ingest path supports them, repoint is apt-first.
            return

        host_id = str(host.id)
        signature = hashlib.sha256(
            f"{kind}|{repo.repo_url}|{suite}|{components}".encode("utf-8")
        ).hexdigest()
        if _LAST_REPOINT.get(host_id) == signature:
            return  # already repointed with this exact config

        from backend.services.proplus_dispatch import (  # pylint: disable=import-outside-toplevel
            enqueue_apply_plan,
        )

        enqueue_apply_plan(host_id=host_id, plan=plan, timeout=600)
        _LAST_REPOINT[host_id] = signature
        logger.info(
            "Repointed agent %s (%s) at mirror %s", host_id, distro, repo.repo_url
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # Repoint must never disrupt inbound message processing.
        logger.warning("maybe_repoint failed for host", exc_info=True)
