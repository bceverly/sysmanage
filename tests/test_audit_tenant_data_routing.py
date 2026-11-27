# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tenant data is audited in the tenant's own log (2026-11-27).

Firewall roles, antivirus defaults, repositories, package managers and
compliance profiles, dynamic secrets, asset tags and discovery, report
branding and templates, time sync, hardware health, Ubuntu Pro and iCloud
backups were audited as ``setting``, which the audit service routes to the
server-wide database, so none of them showed in the tenant's audit view.
They use the entity they are about now, or ``configuration`` for a tenant's
own settings.  The server's settings (server role, CVE feeds, user
preferences, the antivirus swap switch ...) stay ``setting``.

Also: the audit page's Entity Type filter sends ``HOST`` while entries are
stored ``host``, so it never matched anything; it compares case-insensitively.
"""

# pylint: disable=protected-access

import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.api import audit_log
from backend.persistence import models
from backend.services import audit_service
from backend.services.audit_service import EntityType

BACKEND = Path(__file__).resolve().parents[1] / "backend"

TENANT_DATA = (
    "api/antivirus_defaults.py",
    "api/asset_discovery.py",
    "api/asset_tags.py",
    "api/cloud_backup.py",
    "api/default_repositories.py",
    "api/dynamic_secrets.py",
    "api/enabled_package_managers.py",
    "api/firewall_roles.py",
    "api/hardware_health.py",
    "api/package_compliance.py",
    "api/report_branding.py",
    "api/report_templates.py",
    "api/time_sync.py",
    "api/time_sync_policy.py",
    "api/ubuntu_pro_settings.py",
    "services/cloud_backup_tick.py",
)
# antivirus_defaults keeps ONE: the swap switch is a server setting.
SERVER_SETTINGS_LEFT = {"api/antivirus_defaults.py": 1}


def _route(entity_type):
    bootstrap, tenant = MagicMock(name="bootstrap"), MagicMock(name="tenant")
    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch("backend.persistence.db.get_engine", return_value=bootstrap), patch.object(
        audit_service, "_bind_of", return_value=tenant
    ):
        target = audit_service._target_engine(MagicMock(), "UPDATE", entity_type)
    return target, bootstrap


def test_a_tenant_configuration_entry_stays_in_the_tenant_database():
    target, _bootstrap = _route(EntityType.CONFIGURATION.value)
    assert target is None


def test_a_server_setting_still_goes_to_the_server_database():
    target, bootstrap = _route(EntityType.SETTING.value)
    assert target is bootstrap


def test_tenant_data_no_longer_audits_as_a_setting():
    for name in TENANT_DATA:
        text = (BACKEND / name).read_text(encoding="utf-8")
        left = text.count("EntityType.SETTING")
        assert left == SERVER_SETTINGS_LEFT.get(name, 0), name


def _entry(session, entity_type):
    session.add(
        models.AuditLog(
            id=uuid.uuid4(), timestamp=datetime(2026, 11, 27, 12, 0),
            action_type="UPDATE", entity_type=entity_type,
            description="x", result="SUCCESS",
        )  # fmt: skip
    )


def test_the_entity_type_filter_matches_whatever_the_case(db_session):
    _entry(db_session, "host")
    _entry(db_session, "backup")
    db_session.commit()
    filters = audit_log.AuditLogFilters(
        user_id=None, action_type=None, entity_type="HOST", result=None,
        category=None, entry_type=None, search=None, start_date=None, end_date=None,
    )  # fmt: skip
    rows = audit_log._apply_audit_filters(
        db_session.query(models.AuditLog), filters
    ).all()
    assert [row.entity_type for row in rows] == ["host"]
