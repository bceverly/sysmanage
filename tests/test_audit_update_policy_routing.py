# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic update policies are audited in the tenant's own log (2026-11-17).

Policy changes, holds, Trigger Now, the settings and rollouts were audited
as ``setting``, which the audit service routes to the server-wide database
(a server setting), so none of them showed in the tenant's audit view.  They
are ``update_policy`` now, tenant data like a host.
"""

# pylint: disable=protected-access

from unittest.mock import MagicMock, patch

from backend.services import audit_service
from backend.services.audit_service import EntityType


def _route(entity_type):
    bootstrap, tenant = MagicMock(name="bootstrap"), MagicMock(name="tenant")
    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch("backend.persistence.db.get_engine", return_value=bootstrap), patch.object(
        audit_service, "_bind_of", return_value=tenant
    ):
        target = audit_service._target_engine(MagicMock(), "UPDATE", entity_type)
    return target, bootstrap


def test_an_update_policy_entry_stays_in_the_tenant_database():
    target, _bootstrap = _route(EntityType.UPDATE_POLICY.value)
    assert target is None  # written to the caller's (tenant) session


def test_a_server_setting_still_goes_to_the_server_database():
    target, bootstrap = _route(EntityType.SETTING.value)
    assert target is bootstrap


def test_the_automatic_update_code_no_longer_audits_as_a_setting():
    from pathlib import Path  # pylint: disable=import-outside-toplevel

    root = Path(__file__).resolve().parents[1] / "backend"
    for name in (
        "api/upgrade_profiles.py",
        "api/auto_updates.py",
        "api/auto_update_rollouts.py",
        "services/auto_update_rollout.py",
        "services/auto_update_runner.py",
        "services/auto_update_results.py",
    ):
        assert "EntityType.SETTING" not in (root / name).read_text(), name
