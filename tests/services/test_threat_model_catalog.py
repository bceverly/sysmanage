# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The curated threat-model questionnaire: engine -> shared catalog (21.4 S2).

Every VERSION is kept (a saved threat model names the version it answered);
a version the engine itself rejects is never written; the sync never raises.
"""

import copy
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import threat_model_catalog as cat

Q1 = {
    "id": "sysmanage-threat-model",
    "version": 1,
    "contract": 1,
    "attributes": {"a": "x"},
    "questions": [
        {"id": "q", "kind": "one", "options": [{"id": "y", "sets": ["a"]}, {"id": "n"}]}
    ],
}


class Engine:
    def __init__(self, questionnaires, invalid=()):
        self.questionnaires = questionnaires
        self.invalid = set(invalid)

    def curated_questionnaires(self):
        return copy.deepcopy(self.questionnaires)

    def validate_questionnaire(self, q):
        return [{"code": "bad"}] if q["version"] in self.invalid else []


@pytest.fixture
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    @contextmanager
    def _session(_partition):
        session = maker()
        try:
            yield session
        finally:
            session.close()

    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with patch.object(cat, "partition_session", _session):
        yield maker
    engine.dispose()


def _versions(factory):
    with factory() as s:
        return sorted(
            (r.slug, r.version) for r in s.query(models.SharedThreatQuestionnaire)
        )


def test_a_new_version_is_added_and_the_old_one_kept(factory):
    assert cat.sync_questionnaires(Engine([Q1]))["written"] == 1
    q2 = dict(copy.deepcopy(Q1), version=2)
    summary = cat.sync_questionnaires(Engine([Q1, q2]))
    assert summary == {"written": 1, "unchanged": 1, "invalid": 0}
    assert _versions(factory) == [
        ("sysmanage-threat-model", 1),
        ("sysmanage-threat-model", 2),
    ]


def test_resyncing_writes_nothing(factory):
    cat.sync_questionnaires(Engine([Q1]))
    assert cat.sync_questionnaires(Engine([Q1]))["written"] == 0


def test_a_version_the_engine_rejects_is_never_written(factory):
    assert cat.sync_questionnaires(Engine([Q1], invalid={1}))["invalid"] == 1
    assert _versions(factory) == []


def test_load_returns_the_newest_or_the_named_version(factory):
    cat.sync_questionnaires(Engine([Q1, dict(copy.deepcopy(Q1), version=2)]))
    assert cat.load_questionnaire("sysmanage-threat-model")["version"] == 2
    assert cat.load_questionnaire("sysmanage-threat-model", 1)["version"] == 1
    assert cat.load_questionnaire("nope") is None


def test_no_engine_or_a_failing_catalog_never_raises(factory):
    assert cat.sync_questionnaires(None)["written"] == 0
    with patch.object(cat, "partition_session", side_effect=RuntimeError("db down")):
        assert cat.sync_questionnaires(Engine([Q1]))["written"] == 0
