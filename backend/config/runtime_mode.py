# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Is this a development box or a real deployment?

WHY ONE FLAG
------------
Production and development disagree about several things at once, and deriving
each of them separately is how they end up disagreeing with each other:

===================  ===========================  ==========================
                     production (default)         dev_mode: true
===================  ===========================  ==========================
served on            nginx 443 (80 redirects)     Vite 3000, backend 8080
TLS                  yes, nginx holds the cert    no
emailed links        https://host                 http://host:3000
api.host wildcard    warned about loudly          expected, not warned about
===================  ===========================  ==========================

Every one of those follows from a single question -- "is there a reverse proxy
with a certificate in front of this?" -- so it is asked once, here.

THE DEFAULT IS PRODUCTION
-------------------------
An absent flag means production: 443, TLS, no port in URLs.  That direction
matters.  A missing or misspelt setting should fail toward the SECURE
configuration, where the worst case is a link that redirects; defaulting to dev
would mean a forgotten flag silently downgrades a real deployment to plaintext.
"""

from __future__ import annotations

from typing import Any, Dict

# Accepted spellings.  ``dev_mode`` at the top level is the documented one; the
# others are tolerated because they are what people type, and a flag that
# silently does nothing because it was written ``development: true`` is worse
# than one that is slightly permissive.
_DEV_KEYS = ("dev_mode", "development_mode", "development")


def is_dev_mode(app_config: Dict[str, Any]) -> bool:
    """True when this instance is a development box with no TLS front end."""
    config = app_config or {}
    for key in _DEV_KEYS:
        if key in config:
            return _truthy(config[key])
    return False


def _truthy(value: Any) -> bool:
    """YAML gives real booleans, but a quoted "true" should still count."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "on", "1")
    return bool(value)
