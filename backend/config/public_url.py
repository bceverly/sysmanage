# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The one place that knows the console's externally reachable URL.

WHY THIS EXISTS
---------------
Invitation and password-reset emails carry a link to this console.  Three call
sites built that link independently, and all three built it the same wrong way::

    is_secure = bool(config["api"]["certFile"])
    protocol  = "https" if is_secure else "http"
    url       = f"{protocol}://{hostname}:{webui_port}/..."

Both halves fail once nginx terminates TLS, which is the shipped architecture:

* ``api.certFile`` is unset -- the BACKEND has no certificate, nginx holds it --
  so ``is_secure`` is False and every emailed link says ``http://``.
* ``webui.port`` was 3000, a port nginx no longer listens on.  The link pointed
  at a closed port on a host that only serves 443.

So the practical effect was an invitation email nobody could open.  Neither
mistake is visible from the code that makes it: you have to know how the whole
deployment fits together, which is exactly the knowledge that belongs in one
function instead of three.

CONFIGURATION
-------------
``webui.public_url`` is the answer whenever it is known -- and it is always
known for a SaaS or reverse-proxied deployment, where the name customers use has
nothing to do with the server's own hostname::

    webui:
      public_url: "https://console.example.com"

Without it, the URL is derived: https, the host's best-guess FQDN, and the
port omitted when it is the scheme default.  Derivation is a fallback, not a
feature -- it cannot know a name the server has never been told.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from backend.config.runtime_mode import is_dev_mode

logger = logging.getLogger(__name__)

DEFAULT_PORTS = {"http": 80, "https": 443}


def build_public_base_url(
    app_config: Dict[str, Any],
    hostname_resolver: Optional[Callable[[], str]] = None,
) -> str:
    """Return the console's external base URL, with no trailing slash.

    ``hostname_resolver`` is injected so callers can pass their existing
    FQDN-discovery helper rather than this module growing a second one.
    """
    config = app_config or {}
    webui = config.get("webui") or {}

    explicit = (webui.get("public_url") or "").strip()
    if explicit:
        return explicit.rstrip("/")

    # Derived fallback.  https unless this is explicitly a development box:
    # every shipped nginx configuration serves 443 only and redirects 80 to it,
    # so http would be wrong on a stock install.  The default direction is
    # deliberate -- a forgotten flag must not downgrade a real deployment.
    dev = is_dev_mode(config)
    scheme = "http" if dev else "https"

    host = hostname_resolver() if hostname_resolver else "localhost"

    # In production the console is on 443 and webui.port describes nothing that
    # faces outward, so it is ignored.  In development it IS the Vite port and
    # belongs in the link.
    port = webui.get("port") if dev else None
    try:
        port = int(port) if port is not None else None
    except (TypeError, ValueError):
        logger.warning("webui.port is not a number (%r); ignoring it.", port)
        port = None

    if port is None or port == DEFAULT_PORTS.get(scheme):
        authority = host
    else:
        authority = f"{host}:{port}"

    url = f"{scheme}://{authority}"
    if not explicit:
        logger.debug(
            "webui.public_url is not set; derived %s. Set it explicitly if this "
            "console is reached under a different name.",
            url,
        )
    return url
