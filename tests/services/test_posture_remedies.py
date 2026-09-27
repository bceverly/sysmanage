# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Closing the loop (21.4 S5): remedies for open posture items.

The properties: a preview is exactly what apply does; only OPEN items, and
under multi-tenancy never a server-managed one for a tenant; guided and
manual remedies never pretend to automate; a fleet remedy touches only the
FAILING (and freshly reported) hosts, keeps going past one that fails, and
every application is audited and leaves an event; a setting write that
fails is an error, never a silent success.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import posture_remedies as pr
from backend.services import posture_service as ps

NOW = datetime.now(timezone.utc).replace(tzinfo=None)


class Admin:
    id = None
    userid = "admin@sysmanage.org"


@pytest.fixture
def factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with patch.object(pr, "_main_session", maker), patch.object(
        pr, "_multitenant", return_value=False
    ):
        yield maker
    engine.dispose()


def _item(db, state="open", managed_by="tenant", key="PM-X"):
    item = models.PostureItem(
        **ps.SCOPE,
        rule_source="shared",
        rule_key=key,
        state=state,
        outcome="fires",
        managed_by=managed_by,
        rule_version=1
    )
    db.add(item)
    db.flush()
    return item


def _host(db, name, fw_enabled=None, fw_age=timedelta(hours=1)):
    host = models.Host(
        id=uuid.uuid4(), fqdn=name, active=True, approval_status="approved"
    )
    db.add(host)
    db.flush()
    if fw_enabled is not None:
        db.add(
            models.FirewallStatus(
                host_id=host.id,
                firewall_name="ufw",
                enabled=fw_enabled,
                last_updated=NOW - fw_age,
            )
        )
    return host


@pytest.mark.parametrize(
    "remedy,kind,reason",
    [
        ("configure_alerting", "guided", "not_automated"),
        ("set_password_policy", "none", "not_automated"),
        ("teleport", None, "unknown_remedy"),
    ],
)
def test_guided_manual_and_unknown_remedies_never_pretend_to_automate(
    factory, remedy, kind, reason
):
    with factory() as db:
        plan = pr.preview(db, _item(db), {"remedy": remedy})
    assert (plan["kind"], plan["available"], plan["unavailable_reason"]) == (
        kind,
        False,
        reason,
    )
    if remedy == "configure_alerting":
        assert plan["target"] == "alerting"  # the UI owns the link


def test_only_an_open_item_has_a_remedy(factory):
    with factory() as db:
        plan = pr.preview(
            db, _item(db, state="satisfied"), {"remedy": "enable_firewall"}
        )
    assert plan["unavailable_reason"] == "not_open"


def test_a_server_setting_is_not_a_tenants_to_change(factory):
    with factory() as db, patch.object(pr, "_multitenant", return_value=True):
        plan = pr.preview(
            db, _item(db, managed_by="server"), {"remedy": "shorten_session"}
        )
    assert plan["unavailable_reason"] == "managed_by_server"


def test_a_setting_remedy_previews_and_applies_the_change(factory):
    with factory() as db, patch.object(
        pr.config, "get_jwt_auth_timeout", return_value=6000
    ), patch.object(pr.settings_service, "set_setting", return_value=True) as write:
        item = _item(db, managed_by="server")
        plan = pr.preview(db, item, {"remedy": "shorten_session"})
        assert plan["changes"] == [
            {"setting": "jwt_auth_timeout", "from": 6000, "to": 3600}
        ]
        pr.apply(db, ps.SCOPE, item, {"remedy": "shorten_session"}, Admin())
        write.assert_called_once_with("jwt_auth_timeout", 3600)
        audit = db.query(models.AuditLog).one()
        assert (audit.action_type, audit.entity_type) == ("EXECUTE", "setting")
        assert db.query(models.PostureItemEvent).one().cause == "remediation_requested"


def test_a_setting_already_in_place_is_nothing_to_do(factory):
    with factory() as db, patch.object(
        pr.config, "get_jwt_auth_timeout", return_value=1800
    ):
        plan = pr.preview(db, _item(db), {"remedy": "shorten_session"})
    assert plan["unavailable_reason"] == "nothing_to_do"


def test_a_setting_that_did_not_persist_is_an_error_not_a_success(factory):
    with factory() as db, patch.object(
        pr.config, "get_max_failed_logins", return_value=0
    ), patch.object(pr.settings_service, "set_setting", return_value=False):
        with pytest.raises(RuntimeError):
            pr.apply(db, ps.SCOPE, _item(db), {"remedy": "enforce_lockout"}, Admin())


def test_require_admin_mfa_turns_it_on(factory):
    with factory() as db:
        item = _item(db, managed_by="server")
        pr.apply(db, ps.SCOPE, item, {"remedy": "require_admin_mfa"}, Admin())
        assert db.query(models.MfaSettings).one().admin_required is True


def test_a_fleet_remedy_touches_only_failing_fresh_hosts(factory):
    dispatched = []
    with factory() as db:
        off = _host(db, "off", fw_enabled=False)
        _host(db, "on", fw_enabled=True)
        _host(db, "stale", fw_enabled=False, fw_age=timedelta(days=5))
        _host(db, "silent")
        item = _item(db)
        plan = pr.preview(db, item, {"remedy": "enable_firewall"})
        assert [h["fqdn"] for h in plan["hosts"]] == ["off"]
        fleet = dict(
            pr.FLEET,
            enable_firewall=(
                pr.FLEET["enable_firewall"][0],
                lambda _db, host, _u: dispatched.append(host.fqdn),
                pr.FLEET["enable_firewall"][2],
            ),
        )
        with patch.object(pr, "FLEET", fleet):
            result = pr.apply(
                db, ps.SCOPE, item, {"remedy": "enable_firewall"}, Admin()
            )
    assert dispatched == ["off"] and result["failed"] == [] and off is not None


def test_one_failing_host_does_not_stop_the_rest(factory):
    def dispatch(_db, host, _u):
        if host.fqdn == "a":
            raise ValueError("unsupported OS")

    with factory() as db:
        _host(db, "a", fw_enabled=False)
        _host(db, "b", fw_enabled=False)
        fleet = dict(
            pr.FLEET,
            enable_firewall=(
                pr.FLEET["enable_firewall"][0],
                dispatch,
                pr.FLEET["enable_firewall"][2],
            ),
        )
        with patch.object(pr, "FLEET", fleet):
            result = pr.apply(
                db, ps.SCOPE, _item(db), {"remedy": "enable_firewall"}, Admin()
            )
    assert result["failed"] == [{"fqdn": "a", "reason": "unsupported OS"}]
    assert {h["fqdn"] for h in result["hosts"]} == {"a", "b"}


def test_a_fleet_remedy_needs_the_per_host_role():
    assert pr.required_role({"remedy": "enable_firewall"}).value == "Enable Firewall"
    assert pr.required_role({"remedy": "shorten_session"}) is None


def test_apply_refuses_what_the_preview_refuses(factory):
    with factory() as db:
        with pytest.raises(ValueError, match="not_open"):
            pr.apply(
                db,
                ps.SCOPE,
                _item(db, state="satisfied"),
                {"remedy": "enable_firewall"},
                Admin(),
            )


@pytest.mark.parametrize(
    "dispatch", [pr._dispatch_firewall, pr._dispatch_antivirus]
)  # pylint: disable=protected-access
def test_the_real_dispatchers_queue_a_deployment_plan(factory, dispatch):
    """The fleet remedies reach into the per-host routes' helpers; this proves
    that wiring end to end, down to the outbound queue row."""
    with factory() as db:
        host = models.Host(
            id=uuid.uuid4(),
            fqdn="h",
            active=True,
            approval_status="approved",
            platform="Linux",
            platform_release="Ubuntu 24.04",
        )
        db.add(host)
        db.flush()
        dispatch(db, host, Admin())
        db.flush()
        rows = db.query(models.MessageQueue).filter_by(host_id=str(host.id)).all()
    assert len(rows) == 1 and rows[0].message_type == "command"
