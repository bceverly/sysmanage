# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Repository-mirroring API: default-mirror assignment.

``_default_mirror_plan_for`` is what actually repoints a fleet's package
manager at a LAN mirror.  A wrong builder there rewrites sources.list on
every matching host at once, and the only symptom is that hosts start
failing to fetch packages -- so the per-platform routing and the
mirror-value-beats-catalog-default precedence are asserted directly rather
than inferred from an end-to-end plan.

Shared fakes live in ``tests/mirroring_fakes.py``.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import repository_mirroring as api
from backend.api.repository_mirroring_schemas import MirrorSettingsRequest
from backend.persistence import models
from tests.mirroring_fakes import (
    API,
    MIRROR_UUID,
    _engine,
    _FakeSession,
    _known_version,
    _licensed,
    _mirror,
)

# ---------------------------------------------------------------------------
# Default-mirror assignment
# ---------------------------------------------------------------------------


class TestHostsMatchingVersion:
    def _host(self, release="noble", version=""):
        return SimpleNamespace(platform_release=release, platform_version=version)

    def test_matching_hosts_are_returned_case_insensitively(self):
        hosts = [self._host("NOBLE"), self._host("bookworm")]
        db = _FakeSession(Host=hosts)
        out = api._hosts_matching_version(db, _known_version())
        assert out == [hosts[0]]

    def test_the_version_field_is_searched_too(self):
        hosts = [self._host(release="", version="24.04")]
        assert api._hosts_matching_version(_FakeSession(Host=hosts), _known_version())

    def test_an_uncompilable_catalog_regex_matches_nothing(self):
        # Better than raising: a single malformed catalog row would otherwise
        # 500 the whole assignments page.
        db = _FakeSession(Host=[self._host()])
        assert api._hosts_matching_version(db, _known_version(match_regex="[")) == []

    def test_the_search_text_is_length_capped(self):
        # ReDoS defense-in-depth against an admin-curated but untrusted regex.
        host = self._host(release="x" * 5000, version="noble")
        db = _FakeSession(Host=[host])
        assert api._hosts_matching_version(db, _known_version()) == []

    def test_hosts_with_no_platform_strings_do_not_crash(self):
        db = _FakeSession(Host=[self._host(release=None, version=None)])
        assert api._hosts_matching_version(db, _known_version()) == []


class TestLegacyFieldMatch:
    @pytest.mark.parametrize(
        "platform,field,default_field",
        [
            ("apt", "suite", "default_suite"),
            ("dnf", "repoid", "default_repoid"),
            ("zypper", "repo_alias", "default_repo_alias"),
            ("pkg", "release", "default_release"),
        ],
    )
    def test_each_package_manager_compares_its_own_column(
        self, platform, field, default_field
    ):
        mirror = _mirror(**{field: "match-me"})
        kv = _known_version(platform=platform, **{default_field: "match-me"})
        assert api._legacy_field_match(mirror, kv) is True

    def test_a_mismatch_is_false(self):
        assert (
            api._legacy_field_match(
                _mirror(suite="noble"), _known_version(default_suite="jammy")
            )
            is False
        )

    def test_two_empty_values_do_not_count_as_a_match(self):
        # Without the truthiness guard, every mirror with a NULL suite would
        # match every catalog row with a NULL default -- a silent mass match.
        assert (
            api._legacy_field_match(
                _mirror(suite=None), _known_version(default_suite=None)
            )
            is False
        )

    def test_an_unknown_platform_is_false(self):
        assert (
            api._legacy_field_match(_mirror(), _known_version(platform="apk")) is False
        )


class TestEligibleMirrorsForVersion:
    def test_a_foreign_key_match_is_eligible(self):
        kv = _known_version()
        db = _FakeSession(MirrorRepository=[_mirror(known_version_id=kv.id)])
        assert api._eligible_mirrors_for_version(db, kv) == [
            {"id": str(MIRROR_UUID), "name": "ubuntu-noble"}
        ]

    def test_a_legacy_free_text_match_is_eligible(self):
        kv = _known_version()
        db = _FakeSession(MirrorRepository=[_mirror(suite="noble")])
        assert len(api._eligible_mirrors_for_version(db, kv)) == 1

    def test_a_mirror_matching_neither_is_excluded(self):
        kv = _known_version()
        db = _FakeSession(MirrorRepository=[_mirror(suite="jammy")])
        assert api._eligible_mirrors_for_version(db, kv) == []


class TestAssignmentRow:
    def test_an_assigned_row_reports_its_mirror_and_timestamp(self):
        cur = SimpleNamespace(
            id=uuid.uuid4(),
            mirror_id=MIRROR_UUID,
            updated_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00"),
        )
        out = api._assignment_row(_known_version(), cur, [])
        assert out["current_mirror_id"] == str(MIRROR_UUID)
        assert out["updated_at"] == "2026-01-01T00:00:00"

    def test_an_unassigned_tuple_reports_nulls_rather_than_omitting_the_row(self):
        # The UI renders one row per catalog tuple; dropping the unassigned
        # ones would hide exactly the tuples an operator needs to assign.
        out = api._assignment_row(_known_version(), None, [])
        assert out["current_mirror_id"] is None
        assert out["assignment_id"] is None
        assert out["version_key"] == "noble"


class TestResolveAssignmentMirror:
    def test_an_empty_mirror_id_is_the_revert_case(self):
        request = SimpleNamespace(mirror_id="")
        assert api._resolve_assignment_mirror(_FakeSession(), request, "apt") is None

    def test_a_synced_matching_mirror_resolves(self):
        row = _mirror()
        db = _FakeSession(MirrorRepository=[row])
        request = SimpleNamespace(mirror_id=str(MIRROR_UUID))
        assert api._resolve_assignment_mirror(db, request, "apt") is row

    def test_an_unknown_mirror_is_a_404(self):
        request = SimpleNamespace(mirror_id=str(MIRROR_UUID))
        with pytest.raises(HTTPException) as exc:
            api._resolve_assignment_mirror(_FakeSession(), request, "apt")
        assert exc.value.status_code == 404

    def test_an_unsynced_mirror_is_a_409(self):
        db = _FakeSession(MirrorRepository=[_mirror(last_sync_status="DISPATCHED")])
        request = SimpleNamespace(mirror_id=str(MIRROR_UUID))
        with pytest.raises(HTTPException) as exc:
            api._resolve_assignment_mirror(db, request, "apt")
        # Assigning an unsynced mirror points the fleet at an empty tree.
        assert exc.value.status_code == 409

    def test_a_package_manager_mismatch_is_a_400(self):
        db = _FakeSession(MirrorRepository=[_mirror(package_manager="dnf")])
        request = SimpleNamespace(mirror_id=str(MIRROR_UUID))
        with pytest.raises(HTTPException) as exc:
            api._resolve_assignment_mirror(db, request, "apt")
        assert exc.value.status_code == 400


class TestUpsertAssignmentRow:
    def test_an_existing_row_is_updated_and_its_previous_mirror_reported(self):
        old = uuid.uuid4()
        row = SimpleNamespace(id=uuid.uuid4(), mirror_id=old)
        db = _FakeSession(HostDefaultMirror=[row])
        out, previous = api._upsert_assignment_row(
            db, "apt", "noble", "ubuntu", _mirror()
        )
        assert out is row
        assert row.mirror_id == MIRROR_UUID
        # The caller needs the previous id to decide whether anything changed.
        assert previous == old

    def test_a_missing_row_is_created(self):
        db = _FakeSession(HostDefaultMirror=[])
        row, previous = api._upsert_assignment_row(
            db, "apt", "noble", "ubuntu", _mirror()
        )
        assert isinstance(row, models.HostDefaultMirror)
        assert previous is None
        assert db.commits == 1

    def test_a_revert_clears_the_mirror_id(self):
        row = SimpleNamespace(id=uuid.uuid4(), mirror_id=MIRROR_UUID)
        db = _FakeSession(HostDefaultMirror=[row])
        api._upsert_assignment_row(db, "apt", "noble", "ubuntu", None)
        assert row.mirror_id is None


class TestDefaultMirrorPlanFor:
    @pytest.mark.parametrize(
        "platform,builder",
        [
            ("apt", "build_apt_revert_default_mirror_plan"),
            ("dnf", "build_dnf_revert_default_mirror_plan"),
            ("zypper", "build_zypper_revert_default_mirror_plan"),
            ("pkg", "build_pkg_revert_default_mirror_plan"),
        ],
    )
    def test_a_revert_routes_to_its_platforms_builder(self, platform, builder):
        engine = _engine()
        plan = api._default_mirror_plan_for(
            engine, _known_version(platform=platform), None
        )
        assert plan == {"commands": [{"argv": [builder]}]}

    @pytest.mark.parametrize(
        "platform,builder",
        [
            ("apt", "build_apt_apply_default_mirror_plan"),
            ("dnf", "build_dnf_apply_default_mirror_plan"),
            ("zypper", "build_zypper_apply_default_mirror_plan"),
            ("pkg", "build_pkg_apply_default_mirror_plan"),
        ],
    )
    def test_an_apply_routes_to_its_platforms_builder(self, platform, builder):
        engine = _engine()
        with patch(f"{API}._resolve_mirror_url", return_value="http://m/mirror/x"):
            plan = api._default_mirror_plan_for(
                engine, _known_version(platform=platform), _mirror()
            )
        assert plan == {"commands": [{"argv": [builder]}]}

    def test_the_mirrors_own_value_wins_over_the_catalog_default(self):
        engine = _engine()
        with patch(f"{API}._resolve_mirror_url", return_value="http://m/mirror/x"):
            api._default_mirror_plan_for(
                engine,
                _known_version(default_suite="jammy"),
                _mirror(suite="oracular"),
            )
        # The catalog default is a fallback for mirrors that never set one --
        # using it over an explicit suite would repoint hosts at the wrong tree.
        engine.build_apt_apply_default_mirror_plan.assert_called_once_with(
            "http://m/mirror/x", "oracular", "main"
        )

    def test_a_mirror_with_no_suite_falls_back_to_the_catalog(self):
        engine = _engine()
        with patch(f"{API}._resolve_mirror_url", return_value="http://m/mirror/x"):
            api._default_mirror_plan_for(
                engine, _known_version(default_suite="noble"), _mirror(suite=None)
            )
        assert engine.build_apt_apply_default_mirror_plan.call_args[0][1] == "noble"

    @pytest.mark.parametrize("mirror", [None, "present"])
    def test_an_unknown_platform_yields_no_plan(self, mirror):
        target = _mirror() if mirror else None
        with patch(f"{API}._resolve_mirror_url", return_value="http://m"):
            assert (
                api._default_mirror_plan_for(
                    _engine(), _known_version(platform="apk"), target
                )
                is None
            )


class TestResolveMirrorUrl:
    def test_the_url_names_the_mirror_hosts_fqdn(self):
        session = _FakeSession(Host=[SimpleNamespace(fqdn="mirror.example.invalid")])
        with patch("backend.persistence.db.get_session_local", return_value=session):
            url = api._resolve_mirror_url(_mirror())
        assert url == "http://mirror.example.invalid/mirror/ubuntu-noble"

    def test_a_missing_host_row_falls_back_to_localhost(self):
        with patch(
            "backend.persistence.db.get_session_local", return_value=_FakeSession()
        ):
            assert api._resolve_mirror_url(_mirror()).startswith("http://localhost/")


class TestDispatchDefaultMirrorChange:
    def test_one_plan_is_queued_per_matching_host(self):
        hosts = [SimpleNamespace(id="h1"), SimpleNamespace(id="h2")]
        with patch(f"{API}._hosts_matching_version", return_value=hosts):
            with patch(
                f"{API}._default_mirror_plan_for", return_value={"commands": []}
            ):
                with patch(
                    f"{API}._dispatch_plan", side_effect=["m1", "m2"]
                ) as dispatch:
                    out = api._dispatch_default_mirror_change(
                        _engine(), _known_version(), _mirror(), _FakeSession()
                    )
        assert out == [
            {"host_id": "h1", "message_id": "m1"},
            {"host_id": "h2", "message_id": "m2"},
        ]
        assert dispatch.call_args.kwargs["action"] == "default_apply"

    def test_a_revert_uses_the_revert_action(self):
        with patch(
            f"{API}._hosts_matching_version", return_value=[SimpleNamespace(id="h1")]
        ):
            with patch(
                f"{API}._default_mirror_plan_for", return_value={"commands": []}
            ):
                with patch(f"{API}._dispatch_plan", return_value="m1") as dispatch:
                    api._dispatch_default_mirror_change(
                        _engine(), _known_version(), None, _FakeSession()
                    )
        assert dispatch.call_args.kwargs["action"] == "default_revert"

    def test_a_host_with_no_buildable_plan_is_skipped_not_failed(self):
        with patch(
            f"{API}._hosts_matching_version", return_value=[SimpleNamespace(id="h1")]
        ):
            with patch(f"{API}._default_mirror_plan_for", return_value=None):
                with patch(f"{API}._dispatch_plan") as dispatch:
                    out = api._dispatch_default_mirror_change(
                        _engine(), _known_version(), _mirror(), _FakeSession()
                    )
        dispatch.assert_not_called()
        assert out == []


class TestApplyDefaultMirrorsForNewHost:
    def _session(self, host, assignments=(), mirrors=()):
        return _FakeSession(
            Host=[host] if host else [],
            HostDefaultMirror=list(assignments),
            MirrorRepository=list(mirrors),
        )

    def _shared(self, catalog):
        shared = _FakeSession(MirrorKnownVersion=list(catalog))
        return patch(f"{API}.shared_sessionmaker", return_value=lambda: shared)

    def _host(self, release="noble"):
        return SimpleNamespace(id="h1", platform_release=release, platform_version="")

    def test_a_matching_assignment_queues_an_apply_plan(self):
        kv = _known_version()
        assignment = SimpleNamespace(
            platform="apt",
            version_key="noble",
            os_family="ubuntu",
            mirror_id=MIRROR_UUID,
        )
        session = self._session(self._host(), [assignment], [_mirror()])
        with patch("backend.persistence.db.get_session_local", return_value=session):
            with patch(f"{API}.module_loader.get_module", return_value=_engine()):
                with self._shared([kv]):
                    with patch(
                        f"{API}._default_mirror_plan_for", return_value={"c": []}
                    ):
                        with patch(f"{API}._dispatch_plan", return_value="m1"):
                            out = api.apply_default_mirrors_for_new_host("h1")
        assert out == [{"platform": "apt", "version_key": "noble", "message_id": "m1"}]

    def test_a_host_that_does_not_match_the_regex_gets_nothing(self):
        kv = _known_version()
        assignment = SimpleNamespace(
            platform="apt",
            version_key="noble",
            os_family="ubuntu",
            mirror_id=MIRROR_UUID,
        )
        session = self._session(self._host("bookworm"), [assignment], [_mirror()])
        with patch("backend.persistence.db.get_session_local", return_value=session):
            with patch(f"{API}.module_loader.get_module", return_value=_engine()):
                with self._shared([kv]):
                    with patch(f"{API}._dispatch_plan") as dispatch:
                        assert api.apply_default_mirrors_for_new_host("h1") == []
        dispatch.assert_not_called()

    def test_an_uncompilable_catalog_regex_is_skipped(self):
        kv = _known_version(match_regex="[")
        assignment = SimpleNamespace(
            platform="apt",
            version_key="noble",
            os_family="ubuntu",
            mirror_id=MIRROR_UUID,
        )
        session = self._session(self._host(), [assignment], [_mirror()])
        with patch("backend.persistence.db.get_session_local", return_value=session):
            with patch(f"{API}.module_loader.get_module", return_value=_engine()):
                with self._shared([kv]):
                    assert api.apply_default_mirrors_for_new_host("h1") == []

    def test_an_assignment_with_no_catalog_row_is_dropped(self):
        assignment = SimpleNamespace(
            platform="apt",
            version_key="gone",
            os_family="ubuntu",
            mirror_id=MIRROR_UUID,
        )
        session = self._session(self._host(), [assignment], [_mirror()])
        with patch("backend.persistence.db.get_session_local", return_value=session):
            with patch(f"{API}.module_loader.get_module", return_value=_engine()):
                with self._shared([_known_version()]):
                    assert api.apply_default_mirrors_for_new_host("h1") == []

    def test_a_deleted_mirror_is_skipped(self):
        assignment = SimpleNamespace(
            platform="apt",
            version_key="noble",
            os_family="ubuntu",
            mirror_id=MIRROR_UUID,
        )
        session = self._session(self._host(), [assignment], [])
        with patch("backend.persistence.db.get_session_local", return_value=session):
            with patch(f"{API}.module_loader.get_module", return_value=_engine()):
                with self._shared([_known_version()]):
                    assert api.apply_default_mirrors_for_new_host("h1") == []

    def test_an_unbuildable_plan_is_skipped(self):
        assignment = SimpleNamespace(
            platform="apt",
            version_key="noble",
            os_family="ubuntu",
            mirror_id=MIRROR_UUID,
        )
        session = self._session(self._host(), [assignment], [_mirror()])
        with patch("backend.persistence.db.get_session_local", return_value=session):
            with patch(f"{API}.module_loader.get_module", return_value=_engine()):
                with self._shared([_known_version()]):
                    with patch(f"{API}._default_mirror_plan_for", return_value=None):
                        assert api.apply_default_mirrors_for_new_host("h1") == []

    def test_an_unknown_host_or_unlicensed_engine_does_nothing(self):
        with patch(
            "backend.persistence.db.get_session_local", return_value=self._session(None)
        ):
            assert api.apply_default_mirrors_for_new_host("h1") == []
        session = self._session(self._host())
        with patch("backend.persistence.db.get_session_local", return_value=session):
            with patch(f"{API}.module_loader.get_module", return_value=None):
                assert api.apply_default_mirrors_for_new_host("h1") == []


class TestListDefaultMirrorAssignments:
    @pytest.mark.asyncio
    async def test_every_catalog_tuple_gets_a_row_assigned_or_not(self):
        assigned = _known_version(version_key="noble")
        unassigned = _known_version(version_key="jammy", default_suite="jammy")
        assignment = SimpleNamespace(
            id=uuid.uuid4(),
            platform="apt",
            version_key="noble",
            os_family="ubuntu",
            mirror_id=MIRROR_UUID,
            updated_at=None,
        )
        shared_db = _FakeSession(MirrorKnownVersion=[assigned, unassigned])
        db = _FakeSession(
            HostDefaultMirror=[assignment],
            MirrorRepository=[_mirror(known_version_id=assigned.id)],
        )
        with _licensed():
            out = await api.list_default_mirror_assignments(db=db, shared_db=shared_db)
        assert [r["version_key"] for r in out] == ["noble", "jammy"]
        assert out[0]["current_mirror_id"] == str(MIRROR_UUID)
        assert out[1]["current_mirror_id"] is None
        # Eligibility is per-tuple: the noble mirror must not appear as a
        # candidate for jammy.
        assert out[0]["eligible_mirrors"] and out[1]["eligible_mirrors"] == []


class TestSetDefaultMirrorAssignment:
    def _shared(self, kv):
        return _FakeSession(MirrorKnownVersion=[kv] if kv else [])

    @pytest.mark.asyncio
    async def test_an_assignment_is_persisted_and_rolled_out(self):
        kv = _known_version()
        row = SimpleNamespace(id=uuid.uuid4(), mirror_id=None)
        db = _FakeSession(HostDefaultMirror=[row], MirrorRepository=[_mirror()])
        request = api.HostDefaultMirrorRequest(mirror_id=str(MIRROR_UUID))
        with _licensed():
            with patch(
                f"{API}._dispatch_default_mirror_change",
                return_value=[{"host_id": "h1", "message_id": "m1"}],
            ):
                out = await api.set_default_mirror_assignment(
                    "apt",
                    "noble",
                    "ubuntu",
                    request=request,
                    db=db,
                    shared_db=self._shared(kv),
                    current_user="u",
                )
        assert out["mirror_id"] == str(MIRROR_UUID)
        assert out["previous_mirror_id"] is None
        # The dispatch list is what the UI polls; an empty list would look
        # like a silent success on a fleet that never got repointed.
        assert out["dispatched"] == [{"host_id": "h1", "message_id": "m1"}]

    @pytest.mark.asyncio
    async def test_a_revert_reports_the_mirror_it_replaced(self):
        kv = _known_version()
        row = SimpleNamespace(id=uuid.uuid4(), mirror_id=MIRROR_UUID)
        db = _FakeSession(HostDefaultMirror=[row])
        with _licensed():
            with patch(f"{API}._dispatch_default_mirror_change", return_value=[]):
                out = await api.set_default_mirror_assignment(
                    "apt",
                    "noble",
                    "ubuntu",
                    request=api.HostDefaultMirrorRequest(mirror_id=None),
                    db=db,
                    shared_db=self._shared(kv),
                    current_user="u",
                )
        assert out["mirror_id"] is None
        assert out["previous_mirror_id"] == str(MIRROR_UUID)

    @pytest.mark.asyncio
    async def test_an_unknown_catalog_tuple_is_a_404(self):
        with _licensed():
            with pytest.raises(HTTPException) as exc:
                await api.set_default_mirror_assignment(
                    "apt",
                    "gone",
                    "ubuntu",
                    request=api.HostDefaultMirrorRequest(mirror_id=None),
                    db=_FakeSession(),
                    shared_db=self._shared(None),
                    current_user="u",
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_an_unsynced_mirror_blocks_before_anything_is_written(self):
        kv = _known_version()
        db = _FakeSession(
            HostDefaultMirror=[],
            MirrorRepository=[_mirror(last_sync_status="FAILED")],
        )
        with _licensed():
            with pytest.raises(HTTPException) as exc:
                await api.set_default_mirror_assignment(
                    "apt",
                    "noble",
                    "ubuntu",
                    request=api.HostDefaultMirrorRequest(mirror_id=str(MIRROR_UUID)),
                    db=db,
                    shared_db=self._shared(kv),
                    current_user="u",
                )
        assert exc.value.status_code == 409
        # Hard block: no row written, no plans queued.
        assert db.commits == 0 and db.added == []


class TestUpdateMirrorSettingsCreatesTheSingleton:
    @pytest.mark.asyncio
    async def test_a_detached_settings_row_is_added_to_the_session(self):
        row = SimpleNamespace(
            mirror_root_path="/old", to_dict=lambda: {"mirror_root_path": "/new"}
        )

        class _NotContaining(_FakeSession):
            def __contains__(self, _row):
                return False

        db = _NotContaining()
        with _licensed(), patch(f"{API}._get_settings", return_value=row):
            await api.update_mirror_settings(
                MirrorSettingsRequest(mirror_root_path="/new"), db=db, current_user="u"
            )
        # _get_settings hands back an unsaved instance the first time; without
        # the add() the update commits nothing at all.
        assert db.added == [row]
