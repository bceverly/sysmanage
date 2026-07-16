# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
OpenTelemetry deployment API endpoints for SysManage.

This module provides functionality for:
- Checking OpenTelemetry eligibility
- Deploying and removing OpenTelemetry
- Checking OpenTelemetry status
- Starting, stopping, and restarting OpenTelemetry services
- Connecting and disconnecting OpenTelemetry to/from Grafana
"""

from fastapi import APIRouter

from . import deployment, eligibility, grafana_connection, service_control, status

# Create a single router that includes all sub-routers
router = APIRouter()

# Include all sub-routers
router.include_router(eligibility.router)
router.include_router(deployment.router)
router.include_router(status.router)
router.include_router(service_control.router)
router.include_router(grafana_connection.router)

# Export the combined router
__all__ = ["router"]
