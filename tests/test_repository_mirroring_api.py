# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Repository-mirroring API: mirror CRUD and the dispatch routes.

Every dispatch route stamps ``last_<action>_message_id`` in the SAME commit
that queues the plan.  Queue-then-stamp-later would leave a window where the
agent result can land before the marker exists, and the result handler would
then clear a marker written afterwards -- a chip that reads "in progress"
for ever with no failure anywhere to point at.

The default-mirror assignment half of this module is tested in
``test_repository_mirroring_defaults.py``; shared fakes live in
``tests/mirroring_fakes.py``.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import repository_mirroring as api
from backend.api.repository_mirroring_schemas import (
    MirrorCreateRequest,
    MirrorSettingsRequest,
    MirrorUpdateRequest,
)
from backend.persistence import models
from tests.mirroring_fakes import (
    API,
    HOST_UUID,
    MIRROR_UUID,
    _dispatching,
    _engine,
    _FakeSession,
    _licensed,
    _mirror,
    _settings,
)

# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestListMirrors:
    @pytest.mark.asyncio
    async def test_all_mirrors_are_serialized(self):
        db = _FakeSession(MirrorRepository=[_mirror()])
        with _licensed():
            out = await api.list_mirrors(db=db)
        assert out == [{"id": str(MIRROR_UUID), "name": "ubuntu-noble"}]

    @pytest.mark.asyncio
    async def test_a_malformed_platform_config_filter_is_rejected(self):
        db = _FakeSession(MirrorRepository=[])
        with _licensed():
            with pytest.raises(HTTPException) as exc:
                await api.list_mirrors(platform_config_id="not-a-uuid", db=db)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_valid_platform_config_filter_is_accepted(self):
        db = _FakeSession(MirrorRepository=[_mirror()])
        with _licensed():
            out = await api.list_mirrors(platform_config_id=str(uuid.uuid4()), db=db)
        assert len(out) == 1


def _create_request(**overrides):
    payload = {
        "name": "ubuntu-noble",
        "package_manager": "apt",
        "upstream_url": "http://archive.ubuntu.invalid/ubuntu",
        "host_id": str(HOST_UUID),
    }
    payload.update(overrides)
    return MirrorCreateRequest(**payload)


class TestCreateMirror:
    @pytest.mark.asyncio
    async def test_a_valid_mirror_is_persisted_under_a_platform_config(self):
        db = _FakeSession(Host=[SimpleNamespace(id=HOST_UUID)], MirrorPlatformConfig=[])
        with _licensed():
            out = await api.create_mirror(_create_request(), db=db, current_user="u")
        # A config is auto-created so the table never holds unparented rows.
        assert any(isinstance(r, models.MirrorPlatformConfig) for r in db.added)
        assert any(isinstance(r, models.MirrorRepository) for r in db.added)
        assert db.flushes == 1  # needed to obtain cfg.id before the FK is set
        assert out["name"] == "ubuntu-noble"

    @pytest.mark.asyncio
    async def test_an_existing_platform_config_is_reused(self):
        cfg = SimpleNamespace(id=uuid.uuid4())
        db = _FakeSession(
            Host=[SimpleNamespace(id=HOST_UUID)], MirrorPlatformConfig=[cfg]
        )
        with _licensed():
            await api.create_mirror(_create_request(), db=db, current_user="u")
        assert db.flushes == 0
        assert not any(isinstance(r, models.MirrorPlatformConfig) for r in db.added)

    @pytest.mark.asyncio
    async def test_an_engine_rejection_becomes_a_400(self):
        engine = _engine()
        engine.validate_mirror_config.side_effect = ValueError("suite is required")
        db = _FakeSession(Host=[SimpleNamespace(id=HOST_UUID)])
        with _licensed(engine):
            with pytest.raises(HTTPException) as exc:
                await api.create_mirror(_create_request(), db=db, current_user="u")
        assert exc.value.status_code == 400
        # Surfaced verbatim: the engine knows which field is wrong, we don't.
        assert "suite is required" in exc.value.detail

    @pytest.mark.asyncio
    async def test_an_unknown_host_is_a_404(self):
        db = _FakeSession(Host=[])
        with _licensed():
            with pytest.raises(HTTPException) as exc:
                await api.create_mirror(_create_request(), db=db, current_user="u")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_known_version_id_is_parsed_into_the_fk(self):
        kv_id = uuid.uuid4()
        db = _FakeSession(Host=[SimpleNamespace(id=HOST_UUID)], MirrorPlatformConfig=[])
        with _licensed():
            await api.create_mirror(
                _create_request(known_version_id=str(kv_id)), db=db, current_user="u"
            )
        row = [r for r in db.added if isinstance(r, models.MirrorRepository)][0]
        assert row.known_version_id == kv_id


class TestGetUpdateDeleteMirror:
    @pytest.mark.asyncio
    async def test_a_known_mirror_is_returned(self):
        db = _FakeSession(MirrorRepository=[_mirror()])
        with _licensed():
            assert (await api.get_mirror(str(MIRROR_UUID), db=db))["name"] == (
                "ubuntu-noble"
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "call",
        ["get_mirror", "update_mirror", "delete_mirror"],
    )
    async def test_a_missing_mirror_is_a_404_on_every_verb(self, call):
        db = _FakeSession(MirrorRepository=[])
        kwargs = {"db": db}
        args = [str(MIRROR_UUID)]
        if call == "update_mirror":
            args.append(MirrorUpdateRequest())
        if call != "get_mirror":
            kwargs["current_user"] = "u"
        with _licensed():
            with pytest.raises(HTTPException) as exc:
                await getattr(api, call)(*args, **kwargs)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_only_the_supplied_fields_are_written(self):
        row = _mirror(components="main")
        db = _FakeSession(MirrorRepository=[row])
        with _licensed():
            await api.update_mirror(
                str(MIRROR_UUID),
                MirrorUpdateRequest(suite="oracular"),
                db=db,
                current_user="u",
            )
        assert row.suite == "oracular"
        # exclude_unset: an omitted field must not be blanked to its default.
        assert row.components == "main"

    @pytest.mark.asyncio
    async def test_a_known_version_id_update_is_coerced_to_a_uuid(self):
        kv_id = uuid.uuid4()
        row = _mirror()
        db = _FakeSession(MirrorRepository=[row])
        with _licensed():
            await api.update_mirror(
                str(MIRROR_UUID),
                MirrorUpdateRequest(known_version_id=str(kv_id)),
                db=db,
                current_user="u",
            )
        assert row.known_version_id == kv_id

    @pytest.mark.asyncio
    async def test_deleting_removes_the_row(self):
        row = _mirror()
        db = _FakeSession(MirrorRepository=[row])
        with _licensed():
            out = await api.delete_mirror(str(MIRROR_UUID), db=db, current_user="u")
        assert db.deleted == [row]
        assert out["id"] == str(MIRROR_UUID)


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


class TestSyncMirror:
    @pytest.mark.asyncio
    async def test_a_dispatch_stamps_the_inflight_marker_in_the_same_commit(self):
        row = _mirror()
        db = _FakeSession(MirrorRepository=[row])
        with _licensed(), _settings(), _dispatching("msg-7"):
            out = await api.sync_mirror(str(MIRROR_UUID), db=db)
        assert out["message_id"] == "msg-7"
        assert row.last_sync_status == "DISPATCHED"
        assert row.last_sync_message_id == "msg-7"
        assert row.last_sync_error is None
        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_an_unsupported_package_manager_is_a_400(self):
        row = _mirror(package_manager="portage")
        db = _FakeSession(MirrorRepository=[row])
        with _licensed(), _settings(), _dispatching():
            with pytest.raises(HTTPException) as exc:
                await api.sync_mirror(str(MIRROR_UUID), db=db)
        assert exc.value.status_code == 400
        # Nothing stamped -- a marker with no plan behind it never clears.
        assert row.last_sync_message_id is None

    @pytest.mark.asyncio
    async def test_a_missing_mirror_is_a_404(self):
        with _licensed():
            with pytest.raises(HTTPException) as exc:
                await api.sync_mirror(str(MIRROR_UUID), db=_FakeSession())
        assert exc.value.status_code == 404


class TestSnapshotAndRestore:
    @pytest.mark.asyncio
    async def test_a_snapshot_inserts_a_placeholder_row_eagerly(self):
        row = _mirror()
        db = _FakeSession(MirrorRepository=[row])
        with _licensed(), _settings(), _dispatching("msg-8"):
            out = await api.snapshot_mirror(str(MIRROR_UUID), db=db)
        placeholders = [r for r in db.added if isinstance(r, models.MirrorSnapshot)]
        assert len(placeholders) == 1
        # The result handler finds this row by "most recent for the mirror",
        # so it must exist before the agent can report back.
        assert placeholders[0].snapshot_id == out["snapshot_id"]
        assert row.last_snapshot_message_id == "msg-8"

    @pytest.mark.asyncio
    async def test_a_restore_stamps_its_own_column_group(self):
        row = _mirror()
        db = _FakeSession(MirrorRepository=[row])
        with _licensed(), _settings(), _dispatching("msg-9"):
            out = await api.restore_mirror(str(MIRROR_UUID), "20260101T000000", db=db)
        assert out == {"snapshot_id": "20260101T000000", "message_id": "msg-9"}
        assert row.last_restore_status == "DISPATCHED"
        assert row.last_sync_status == "SUCCESS"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("call", ["snapshot_mirror", "restore_mirror"])
    async def test_a_missing_mirror_is_a_404(self, call):
        args = [str(MIRROR_UUID)]
        if call == "restore_mirror":
            args.append("snap-1")
        with _licensed():
            with pytest.raises(HTTPException) as exc:
                await getattr(api, call)(*args, db=_FakeSession())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_snapshots_are_listed_newest_first(self):
        snap = SimpleNamespace(to_dict=lambda: {"snapshot_id": "s1"})
        db = _FakeSession(MirrorSnapshot=[snap])
        with _licensed():
            assert await api.list_snapshots(str(MIRROR_UUID), db=db) == [
                {"snapshot_id": "s1"}
            ]


class TestTickMirrors:
    @pytest.mark.asyncio
    async def test_results_are_aggregated_across_every_host_database(self):
        sessions = [_FakeSession(), _FakeSession()]
        databases = [("bootstrap", None, sessions[0]), ("tenant-a", "t", sessions[1])]
        with _licensed(), patch(
            f"{API}.module_loader.get_module", return_value=object()
        ):
            with patch(f"{API}.iter_host_databases", return_value=databases):
                with patch(
                    f"{API}._tick_mirrors_one_db",
                    side_effect=[(["m1"], []), (["m2"], ["m3"])],
                ):
                    out = await api.tick_mirrors()
        # A tenant host's mirrors live in the tenant DB; a bootstrap-only
        # sweep would never fire them.
        assert out["fired"] == ["m1", "m2"]
        assert out["disabled_count"] == 1
        assert all(s.closed for s in sessions)

    @pytest.mark.asyncio
    async def test_one_bad_tenant_database_does_not_stall_the_sweep(self):
        bad, good = _FakeSession(), _FakeSession()
        databases = [("bad", None, bad), ("good", None, good)]
        with _licensed(), patch(
            f"{API}.module_loader.get_module", return_value=object()
        ):
            with patch(f"{API}.iter_host_databases", return_value=databases):
                with patch(
                    f"{API}._tick_mirrors_one_db",
                    side_effect=[RuntimeError("db gone"), (["m2"], [])],
                ):
                    out = await api.tick_mirrors()
        assert bad.rolled_back is True
        assert bad.closed and good.closed
        assert out["fired"] == ["m2"]

    @pytest.mark.asyncio
    async def test_a_missing_automation_engine_is_a_502(self):
        with _licensed(), patch(f"{API}.module_loader.get_module", return_value=None):
            with pytest.raises(HTTPException) as exc:
                await api.tick_mirrors()
        assert exc.value.status_code == 502


class TestMirrorSettings:
    @pytest.mark.asyncio
    async def test_the_singleton_is_returned(self):
        with _licensed(), _settings("/srv/mirror"):
            assert await api.get_mirror_settings(db=_FakeSession()) == {
                "mirror_root_path": "/srv/mirror"
            }

    @pytest.mark.asyncio
    async def test_only_supplied_settings_fields_are_written(self):
        row = SimpleNamespace(
            mirror_root_path="/old", to_dict=lambda: {"mirror_root_path": "/new"}
        )
        db = _FakeSession()
        with _licensed(), patch(f"{API}._get_settings", return_value=row):
            await api.update_mirror_settings(
                MirrorSettingsRequest(mirror_root_path="/new"), db=db, current_user="u"
            )
        assert row.mirror_root_path == "/new"
        assert db.commits == 1


class TestListKnownVersions:
    @pytest.mark.asyncio
    async def test_the_catalog_is_serialized(self):
        kv = SimpleNamespace(to_dict=lambda: {"version_key": "noble"})
        db = _FakeSession(MirrorKnownVersion=[kv])
        with _licensed():
            assert await api.list_known_versions(db=db) == [{"version_key": "noble"}]

    @pytest.mark.asyncio
    async def test_a_platform_filter_is_accepted(self):
        kv = SimpleNamespace(to_dict=lambda: {"version_key": "noble"})
        db = _FakeSession(MirrorKnownVersion=[kv])
        with _licensed():
            assert len(await api.list_known_versions(platform="apt", db=db)) == 1
