# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Waivers as audit artifacts (21.4 S4).

A waiver is neutral, never green: it overlays an OPEN item, which keeps
evaluating as open underneath. It is scoped to its basis (decided
2026-09-26): stale when the risk RISES, the rule version changes, or the
attributes the rule reads change -- and once stale it stays stale until an
administrator re-affirms. Every grant, revoke and re-affirmation is audited.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import posture_service as ps
from backend.services import posture_waivers as pw

SCOPE = ps.SCOPE
RULE = {
    "id": "PM-MFA",
    "scope": "installation",
    "applies_when": {"any": ["regulated", "targeted"]},
}


class Admin:
    id = None
    userid = "admin@sysmanage.org"


class Model:
    model_version = 1
    attributes = {"regulated": True, "targeted": False, "phi": True}


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _item(db, state="open", risk=20, version=1):
    item = models.PostureItem(
        **SCOPE,
        rule_source="shared",
        rule_key="PM-MFA",
        rule_version=version,
        state=state,
        outcome="fires",
        managed_by="server",
        risk=risk
    )
    db.add(item)
    db.flush()
    return item


def _audits(db):
    return [
        (a.action_type, a.entity_type, a.entity_name) for a in db.query(models.AuditLog)
    ]


def test_granting_records_the_basis_and_is_audited(db):
    item = _item(db)
    waiver = pw.grant(
        db, SCOPE, item, RULE, Model(), Admin(), "  compensating control: VPN only  "
    )
    assert waiver.reason == "compensating control: VPN only"
    assert waiver.basis_attributes == {
        "regulated": True,
        "targeted": False,
    }  # only what the rule reads
    assert (waiver.risk, waiver.rule_version, waiver.threat_model_version) == (20, 1, 1)
    assert _audits(db) == [("CREATE", "posture_waiver", "PM-MFA")]


@pytest.mark.parametrize(
    "state,reason,code",
    [
        ("open", "   ", "reason_required"),
        ("satisfied", "fine", "not_open"),
        ("not_assessable", "fine", "not_open"),  # waiving a blind spot would hide it
    ],
)
def test_only_an_open_item_with_a_reason_can_be_waived(db, state, reason, code):
    with pytest.raises(pw.WaiverError) as err:
        pw.grant(db, SCOPE, _item(db, state=state), RULE, Model(), Admin(), reason)
    assert err.value.code == code


def test_a_second_waiver_is_refused(db):
    item = _item(db)
    pw.grant(db, SCOPE, item, RULE, Model(), Admin(), "accepted")
    with pytest.raises(pw.WaiverError) as err:
        pw.grant(db, SCOPE, item, RULE, Model(), Admin(), "again")
    assert err.value.code == "already_waived"


def test_waived_is_an_overlay_on_open_only(db):
    item = _item(db)
    waiver = pw.grant(db, SCOPE, item, RULE, Model(), Admin(), "accepted")
    assert pw.display_state(item, waiver) == "waived"
    assert item.state == "open"  # the evaluation still says open underneath
    item.state = "satisfied"
    assert pw.display_state(item, waiver) == "satisfied"


@pytest.mark.parametrize(
    "change,reason",
    [
        (lambda item, attrs: setattr(item, "risk", 25), "risk_rose"),
        (lambda item, attrs: setattr(item, "rule_version", 2), "rule_version_changed"),
        (lambda item, attrs: attrs.update(targeted=True), "threat_model_changed"),
    ],
)
def test_the_waiver_goes_stale_when_its_basis_changes(db, change, reason):
    item = _item(db)
    waiver = pw.grant(db, SCOPE, item, RULE, Model(), Admin(), "accepted")
    attrs = dict(Model.attributes)
    change(item, attrs)
    assert pw.refresh_staleness(db, SCOPE, item, RULE, attrs) == reason
    assert waiver.stale_since is not None
    assert pw.display_state(item, waiver) == "open"  # counts as open again


def test_a_lower_risk_or_an_unread_attribute_keeps_the_waiver(db):
    item = _item(db)
    pw.grant(db, SCOPE, item, RULE, Model(), Admin(), "accepted")
    item.risk = 12
    attrs = dict(Model.attributes, phi=False)  # PM-MFA does not read phi
    assert pw.refresh_staleness(db, SCOPE, item, RULE, attrs) is None


def test_stale_stays_stale_until_reaffirmed(db):
    item = _item(db)
    waiver = pw.grant(db, SCOPE, item, RULE, Model(), Admin(), "accepted")
    item.risk = 25
    pw.refresh_staleness(db, SCOPE, item, RULE, Model.attributes)
    item.risk = 20  # the risk falls back -- the acceptance was about another situation
    assert pw.refresh_staleness(db, SCOPE, item, RULE, Model.attributes) == "risk_rose"
    item.risk = 25
    pw.reaffirm(db, SCOPE, item, RULE, Model(), Admin(), "still accepted at 25")
    assert (waiver.stale_reason, waiver.risk, waiver.reason) == (
        None,
        25,
        "still accepted at 25",
    )
    assert pw.display_state(item, waiver) == "waived"
    assert _audits(db)[-1] == ("UPDATE", "posture_waiver", "PM-MFA")


def test_reaffirming_a_fresh_waiver_is_refused(db):
    item = _item(db)
    pw.grant(db, SCOPE, item, RULE, Model(), Admin(), "accepted")
    with pytest.raises(pw.WaiverError) as err:
        pw.reaffirm(db, SCOPE, item, RULE, Model(), Admin())
    assert err.value.code == "not_stale"


def test_revoking_reopens_and_keeps_the_history(db):
    item = _item(db)
    pw.grant(db, SCOPE, item, RULE, Model(), Admin(), "accepted")
    pw.revoke(db, SCOPE, item, Admin())
    assert pw.active_waiver(db, SCOPE, "PM-MFA") is None
    assert db.query(models.PostureWaiver).count() == 1  # revoked rows are audit history
    assert _audits(db)[-1] == ("DELETE", "posture_waiver", "PM-MFA")
    with pytest.raises(pw.WaiverError):
        pw.revoke(db, SCOPE, item, Admin())


def test_an_always_rule_has_an_empty_basis():
    assert pw.basis_attributes({"applies_when": {"always": True}}, {"x": True}) == {}
