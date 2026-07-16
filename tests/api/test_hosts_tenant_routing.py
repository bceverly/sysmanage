# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests that the hosts list endpoint routes to the active tenant (Phase 13.1).

The endpoint offloads the DB work to a thread pool, so it must capture the
active tenant in the async layer and pass it down (ContextVars don't cross the
thread boundary).
"""

import asyncio
from unittest.mock import patch

from backend.api import host as host_api


def test_get_all_hosts_passes_active_tenant_to_sync():
    captured = {}

    def fake_sync(tenant_id=None):
        captured["tenant_id"] = tenant_id
        return []

    with patch(
        "backend.persistence.tenant_context.get_active_tenant",
        return_value="t-42",
    ), patch.object(host_api, "_get_all_hosts_sync", side_effect=fake_sync):
        result = asyncio.run(host_api.get_all_hosts())

    assert result == []
    # The tenant captured in the async context is handed to the thread worker.
    assert captured["tenant_id"] == "t-42"


def test_get_all_hosts_server_scope_passes_none():
    captured = {}

    def fake_sync(tenant_id=None):
        captured["tenant_id"] = tenant_id
        return []

    with patch(
        "backend.persistence.tenant_context.get_active_tenant",
        return_value=None,
    ), patch.object(host_api, "_get_all_hosts_sync", side_effect=fake_sync):
        asyncio.run(host_api.get_all_hosts())

    assert captured["tenant_id"] is None
