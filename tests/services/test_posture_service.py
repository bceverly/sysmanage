# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The threat model and the punch list, per tenant (21.4 S3).

The properties: saving ADDS a version (the previous stays, not current); no
model means no list; every state change is an event with its cause -- the
first pass under a new model is the model's doing, later ones the fleet's; a
check the model stops applying, or a withdrawn check, leaves with an event.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import posture_service as ps


class Engine:
    """A stand-in: attribute 'x' from answers; each rule's state is scripted."""

    def __init__(self):
        self.states = {}

    def derive_threat_model(self, questionnaire, answers):
        attrs = {"x": answers.get("q") == "yes"}
        return {
            "questionnaire": questionnaire["id"],
            "questionnaire_version": 1,
            "attributes": attrs,
            "answers": dict(answers),
            "digest": str(attrs),
            "complete": True,
            "missing": [],
            "ignored": [],
        }

    def diff_threat_models(self, old, new):
        before = (old or {}).get("attributes") or {}
        return {
            "attributes_on": [
                k for k, v in new["attributes"].items() if v and not before.get(k)
            ]
        }

    def evaluate_installation(self, rules, model, evidence):
        out = []
        for rule in rules:
            outcome = self.states.get(rule["id"], "does_not_fire")
            out.append(
                {
                    "rule_id": rule["id"],
                    "rule_version": 1,
                    "outcome": outcome,
                    "managed_by": "server" if rule["id"] == "PM-S" else "tenant",
                    "gaps": [],
                    "coverage": None,
                    "matches": [],
                }
            )
        return out

    def posture_state(self, result):
        return {
            "fires": "open",
            "does_not_fire": "satisfied",
            "not_assessable": "not_assessable",
        }.get(result["outcome"])


def _entry(key):
    return {
        "source": "shared",
        "key": key,
        "rule": {"id": key, "scope": "installation"},
    }


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    with patch.object(
        ps.threat_model_catalog,
        "load_questionnaire",
        return_value={"id": "sysmanage-threat-model", "version": 1},
    ), patch.object(ps.posture_evidence, "gather", return_value={}):
        yield session
    session.close()
    engine.dispose()


def _items(db):
    return {i.rule_key: i.state for i in db.query(models.PostureItem)}


def _events(db):
    return [
        (e.rule_key, e.from_state, e.to_state, e.cause)
        for e in db.query(models.PostureItemEvent).order_by(models.PostureItemEvent.at)
    ]


def test_saving_adds_a_version_and_says_what_changed(db):
    engine = Engine()
    one, _ = ps.save_threat_model(engine, db, {"q": "no"}, "a@b")
    two, diff = ps.save_threat_model(engine, db, {"q": "yes"}, "a@b")
    db.commit()
    assert (one.model_version, two.model_version) == (1, 2)
    assert ps.current_threat_model(db).id == two.id
    assert db.query(models.ThreatModel).count() == 2
    assert diff == {"attributes_on": ["x"]}


def test_without_a_model_there_is_no_punch_list(db):
    summary = ps.evaluate(Engine(), db, None, [_entry("PM-A")])
    assert summary["posture_items"] == 0 and _items(db) == {}


def test_state_changes_are_events_with_their_cause(db):
    engine = Engine()
    ps.save_threat_model(engine, db, {"q": "yes"}, "a@b")
    engine.states = {"PM-A": "fires"}
    ps.evaluate(engine, db, None, [_entry("PM-A"), _entry("PM-S")])
    db.commit()
    assert _items(db) == {"PM-A": "open", "PM-S": "satisfied"}
    assert {e[3] for e in _events(db)} == {"threat_model"}  # first pass under the model
    assert (
        db.query(models.PostureItem).filter_by(rule_key="PM-S").one().managed_by
        == "server"
    )

    engine.states = {"PM-A": "does_not_fire"}  # the fleet was fixed
    ps.evaluate(engine, db, None, [_entry("PM-A"), _entry("PM-S")])
    db.commit()
    assert _items(db)["PM-A"] == "satisfied"
    assert _events(db)[-1] == ("PM-A", "open", "satisfied", "evaluation")


def test_an_unchanged_item_writes_no_event(db):
    engine = Engine()
    ps.save_threat_model(engine, db, {"q": "yes"}, "a@b")
    ps.evaluate(engine, db, None, [_entry("PM-A")])
    before = len(_events(db))
    ps.evaluate(engine, db, None, [_entry("PM-A")])
    assert len(_events(db)) == before


def test_a_check_the_model_stops_applying_leaves_with_an_event(db):
    engine = Engine()
    ps.save_threat_model(engine, db, {"q": "yes"}, "a@b")
    ps.evaluate(engine, db, None, [_entry("PM-A")])
    engine.states = {"PM-A": "not_applicable"}
    ps.evaluate(engine, db, None, [_entry("PM-A")])
    assert _items(db) == {}
    assert _events(db)[-1][1:3] == ("satisfied", None)


def test_a_withdrawn_check_leaves_with_an_event(db):
    engine = Engine()
    ps.save_threat_model(engine, db, {"q": "yes"}, "a@b")
    ps.evaluate(engine, db, None, [_entry("PM-A"), _entry("PM-B")])
    ps.evaluate(engine, db, None, [_entry("PM-A")])  # PM-B's pack switched off
    assert set(_items(db)) == {"PM-A"}
    assert _events(db)[-1] == ("PM-B", "satisfied", None, "rule_withdrawn")


def test_a_rederived_model_is_the_cause_of_the_next_changes(db):
    engine = Engine()
    ps.save_threat_model(engine, db, {"q": "yes"}, "a@b")
    ps.evaluate(engine, db, None, [_entry("PM-A")])
    ps.save_threat_model(engine, db, {"q": "no"}, "a@b")
    engine.states = {"PM-A": "fires"}
    ps.evaluate(engine, db, None, [_entry("PM-A")])
    assert _events(db)[-1] == ("PM-A", "satisfied", "open", "threat_model")
