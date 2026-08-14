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

WHY A WARNING AND NOT A REFUSAL
-------------------------------
A wildcard bind is legitimate in real cases: development without a reverse
proxy, a container that publishes its own port, or a deployment that terminates
TLS somewhere else entirely.  Refusing to start would break those, and a
security control that stops people working gets disabled rather than
understood.  So this is loud, actionable, and silenceable BY ACKNOWLEDGEMENT
rather than by turning the check off -- setting ``api.allow_public_bind: true``
records that somebody decided this on purpose.
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
        return configured if configured else "localhost"

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

    # Loud on purpose.  This is the one line that turns an internal port into a
    # publicly reachable, unauthenticated enrollment endpoint.
    log.warning(
        "SECURITY: api.host is %r, so the API is listening on ALL interfaces "
        "(port %s). SysManage expects nginx to terminate TLS on 443 and reach "
        "the API on loopback, so a wildcard bind publishes the API directly -- "
        "bypassing TLS, the security headers and the upgrade validation that "
        "live in the nginx configuration. Agent registration is unauthenticated "
        "by design, so this exposes an open enrollment endpoint in cleartext. "
        "Set api.host to 'localhost' unless you know you need otherwise; if you "
        "do, set api.allow_public_bind: true to record that it is intentional "
        "and silence this warning.",
        host,
        port,
    )
    return True
