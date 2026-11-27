# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backups are audited in the tenant's own log (2026-11-27).

Backup targets, policies, keys and escrow, approvals, restores and the
off-site cloud copy were audited as ``setting``, which the audit service
routes to the server-wide database: production's cloud copy setup, bucket
check and key export never showed in the tenant's audit view.  They are
``backup`` now, tenant data like a host.
"""

# pylint: disable=protected-access

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.services import audit_service
from backend.services.audit_service import EntityType

BACKUP_CODE = (
    "api/backups.py",
    "api/backups_escrow.py",
    "api/backups_fleet_restore.py",
    "api/backups_four_eyes.py",
    "api/backups_offsite.py",
    "api/backups_tag_policies.py",
    "api/backups_targets.py",
    "api/backups_transport.py",
    "services/backup_escrow.py",
)


def _route(entity_type):
    bootstrap, tenant = MagicMock(name="bootstrap"), MagicMock(name="tenant")
    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch("backend.persistence.db.get_engine", return_value=bootstrap), patch.object(
        audit_service, "_bind_of", return_value=tenant
    ):
        target = audit_service._target_engine(MagicMock(), "UPDATE", entity_type)
    return target, bootstrap


def test_a_backup_entry_stays_in_the_tenant_database():
    target, _bootstrap = _route(EntityType.BACKUP.value)
    assert target is None  # written to the caller's (tenant) session


def test_the_backup_code_no_longer_audits_as_a_setting():
    root = Path(__file__).resolve().parents[1] / "backend"
    for name in BACKUP_CODE:
        text = (root / name).read_text(encoding="utf-8")
        assert "EntityType.SETTING" not in text, name
