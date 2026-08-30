# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Golden-host baseline diff (Phase 20.2, S5).

The comparison is deliberately BOUNDED to inventory the agent already reports,
so these tests use the real models against a real SQLite session rather than
mocks: the thing most likely to break is a column rename or an identity that
does not actually exist, and a mock cannot catch either.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.services import config_mgmt_baseline as baseline

_NOW = datetime.now(timezone.utc).replace(tzinfo=None)

REF = uuid.uuid4()
TGT = uuid.uuid4()


@pytest.fixture(name="session")
def _session():
    """A real session with just the tables this differ touches."""
    engine = create_engine("sqlite://")
    tables = [models.Host.__table__] + [
        model.__table__ for model, _ident, _cmp in baseline._CATEGORIES.values()
    ]
    models.Host.metadata.create_all(engine, tables=tables)
    made = sessionmaker(bind=engine)()
    made.add(models.Host(id=REF, fqdn="golden.invalid", active=True))
    made.add(models.Host(id=TGT, fqdn="target.invalid", active=True))
    made.commit()
    try:
        yield made
    finally:
        # The suite treats warnings as errors; an undisposed in-memory engine
        # surfaces later as an unraisable ResourceWarning in an unrelated test.
        made.close()
        engine.dispose()


def _pkg(host_id, name, version="1.0"):
    # package_manager is NOT NULL in the real table; the point of testing
    # against the real models is that constraints like this apply.
    return models.SoftwarePackage(
        host_id=host_id,
        package_name=name,
        package_version=version,
        package_manager="apt",
        created_at=_NOW,
        updated_at=_NOW,
    )


class TestCategoryDefinitions:
    def test_every_category_names_a_real_column(self):
        # The whole differ rests on these column names existing. A rename
        # elsewhere would otherwise surface as an empty comparison -- i.e. two
        # hosts reported identical because nothing could be read.
        for name, (model, identity, compared) in baseline._CATEGORIES.items():
            cols = {c.name for c in model.__table__.columns}
            assert identity in cols, f"{name}: identity {identity!r} missing"
            assert "host_id" in cols, f"{name}: not a per-host table"
            for field in compared:
                assert field in cols, f"{name}: compared field {field!r} missing"

    def test_the_public_category_list_matches_the_table(self):
        assert set(baseline.CATEGORIES) == set(baseline._CATEGORIES)


class TestComparison:
    def test_identical_hosts_report_no_differences(self, session):
        for host in (REF, TGT):
            session.add(_pkg(host, "bash", "5.2"))
        session.commit()
        out = baseline.compare_hosts(session, REF, TGT, categories=["packages"])
        assert out["identical"] is True
        assert out["total_differences"] == 0

    def test_a_package_only_on_the_reference_is_missing(self, session):
        session.add(_pkg(REF, "nginx"))
        session.commit()
        cat = baseline.compare_hosts(session, REF, TGT, ["packages"])["categories"]
        assert [i["name"] for i in cat["packages"]["missing"]] == ["nginx"]
        assert cat["packages"]["extra"] == []

    def test_a_package_only_on_the_target_is_extra(self, session):
        session.add(_pkg(TGT, "telnet"))
        session.commit()
        cat = baseline.compare_hosts(session, REF, TGT, ["packages"])["categories"]
        assert [i["name"] for i in cat["packages"]["extra"]] == ["telnet"]
        assert cat["packages"]["missing"] == []

    def test_a_version_mismatch_is_a_difference_not_a_missing(self, session):
        # The distinction an operator acts on: "you don't have it" and "you have
        # the wrong one" are different fixes.
        session.add(_pkg(REF, "openssl", "3.0.2"))
        session.add(_pkg(TGT, "openssl", "1.1.1"))
        session.commit()
        pkgs = baseline.compare_hosts(session, REF, TGT, ["packages"])["categories"][
            "packages"
        ]
        assert pkgs["missing"] == [] and pkgs["extra"] == []
        assert pkgs["different"][0]["name"] == "openssl"
        assert pkgs["different"][0]["fields"]["package_version"] == {
            "reference": "3.0.2",
            "target": "1.1.1",
        }

    def test_naming_is_from_the_targets_point_of_view(self, session):
        # "missing" must mean the TARGET lacks it -- the target is the host
        # being fixed. Getting this backwards would send the operator to undo
        # the reference host instead.
        session.add(_pkg(REF, "only-on-golden"))
        session.add(_pkg(TGT, "only-on-target"))
        session.commit()
        pkgs = baseline.compare_hosts(session, REF, TGT, ["packages"])["categories"][
            "packages"
        ]
        assert [i["name"] for i in pkgs["missing"]] == ["only-on-golden"]
        assert [i["name"] for i in pkgs["extra"]] == ["only-on-target"]

    def test_counts_stay_exact_when_the_lists_are_capped(self, session):
        for i in range(baseline.MAX_ITEMS_PER_BUCKET + 25):
            session.add(_pkg(REF, f"pkg-{i:04d}"))
        session.commit()
        pkgs = baseline.compare_hosts(session, REF, TGT, ["packages"])["categories"][
            "packages"
        ]
        assert len(pkgs["missing"]) == baseline.MAX_ITEMS_PER_BUCKET
        assert pkgs["counts"]["missing"] == baseline.MAX_ITEMS_PER_BUCKET + 25
        assert pkgs["truncated"] is True

    def test_results_are_sorted_so_two_runs_read_the_same(self, session):
        for name in ("zsh", "apache", "mysql"):
            session.add(_pkg(REF, name))
        session.commit()
        pkgs = baseline.compare_hosts(session, REF, TGT, ["packages"])["categories"][
            "packages"
        ]
        assert [i["name"] for i in pkgs["missing"]] == ["apache", "mysql", "zsh"]

    def test_rows_with_no_identity_are_skipped(self, session):
        # An UNMOUNTED disk has no mount_point, and mount_point is this
        # category's identity -- a real, common state, not a synthetic one.
        # There is nothing to match on across hosts, so counting it would
        # report a difference the operator cannot act on.
        session.add(
            models.StorageDevice(
                host_id=REF, device_name="/dev/sdb", mount_point=None, last_updated=_NOW
            )
        )
        session.add(
            models.StorageDevice(
                host_id=REF, device_name="/dev/sda1", mount_point="/", last_updated=_NOW
            )
        )
        session.commit()
        storage = baseline.compare_hosts(session, REF, TGT, ["storage"])["categories"][
            "storage"
        ]
        assert [i["name"] for i in storage["missing"]] == ["/"]
        assert storage["counts"]["reference_total"] == 1

    def test_the_totals_span_every_requested_category(self, session):
        session.add(_pkg(REF, "nginx"))
        session.add(
            models.UserGroup(
                host_id=REF,
                group_name="docker",
                is_system_group=False,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        session.commit()
        out = baseline.compare_hosts(session, REF, TGT, ["packages", "groups"])
        assert out["total_differences"] == 2
        assert out["identical"] is False

    def test_both_hostnames_are_reported(self, session):
        out = baseline.compare_hosts(session, REF, TGT, ["packages"])
        assert out["reference_fqdn"] == "golden.invalid"
        assert out["host_fqdn"] == "target.invalid"


class TestRefusals:
    def test_comparing_a_host_with_itself_is_refused(self, session):
        # Returning an empty result would look like a clean comparison rather
        # than a mistake.
        with pytest.raises(baseline.BaselineError) as exc:
            baseline.compare_hosts(session, REF, REF)
        assert exc.value.status == 400

    def test_an_unknown_reference_host_is_a_404(self, session):
        with pytest.raises(baseline.BaselineError) as exc:
            baseline.compare_hosts(session, uuid.uuid4(), TGT, ["packages"])
        assert exc.value.status == 404
        assert "Reference" in exc.value.message

    def test_an_unknown_target_host_is_a_404(self, session):
        with pytest.raises(baseline.BaselineError) as exc:
            baseline.compare_hosts(session, REF, uuid.uuid4(), ["packages"])
        assert exc.value.status == 404
        assert "Target" in exc.value.message

    def test_an_unknown_category_is_refused_not_ignored(self, session):
        # Silently dropping it returns a clean-looking result for a comparison
        # the caller believes they asked for.
        with pytest.raises(baseline.BaselineError) as exc:
            baseline.compare_hosts(session, REF, TGT, ["packages", "kernel_params"])
        assert exc.value.status == 400
        assert "kernel_params" in exc.value.message


class TestCategorySelection:
    def test_no_selection_means_every_category(self):
        assert baseline.resolve_categories(None) == list(baseline.CATEGORIES)

    def test_an_empty_selection_means_every_category(self):
        assert baseline.resolve_categories([]) == list(baseline.CATEGORIES)

    def test_selection_is_case_and_space_tolerant(self):
        assert baseline.resolve_categories([" Packages ", "USERS"]) == [
            "packages",
            "users",
        ]

    def test_only_the_requested_categories_are_compared(self, session):
        session.add(_pkg(REF, "nginx"))
        session.commit()
        out = baseline.compare_hosts(session, REF, TGT, ["groups"])
        assert set(out["categories"]) == {"groups"}
        assert out["total_differences"] == 0
