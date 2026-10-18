# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Start the license-gated background ticks from ONE startup call.

``startup/lifecycle.py`` sits at the 1000-line budget, so a new tick cannot
add its own import and call there. Each tick owns its gate and its error
handling in a ``start_if_licensed()``; this only calls them in turn.
"""

from backend.services import (
    advisor_tick,
    compliance_scan_tick,
    hardware_tick,
    malware_tick,
    network_discovery_policy,
    os_lifecycle_tick,
)


def start_licensed_ticks():
    """Start every licensed tick; returns the tasks (None where not licensed)."""
    return [
        advisor_tick.start_if_licensed(),  # 21.2 advisor evaluation
        network_discovery_policy.start_if_licensed(),  # 21.6 discovery policy
        malware_tick.start_if_licensed(),  # 21.3 malware rule feed
        hardware_tick.start_if_licensed(),  # 23.1 smartmontools auto-install
        os_lifecycle_tick.start_if_licensed(),  # 14.3 EOL registry refresh
        compliance_scan_tick.start_if_licensed(),  # 24.4 scheduled compliance scan
    ]
