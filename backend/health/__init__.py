# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
SysManage Pro+ Health Analysis Module.

Provides AI-powered health analysis for hosts using the health_engine Cython module.
"""

from backend.health.health_service import health_service

__all__ = ["health_service"]
