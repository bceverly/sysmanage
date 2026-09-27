# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The punch list over time (21.4 S6).

The property that matters: a satisfied -> open change is a REGRESSION only
when the fleet caused it. The same transition after the wizard was re-run is
a model change -- reporting it as a regression would blame the fleet for a
decision the operator just made.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import posture_history as ph
from backend.services import posture_service as ps
from tests.services.test_posture_service import Engine, _entry

T0 = datetime(2026, 9, 27, 12, 0, 0)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _event(db, key, before, after, cause, minutes=0, version=1):
    db.add(
        models.PostureItemEvent(
            **ps.SCOPE,
            rule_key=key,
            from_state=before,
            to_state=after,
            cause=cause,
            threat_model_version=version,
            at=T0 + timedelta(minutes=minutes)
        )
    )
    db.flush()


@pytest.mark.parametrize(
    "before,after,cause,kind",
    [
        ("satisfied", "open", "evaluation", "regression"),
        ("satisfied", "open", "threat_model", "changed_by_model"),  # never a regression
        ("open", "satisfied", "evaluation", "resolved"),
        ("open", "not_assessable", "evaluation", "blind_spot"),
        ("not_assessable", "open", "evaluation", "measured_again"),
        (None, "open", "threat_model", "added_by_model"),
        (None, "open", "evaluation", "added"),
        ("open", None, "threat_model", "removed_by_model"),
        ("open", None, "rule_withdrawn", "withdrawn"),
        ("open", "open", "remediation_requested", "remediation_requested"),
    ],
)
def test_every_change_is_classified(db, before, after, cause, kind):
    _event(db, "PM-A", before, after, cause)
    assert ph.history(db)[0]["kind"] == kind


def test_the_latest_change_decides_whether_an_item_regressed(db):
    _event(db, "PM-A", None, "satisfied", "threat_model", 0)
    _event(db, "PM-A", "satisfied", "open", "evaluation", 1)
    _event(db, "PM-A", "open", "open", "remediation_requested", 2)  # does not hide it
    _event(db, "PM-B", "satisfied", "open", "evaluation", 1)
    _event(db, "PM-B", "open", "satisfied", "evaluation", 2)  # fixed since
    _event(db, "PM-C", "satisfied", "open", "threat_model", 1)  # the wizard did it
    assert ph.regressed_keys(db) == {"PM-A"}


def test_history_is_newest_first_and_can_follow_one_item(db):
    _event(db, "PM-A", None, "open", "threat_model", 0)
    _event(db, "PM-B", None, "open", "threat_model", 1)
    _event(db, "PM-A", "open", "satisfied", "evaluation", 2)
    assert [e["rule_key"] for e in ph.history(db)] == ["PM-A", "PM-B", "PM-A"]
    assert [e["kind"] for e in ph.history(db, rule_key="PM-A")] == [
        "resolved",
        "added_by_model",
    ]
    assert len(ph.history(db, limit=1)) == 1


def test_a_model_diff_says_what_changed_and_what_it_did_to_the_list(db):
    engine = Engine()
    from unittest.mock import patch  # noqa: PLC0415

    with patch.object(
        ps.threat_model_catalog,
        "load_questionnaire",
        return_value={"id": "sysmanage-threat-model", "version": 1},
    ), patch.object(ps.posture_evidence, "gather", return_value={}):
        ps.save_threat_model(engine, db, {"q": "no"}, "a@b")
        ps.evaluate(engine, db, None, [_entry("PM-A")])
        ps.save_threat_model(engine, db, {"q": "yes"}, "a@b")
        engine.states = {"PM-A": "fires"}
        ps.evaluate(engine, db, None, [_entry("PM-A")])
    diff = ph.model_diff(engine, db, 1, 2)
    assert diff["model"] == {"attributes_on": ["x"]}
    assert [(e["rule_key"], e["kind"]) for e in diff["punch_list"]] == [
        ("PM-A", "changed_by_model")
    ]
    assert ph.model_diff(engine, db, 1, 9) is None
