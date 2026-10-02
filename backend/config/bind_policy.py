# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Warn when the API is bound somewhere the internet can reach it.

WHY THIS EXISTS
---------------
SysManage's shipped architecture puts nginx on 80/443 and the API on loopback
8080.  nginx terminates TLS, serves the web UI at ``/``, and proxies ``/api/``
and ``/ws`` to ``127.0.0.1:8080``.  Every server template ships
``api.host: "localhost"`` and nginx is a hard package dependency, so a correct
install exposes exactly one port and the Python application never faces the
internet.

Change ``api.host`` to a wildcard and that quietly stops being true.  The API
becomes directly reachable, bypassing nginx -- and with it the TLS termination,
the security headers and the upgrade-request validation that live in the nginx
config.  Registration is unauthenticated by design (a new agent has no
credentials yet), so an exposed 8080 is an unauthenticated enrollment endpoint
on the public internet, served in cleartext.

Nothing used to say so.  The value sat in a YAML file, the server started
happily, and the only symptom was that pointing an agent at port 8080 "worked"
-- which is exactly how agent configuration templates came to be written
against the back door instead of the front one.

WHY LOOPBACK AND NOT A REFUSAL
------------------------------
In production an unacknowledged wildcard binds loopback instead (2026-10-02,
Bryan: nginx is the only thing facing the network).  The server still starts
and nginx still reaches it, and a loud warning says what was asked for and
what was done.  Until then this only warned -- safe while most service files
forced the address on the uvicorn command line, not once every launcher reads
api.host.  A wildcard bind IS legitimate in real cases -- development without
a reverse proxy, a container publishing its own port, TLS terminated somewhere
else -- so it stays possible BY ACKNOWLEDGEMENT: ``api.allow_public_bind:
true`` records that somebody decided this on purpose.  Dev mode binds every
interface as before.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.config.runtime_mode import is_dev_mode

logger = logging.getLogger(__name__)

# Values that mean "every interface".  The empty string is included because
# some stacks treat a missing host as a wildcard, and "*" because people write
# it expecting it to work.
WILDCARD_HOSTS = frozenset(
    {"0.0.0.0", "::", "[::]", "*", ""}  # nosec B104 - compared against, never bound
)

# Hosts that are unambiguously local-only and never worth a warning.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


def is_wildcard_bind(host: Optional[str]) -> bool:
    """Does ``host`` mean "listen on every interface"?"""
    if host is None:
        return True
    return str(host).strip().lower() in WILDCARD_HOSTS


def is_loopback_bind(host: Optional[str]) -> bool:
    """Is ``host`` unambiguously loopback-only?"""
    if host is None:
        return False
    return str(host).strip().lower() in LOOPBACK_HOSTS


def resolve_api_bind_host(app_config: Dict[str, Any]) -> str:
    """The address the API should actually bind, given the mode.

    Production keeps whatever is configured, which the templates set to
    ``localhost`` -- nginx reaches it over loopback and nothing else should.

    Development binds every interface instead, because the point of dev mode is
    to have things connect to it: an agent on this same machine AND agents on
    other boxes on the LAN, without anyone first discovering that the reason
    their laptop cannot reach the server is a bind address in a YAML file they
    have never opened.  There is no reverse proxy in dev, so the API IS the
    endpoint, and a loopback bind makes it unreachable by definition.

    A deliberately chosen non-loopback address is respected as-is -- that is
    someone who knows exactly which interface they want.
    """
    api = (app_config or {}).get("api") or {}
    configured = api.get("host")

    if not is_dev_mode(app_config):
        if not configured:
            return "localhost"
        # Production: nginx is the only thing that faces the network (Bryan,
        # 2026-10-02).  A wildcard nobody acknowledged binds loopback instead
        # -- the server still starts and nginx still reaches it.  This used to
        # only warn, which was safe while most service files forced the
        # address on the uvicorn command line; now that every launcher reads
        # api.host, an old "0.0.0.0" in a config would have published the API.
        if is_wildcard_bind(configured) and not api.get("allow_public_bind"):
            return "127.0.0.1"
        return configured

    if (
        configured
        and not is_loopback_bind(configured)
        and not is_wildcard_bind(configured)
    ):
        return configured

    return "0.0.0.0"  # nosec B104 - dev mode only; see the docstring


def check_api_bind(app_config: Dict[str, Any], log: logging.Logger = None) -> bool:
    """Warn if the API is bound to a public interface.  Returns True if it is.

    Called once at startup.  Never raises and never prevents startup: see the
    module docstring for why this is a warning rather than a refusal.
    """
    log = log or logger
    api = (app_config or {}).get("api") or {}
    port = api.get("port")

    # Report on what will ACTUALLY be bound, not on what the file says.  Dev
    # mode upgrades a loopback default to every interface, and a startup line
    # claiming "localhost" while the socket answers on 0.0.0.0 would be worse
    # than no line at all.
    host = resolve_api_bind_host(app_config)
    configured = api.get("host")
    if (
        configured
        and is_wildcard_bind(configured)
        and is_loopback_bind(host)
        and not is_dev_mode(app_config)
    ):
        # Loud on purpose: the config asked for every interface and did not get it.
        log.warning(
            "SECURITY: api.host is %r, but the API is bound to %s:%s instead. "
            "nginx terminates TLS on 443 and reaches the API on loopback; a "
            "wildcard bind would publish the API directly -- bypassing TLS, "
            "the security headers and the upgrade validation in the nginx "
            "configuration, with agent registration (unauthenticated by "
            "design) open in cleartext. Set api.host to 'localhost' to silence "
            "this; to really serve the API directly, set "
            "api.allow_public_bind: true.",
            configured,
            host,
            port,
        )
        return False

    if not is_wildcard_bind(host):
        if not is_loopback_bind(host):
            # A specific non-loopback address: deliberate enough not to nag
            # about, but worth a breadcrumb when someone is reading logs to
            # work out why the API is reachable.
            log.info(
                "API bound to %s:%s (a specific interface, not loopback).", host, port
            )
        return False

    if is_dev_mode(app_config):
        # Development runs without a reverse proxy, so binding every interface
        # is how you reach it from another machine.  Say it once, quietly: the
        # warning below is about production, and crying wolf on every dev start
        # is how people learn to ignore it.
        log.info("API bound to %s:%s on all interfaces (dev_mode is on).", host, port)
        return True

    if api.get("allow_public_bind"):
        log.info(
            "API bound to %s:%s on all interfaces; allow_public_bind is set, "
            "so this was deliberate.",
            host,
            port,
        )
        return True

    # Unreachable in production (resolve_api_bind_host binds loopback instead
    # of an unacknowledged wildcard); kept for callers that pass a resolved
    # wildcard some other way.
    log.warning(
        "SECURITY: the API is listening on ALL interfaces (port %s) without "
        "api.allow_public_bind -- it should be behind nginx on loopback.",
        port,
    )
    return True
