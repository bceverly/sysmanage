# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The real client address behind a reverse proxy (Phase 22.2).

``X-Forwarded-For`` is written by whoever sends the request, so it may only
be believed when the request came from a proxy we trust -- and then only the
part that proxy appended: walk the list from the RIGHT, skipping trusted
proxies; the first address that is not one of ours is the client.  Reading
the LEFT-most entry (what the API rate limiter did) lets any client choose
the address it is limited under.

Trusted proxies come from ``security.trusted_proxies`` (addresses or CIDR
ranges).  The default trusts loopback only: the installers put nginx on the
same machine, proxying to 127.0.0.1.
"""

import ipaddress
import logging
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_TRUSTED_PROXIES = ("127.0.0.1/32", "::1/128")


def _networks(entries: Iterable[str]) -> List:
    networks = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(str(entry).strip(), strict=False))
        except ValueError:
            logger.warning(
                "security.trusted_proxies: ignoring %r (not an address)", entry
            )
    return networks


def trusted_proxies(app_config: Optional[dict] = None) -> List:
    """The configured trusted proxy networks."""
    if app_config is None:
        from backend.config import config  # pylint: disable=import-outside-toplevel

        app_config = config.get_config()
    configured = (app_config.get("security") or {}).get("trusted_proxies")
    if configured is None:
        configured = DEFAULT_TRUSTED_PROXIES
    elif isinstance(configured, str):
        configured = [configured]
    return _networks(configured)


def _is_trusted(address: str, networks) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def client_address(
    peer: Optional[str], forwarded_for: Optional[str], networks=None
) -> str:
    """The client's address: ``peer`` unless it is a trusted proxy, in which
    case the right-most ``X-Forwarded-For`` entry that is not a trusted proxy."""
    peer = peer or "unknown"
    networks = trusted_proxies() if networks is None else networks
    if not forwarded_for or not _is_trusted(peer, networks):
        return peer
    for hop in reversed([part.strip() for part in forwarded_for.split(",")]):
        if not hop:
            continue
        try:
            ipaddress.ip_address(hop)
        except ValueError:
            return peer  # garbage in the header: fall back to what we saw
        if not _is_trusted(hop, networks):
            return hop
    return peer


def request_client_address(request) -> str:
    """``client_address`` for a Starlette Request or WebSocket."""
    peer = request.client.host if request.client else None
    return client_address(peer, request.headers.get("x-forwarded-for"))
