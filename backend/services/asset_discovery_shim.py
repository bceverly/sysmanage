# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Delegate unenrolled-asset judgment to the licensed engine (Phase 21.6 S1).

The tables are open-source (``models/asset_discovery.py``); deciding what a
sighting IS -- which device, whether it is managed, what it says about itself
-- is Enterprise, in ``asset_discovery_engine``. This is the thin shim, shaped
like ``query_pack_shim``.

WHY IT FAILS CLOSED
-------------------
Without the engine nothing is stored at all. Storing raw, uncorrelated
sightings would fill the table with every managed host on the network marked
"unmanaged" -- a review page that is wrong on day one is worse than none, and
an unlicensed install must not quietly accumulate rows nobody can view.
"""

import logging

from backend.licensing.module_loader import module_loader

logger = logging.getLogger(__name__)

ENGINE_CODE = "asset_discovery_engine"


def engine():
    """The loaded engine, or None."""
    return module_loader.get_module(ENGINE_CODE)


def engine_available() -> bool:
    """Is the engine loaded? Unlicensed and not-loaded look the same here."""
    return engine() is not None
