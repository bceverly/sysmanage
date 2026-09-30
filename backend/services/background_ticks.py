# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Start the license-gated background ticks from ONE startup call.

``startup/lifecycle.py`` sits at the 1000-line budget, so a new tick cannot
add its own import and call there. Each tick owns its gate and its error
handling in a ``start_if_licensed()``; this only calls them in turn.
"""

from backend.services import advisor_tick, malware_tick, network_discovery_policy


def start_licensed_ticks():
    """Start every licensed tick; returns the tasks (None where not licensed)."""
    return [
        advisor_tick.start_if_licensed(),  # 21.2 advisor evaluation
        network_discovery_policy.start_if_licensed(),  # 21.6 discovery policy
        malware_tick.start_if_licensed(),  # 21.3 malware rule feed
    ]
