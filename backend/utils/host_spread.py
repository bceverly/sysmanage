# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A host's fixed place in a spread-out schedule (Phase 22.3).

Work the server pushes to the fleet on a schedule -- retries, daily refreshes
-- was due for every host at the same moment, so it went out to the whole
fleet at once.  ``host_offset`` gives each host a number in [0, 1) derived from
its id: add ``offset x window`` to the host's due time and the fleet spreads
evenly over the window.  It is a hash, not a random draw, so a host's due time
does not move from one tick to the next (or across restarts).
"""

import hashlib
from typing import Any


def host_offset(host_id: Any) -> float:
    """A fixed number in [0, 1) for this host."""
    if host_id is None:
        return 0.0
    digest = hashlib.sha256(str(host_id).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 2**32
