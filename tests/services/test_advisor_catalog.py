# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Curated advisor packs: engine -> shared catalog, and per-tenant choice (S6).

The properties: a pack is written only when the engine's version is NEWER (an
older engine never rolls content back); a pack the engine stops shipping is
deprecated, not deleted; and a tenant's choice switches rules off without
copying the pack -- clearing what it switched off at once.
"""

import copy
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import advisor_catalog as cat

NOW = datetime.now(timezone.utc).replace(tzinfo=None)

PACK = {
    "slug": "sysmanage-baseline",
    "name": "Baseline",
    "description": "d",
    "version": 1,
    "default_enabled": True,
    "rules": [
        {"id": "SM-A", "version": 1, "contract": 1, "title": "A", "lens": "security"},
        {"id": "SM-B", "version": 1, "contract": 1, "title": "B", "lens": "stability"},
    ],
}


class Engine:
    def __init__(self, packs):
        self.packs = packs

    def curated_packs(self):
        return copy.deepcopy(self.packs)


@pytest.fixture
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def shared(factory):
    @contextmanager
    def _session(_partition):
        session = factory()
        try:
            yield session
        finally:
            session.close()

    with patch.object(cat, "partition_session", _session):
        yield factory


def _packs(factory):
    with factory() as s:
        return {p.slug: p for p in s.query(models.SharedAdvisorRulePack).all()}


def _rules(factory):
    with factory() as s:
        return sorted(r.rule_key for r in s.query(models.SharedAdvisorRule).all())


class TestSync:
    def test_a_new_pack_is_written_with_its_rules(self, shared):
        assert cat.sync_shared_catalog(Engine([PACK]))["written"] == 1
        pack = _packs(shared)["sysmanage-baseline"]
        assert pack.default_enabled and pack.source == cat.ENGINE_SOURCE
        assert _rules(shared) == ["SM-A", "SM-B"]

    def test_the_same_version_is_not_rewritten(self, shared):
        cat.sync_shared_catalog(Engine([PACK]))
        assert cat.sync_shared_catalog(Engine([PACK]))["unchanged"] == 1

    def test_a_newer_version_replaces_the_rules(self, shared):
        cat.sync_shared_catalog(Engine([PACK]))
        v2 = dict(PACK, version=2, rules=PACK["rules"][:1])
        assert cat.sync_shared_catalog(Engine([v2]))["written"] == 1
        assert _rules(shared) == ["SM-A"]

    def test_an_older_engine_never_rolls_content_back(self, shared):
        """Two servers sharing a catalog mid-upgrade: the old one must not win."""
        cat.sync_shared_catalog(
            Engine([dict(PACK, version=3, rules=PACK["rules"][:1])])
        )
        summary = cat.sync_shared_catalog(Engine([PACK]))
        assert summary["skipped_older"] == 1 and _rules(shared) == ["SM-A"]

    def test_a_pack_no_longer_shipped_is_deprecated_not_deleted(self, shared):
        cat.sync_shared_catalog(Engine([PACK]))
        assert cat.sync_shared_catalog(Engine([]))["deprecated"] == 1
        assert _packs(shared)["sysmanage-baseline"].deprecated
        assert _rules(shared) == ["SM-A", "SM-B"]

    def test_a_reshipped_pack_comes_back(self, shared):
        cat.sync_shared_catalog(Engine([PACK]))
        cat.sync_shared_catalog(Engine([]))
        cat.sync_shared_catalog(Engine([PACK]))
        assert not _packs(shared)["sysmanage-baseline"].deprecated

    def test_packs_not_from_the_engine_are_left_alone(self, shared):
        with shared() as s:
            s.add(
                models.SharedAdvisorRulePack(
                    id=uuid.uuid4(),
                    slug="hand-made",
                    name="x",
                    version=1,
                    source="import",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            s.commit()
        cat.sync_shared_catalog(Engine([PACK]))
        assert not _packs(shared)["hand-made"].deprecated

    def test_no_engine_or_a_broken_one_changes_nothing(self, shared):
        assert cat.sync_shared_catalog(None)["written"] == 0

        class Broken:
            def curated_packs(self):
                raise RuntimeError("boom")

        assert cat.sync_shared_catalog(Broken())["written"] == 0


class TestChoice:
    class Setting:  # pylint: disable=too-few-public-methods
        def __init__(self, enabled=None, disabled_rules=None):
            self.enabled, self.disabled_rules = enabled, disabled_rules

    def test_no_choice_follows_the_default(self):
        assert cat.rule_enabled(None, True, "SM-A")
        assert not cat.rule_enabled(None, False, "SM-A")
        assert cat.rule_enabled(self.Setting(enabled=None), True, "SM-A")

    def test_an_explicit_choice_wins(self):
        assert not cat.rule_enabled(self.Setting(enabled=False), True, "SM-A")
        assert cat.rule_enabled(self.Setting(enabled=True), False, "SM-A")

    def test_a_rule_can_be_opted_out_alone(self):
        setting = self.Setting(disabled_rules=["SM-B"])
        assert cat.rule_enabled(setting, True, "SM-A")
        assert not cat.rule_enabled(setting, True, "SM-B")

    def test_switching_off_clears_results_and_proposals_now(self, shared):
        with shared() as db:
            host = models.Host(
                id=uuid.uuid4(), fqdn="h", active=True, approval_status="approved"
            )
            db.add(host)
            db.flush()
            for key in ("SM-A", "SM-B"):
                db.add(
                    models.AdvisorResult(
                        host_id=host.id,
                        rule_source="shared",
                        rule_key=key,
                        outcome="fires",
                        evaluated_at=NOW,
                    )
                )
            db.add(
                models.AdvisorProposal(
                    id=uuid.uuid4(),
                    host_id=host.id,
                    rule_source="shared",
                    rule_key="SM-B",
                    kind="generate",
                    fingerprint="f",
                    status="proposed",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            db.commit()
            pack = {"keys": ["SM-A", "SM-B"], "default_enabled": True}
            cat.set_choice(
                db, "sysmanage-baseline", {"disabled_rules": ["SM-B"]}, "op", pack
            )
            db.commit()
            keys = [r.rule_key for r in db.query(models.AdvisorResult).all()]
            proposal = db.query(models.AdvisorProposal).one()
        assert keys == ["SM-A"]
        assert proposal.status == "withdrawn"

    def test_list_packs_reports_the_tenants_effective_state(self, shared):
        cat.sync_shared_catalog(Engine([PACK]))
        with shared() as db:
            cat.set_choice(
                db,
                "sysmanage-baseline",
                {"disabled_rules": ["SM-B"]},
                "op",
                {"keys": ["SM-A", "SM-B"], "default_enabled": True},
            )
            db.commit()
            (pack,) = cat.list_packs(db)
        assert pack["enabled"] and pack["choice"] is None
        assert {r["key"]: r["enabled"] for r in pack["rules"]} == {
            "SM-A": True,
            "SM-B": False,
        }
