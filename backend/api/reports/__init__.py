# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Reports API module - Split from monolithic reports.py for better maintainability
"""

from backend.api.reports.endpoints import router

__all__ = ["router"]
