# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The canary is its own program (canary/), importable without the server."""

import os
import sys

CANARY = os.path.join(os.path.dirname(__file__), "..", "..", "canary")
if CANARY not in sys.path:
    sys.path.insert(0, os.path.abspath(CANARY))
