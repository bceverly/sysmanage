# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Golden-host drift over watched FILES -- Phase 21.1 S7.

A file-state row records an OUTCOME, not just a value, and that is what makes
this comparator different from every other category. The cases worth testing
are the ones where a host did NOT measure something: those must never become
drift (a divergence that may not exist) and must never become agreement (two
hosts "matching" because neither could look).
"""

import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence import models
from backend.services import config_mgmt_baseline as baseline
from backend.services import config_mgmt_files as cf


@pytest.fixture
def db():
    # In-memory, never a file: tests/api/conftest.py documents at length how
    # file-backed SQLite made the Windows suite ~40x slower.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        # Without this the connection is reclaimed by the garbage collector
        # instead, which pytest reports as an unraisable ResourceWarning.
        engine.dispose()


REF = uuid.uuid4()
TGT = uuid.uuid4()


def _state(db, host, path, state, sha=None, mode="0644", owner="root", **kw):
    db.add(
        models.HostFileState(
            host_id=host,
            path=path,
            state=state,
            sha256=sha,
            mode=mode,
            owner=owner,
            type=kw.pop("type", "regular"),
            **kw,
        )
    )


class FakeHost:
    """A host whose agent advertises a given fact coverage."""

    def __init__(self, serves_file_state, contract_version=2):
        served = {"users": "native"}
        if serves_file_state:
            served["sysmanage_file_state"] = "native"
        self.agent_capabilities = json.dumps(
            {
                "schema_version": 1,
                "commands": [],
                "facts": {
                    "contract_version": contract_version,
                    "served": served,
                    "unsupported": {},
                    "not_applicable": {},
                },
            }
        )
        self.fqdn = "host.example"


class TestRealDriftIsReported:
    def test_content_change_is_drift(self, db):
        _state(db, REF, "/etc/ssh/sshd_config", "present", "aaa")
        _state(db, TGT, "/etc/ssh/sshd_config", "present", "bbb")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert [d["name"] for d in out["different"]] == ["/etc/ssh/sshd_config"]
        assert out["different"][0]["fields"][0]["field"] == "sha256"

    def test_permission_change_with_identical_content_is_drift(self, db):
        """The case a content-only diff would miss entirely: same bytes, wrong
        mode. chmod 644 on /etc/sudoers is a real finding."""
        _state(db, REF, "/etc/sudoers", "present", "aaa", mode="0440")
        _state(db, TGT, "/etc/sudoers", "present", "aaa", mode="0644")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert [f["field"] for f in out["different"][0]["fields"]] == ["mode"]

    def test_file_deleted_on_target_is_missing(self, db):
        _state(db, REF, "/etc/motd", "present", "aaa")
        _state(db, TGT, "/etc/motd", "absent")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert [d["name"] for d in out["missing"]] == ["/etc/motd"]

    def test_file_appeared_on_target_is_extra(self, db):
        _state(db, REF, "/etc/rogue", "absent")
        _state(db, TGT, "/etc/rogue", "present", "aaa")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert [d["name"] for d in out["extra"]] == ["/etc/rogue"]

    def test_identical_files_are_silent(self, db):
        _state(db, REF, "/etc/hosts", "present", "aaa")
        _state(db, TGT, "/etc/hosts", "present", "aaa")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert out["counts"]["different"] == 0
        assert out["counts"]["blind_spots"] == 0

    def test_absent_on_both_is_agreement_not_a_gap(self, db):
        """Neither host has the file. That is a real, measured answer."""
        _state(db, REF, "/etc/never", "absent")
        _state(db, TGT, "/etc/never", "absent")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert out["counts"]["missing"] == 0
        assert out["counts"]["blind_spots"] == 0


class TestBlindSpotsAreNeitherDriftNorAgreement:
    def test_unreadable_target_is_not_reported_as_a_difference(self, db):
        """THE DEFECT: an unreadable file has a null sha256. Compared against a
        reference with a real hash that looks 'different' -- a divergence
        invented out of a permission error."""
        _state(db, REF, "/etc/shadow", "present", "aaa")
        _state(db, TGT, "/etc/shadow", "unreadable")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert out["counts"]["different"] == 0
        assert out["blind_spots"] == [
            {"name": "/etc/shadow", "side": "target", "reason": "unreadable"}
        ]

    def test_unreadable_on_both_sides_is_not_agreement(self, db):
        """The mirror image, and the worse one: two hosts with null hashes
        'match'. They agree only in having been unable to look."""
        _state(db, REF, "/etc/shadow", "unreadable")
        _state(db, TGT, "/etc/shadow", "unreadable")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert out["counts"]["different"] == 0
        assert out["counts"]["blind_spots"] == 1

    def test_path_watched_on_one_side_only_is_not_a_deletion(self, db):
        """A path the target never watched is not a file the target deleted."""
        _state(db, REF, "/etc/only-ref", "present", "aaa")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert out["missing"] == []
        assert out["blind_spots"][0]["reason"] == "not_watched"

    def test_too_large_is_a_blind_spot_not_a_match(self, db):
        """A file we declined to hash has no measurement to compare."""
        _state(db, REF, "/var/lib/big.img", "too_large")
        _state(db, TGT, "/var/lib/big.img", "too_large")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert out["counts"]["blind_spots"] == 1
        assert out["counts"]["different"] == 0

    def test_blind_spots_do_not_inflate_the_difference_count(self, db):
        _state(db, REF, "/etc/a", "present", "aaa")
        _state(db, TGT, "/etc/a", "unreadable")
        _state(db, REF, "/etc/b", "present", "bbb")
        _state(db, TGT, "/etc/b", "present", "ccc")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert out["counts"]["different"] == 1
        assert out["counts"]["blind_spots"] == 1


class TestEmptyWatchListTrap:
    def test_two_unwatched_hosts_are_not_identical(self, db):
        """Every set-difference over two empty sets is empty, so the category
        would announce that two hosts match having compared nothing at all --
        a fabricated all-clear produced by code working exactly as written."""
        out = cf.compare_files(db, REF, TGT)
        assert out["comparable"] is False
        assert out["not_comparable"]["reason"] == "no_watch_list"

    def test_one_side_watched_still_compares(self, db):
        """Not the same case: there IS something to say, namely that the target
        is not watching what the reference watches."""
        _state(db, REF, "/etc/hosts", "present", "aaa")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        assert out["comparable"] is True
        assert out["counts"]["blind_spots"] == 1


class TestServesGate:
    def test_new_category_requires_a_positive_advertisement(self):
        """An agent too old to know the table exists has no rows. The
        permissive gate would compare zero against zero and call it identical
        -- a clean bill of health from a feature that has never run."""
        blocked = baseline.comparability(FakeHost(True), FakeHost(False), "files")
        assert blocked is not None
        assert blocked["not_comparable"]["reason"] == "unknown"
        assert blocked["not_comparable"]["side"] == "target"

    def test_two_current_agents_compare(self):
        assert baseline.comparability(FakeHost(True), FakeHost(True), "files") is None

    def test_legacy_categories_still_tolerate_an_old_agent(self):
        """The stricter gate must stay scoped to the new category. Applying it
        to the 20.2 categories would switch drift off for an entire estate the
        day this shipped."""
        assert baseline.comparability(FakeHost(True), FakeHost(False), "users") is None

    def test_files_is_a_selectable_category(self):
        assert "files" in baseline.CATEGORIES
        assert baseline.resolve_categories(["files"]) == ["files"]


class TestNoFileContentsAnywhere:
    def test_the_stored_row_has_no_content_column(self):
        """The property that lets an operator watch /etc/shadow at all."""
        columns = set(models.HostFileState.__table__.columns.keys())
        assert not columns & {"content", "contents", "data", "body", "text"}

    def test_a_comparison_result_carries_no_file_bytes(self, db):
        _state(db, REF, "/etc/secret", "present", "aaa")
        _state(db, TGT, "/etc/secret", "present", "bbb")
        db.commit()
        out = cf.compare_files(db, REF, TGT)
        # Only hashes and metadata travel; there is nothing to leak.
        rendered = json.dumps(out, default=str)
        assert "aaa" in rendered and "bbb" in rendered
        for field in out["different"][0]["fields"]:
            assert field["field"] in cf.COMPARED_FIELDS
