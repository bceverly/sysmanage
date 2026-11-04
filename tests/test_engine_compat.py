# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""An engine built for a newer server must never replace a working engine.

Written after 2026-11-04: backup_engine 1.0.10 (needs OSS revision
``q77ossbackupkeys``) was swapped in over a working 1.0.9 on a server that
ships only up to ``q75backuptagpolicy``.  The load-time gate refused it, the
UI said "run alembic upgrade head" (which cannot reach a migration the server
does not have), and the engine was gone until a newer server shipped.
"""

import io
import json
import os
import tarfile
from unittest.mock import MagicMock, patch

import pytest

from backend.licensing import engine_compat
from backend.licensing.engine_compat import (
    EngineTooNewError,
    drop_deferred,
    get_pending_updates,
    is_deferred,
    probe_required_revision,
    record_deferred,
    refuse_if_too_new,
)
from backend.licensing.migration_compat import (
    KIND_MIGRATION_PENDING,
    KIND_SERVER_TOO_OLD,
    check_module_compatibility,
    clear_incompatibility,
    is_known_revision,
)
from backend.licensing.module_loader import ModuleLoader

ALEMBIC_CFG = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
)
KNOWN_REV = "q75backuptagpolicy"
UNKNOWN_REV = "zz99notshippedhere"
PROBE = "backend.licensing.engine_compat.probe_required_revision"


@pytest.fixture(autouse=True)
def _empty_registries():
    for entry in get_pending_updates():
        engine_compat.clear_pending_update(entry.module_code)
    clear_incompatibility("thing")
    yield
    for entry in get_pending_updates():
        engine_compat.clear_pending_update(entry.module_code)
    clear_incompatibility("thing")


def _live_install(modules_path, version="1.0.9", code="thing", pyver="3.14"):
    """An installed engine: a compiled module + metadata.json."""
    live = os.path.join(modules_path, f"{code}_{pyver}")
    os.makedirs(live)
    so_path = os.path.join(live, f"{code}.abi3.so")
    with open(so_path, "wb") as handle:
        handle.write(b"the version that already loads")
    with open(os.path.join(live, "metadata.json"), "w", encoding="utf-8") as handle:
        json.dump({"version": version}, handle)
    return live, so_path


def _bundle(tmp_path, version="1.0.10", code="thing"):
    path = tmp_path / "bundle.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for name, body in (
            (f"{code}.abi3.so", b"the newer build"),
            ("metadata.json", json.dumps({"version": version}).encode()),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return str(path)


class TestIsKnownRevision:
    def test_a_shipped_revision_is_known(self):
        assert is_known_revision(KNOWN_REV, ALEMBIC_CFG) is True

    def test_a_revision_this_server_lacks_is_not_known(self):
        assert is_known_revision(UNKNOWN_REV, ALEMBIC_CFG) is False

    def test_unreadable_scripts_say_nothing(self):
        assert is_known_revision(KNOWN_REV, "/nonexistent.ini") is None


class TestLoadTimeGateNamesTheRightRemedy:
    @staticmethod
    def _session(current):
        session = MagicMock()
        session.execute.return_value.fetchall.return_value = [(current,)]
        return session

    def test_a_revision_not_shipped_here_needs_a_newer_server(self):
        incompat = check_module_compatibility(
            "thing",
            {"min_oss_alembic_revision": UNKNOWN_REV, "version": "1.0.10"},
            self._session(KNOWN_REV),
            ALEMBIC_CFG,
        )
        assert incompat.kind == KIND_SERVER_TOO_OLD

    def test_a_shipped_but_unapplied_revision_still_needs_migrations(self):
        # q76 descends from q75: shipped here, not applied in a DB at q75.
        incompat = check_module_compatibility(
            "thing",
            {"min_oss_alembic_revision": "q76backupescrow"},
            self._session(KNOWN_REV),
            ALEMBIC_CFG,
        )
        assert incompat.kind == KIND_MIGRATION_PENDING

    def test_unreadable_scripts_keep_the_old_advice(self):
        incompat = check_module_compatibility(
            "thing",
            {"min_oss_alembic_revision": UNKNOWN_REV},
            self._session(KNOWN_REV),
            "/nonexistent.ini",
        )
        assert incompat.kind == KIND_MIGRATION_PENDING


class TestProbe:
    @staticmethod
    def _engine(tmp_path, body):
        path = tmp_path / "thing.py"
        path.write_text(body, encoding="utf-8")
        return str(path)

    def test_reads_the_declared_revision(self, tmp_path):
        so_path = self._engine(
            tmp_path,
            "print('noise at import')\n"
            "def get_module_info():\n"
            f"    return {{'min_oss_alembic_revision': '{UNKNOWN_REV}'}}\n",
        )
        assert probe_required_revision(so_path, "thing") == UNKNOWN_REV

    def test_no_declaration_is_none(self, tmp_path):
        so_path = self._engine(tmp_path, "def get_module_info():\n    return {}\n")
        assert probe_required_revision(so_path, "thing") is None

    def test_an_engine_that_fails_to_import_is_indeterminate(self, tmp_path):
        so_path = self._engine(tmp_path, "raise ImportError('nope')\n")
        assert probe_required_revision(so_path, "thing") is None


class TestRefuseIfTooNew:
    def test_raises_when_a_working_engine_would_be_replaced(self, tmp_path):
        live, so_path = _live_install(str(tmp_path))
        with patch(PROBE, return_value=UNKNOWN_REV):
            with pytest.raises(EngineTooNewError) as caught:
                refuse_if_too_new("staged.so", "thing", live, ALEMBIC_CFG)
        assert caught.value.live_path == so_path
        assert caught.value.required_revision == UNKNOWN_REV

    def test_a_revision_shipped_here_is_installed(self, tmp_path):
        live, _so = _live_install(str(tmp_path))
        with patch(PROBE, return_value=KNOWN_REV):
            refuse_if_too_new("staged.so", "thing", live, ALEMBIC_CFG)

    def test_an_indeterminate_probe_is_installed(self, tmp_path):
        live, _so = _live_install(str(tmp_path))
        with patch(PROBE, return_value=None):
            refuse_if_too_new("staged.so", "thing", live, ALEMBIC_CFG)

    def test_a_fresh_install_is_not_probed(self, tmp_path):
        with patch(PROBE) as probe:
            refuse_if_too_new(
                "staged.so", "thing", str(tmp_path / "absent"), ALEMBIC_CFG
            )
        probe.assert_not_called()


class TestTheSwapKeepsTheWorkingEngine:
    def test_a_too_new_bundle_leaves_the_install_untouched(self, tmp_path):
        modules_path = str(tmp_path / "modules")
        live, so_path = _live_install(modules_path)
        loader = ModuleLoader()
        with patch("backend.licensing.module_loader.verify_module_dir"), patch(
            PROBE, return_value=UNKNOWN_REV
        ):
            with pytest.raises(EngineTooNewError):
                loader._extract_module_bundle(  # pylint: disable=protected-access
                    _bundle(tmp_path), modules_path, "thing", "3.14"
                )
        with open(so_path, "rb") as handle:
            assert handle.read() == b"the version that already loads"
        assert engine_compat.installed_version(live) == "1.0.9"
        assert sorted(os.listdir(modules_path)) == ["thing_3.14"], "staging leaked"

    @pytest.mark.asyncio
    async def test_download_keeps_and_reports_the_installed_engine(self, tmp_path):
        modules_path = str(tmp_path / "modules")
        _live, so_path = _live_install(modules_path)
        bundle = _bundle(tmp_path)
        loader = ModuleLoader()

        async def _fetch(_url, _key, temp_path, _code, _platform):
            os.replace(bundle, temp_path)
            return None, "1.0.10"

        config = {"license": {"key": "k", "phone_home_url": "https://ls"}}
        with patch(
            "backend.licensing.module_loader.get_config", return_value=config
        ), patch.object(
            loader, "_get_modules_path", return_value=modules_path
        ), patch.object(
            loader, "_fetch_module_bytes", side_effect=_fetch
        ), patch.object(
            loader, "_get_cached_module_version", return_value="1.0.9"
        ), patch.object(
            loader, "_save_module_to_cache"
        ) as save, patch.object(
            loader, "_load_module_from_path", return_value=True
        ) as load, patch(
            "backend.licensing.module_loader.verify_module_dir"
        ), patch(
            PROBE, return_value=UNKNOWN_REV
        ):
            ok = await loader._download_and_cache_module(  # pylint: disable=protected-access
                "thing"
            )

        assert ok is True
        save.assert_not_called()  # the cache still records the kept 1.0.9
        load.assert_called_once_with("thing", so_path)
        assert len(get_pending_updates()) == 1
        pending = get_pending_updates()[0]
        assert (pending.module_code, pending.version, pending.kept_version) == (
            "thing",
            "1.0.10",
            "1.0.9",
        )
        assert pending.required_revision == UNKNOWN_REV


class TestNoRedownloadLoop:
    @staticmethod
    def _defer(version="1.0.10", file_hash="aaaa"):
        record_deferred(
            EngineTooNewError("thing", UNKNOWN_REV, "/x/thing_3.14/thing.so"),
            version,
            file_hash,
            "1.0.9",
        )

    def test_the_same_build_is_deferred(self):
        self._defer()
        assert is_deferred("thing", "1.0.10", "AAAA") is True

    def test_a_rebuild_or_newer_version_is_fetched_again(self):
        self._defer()
        assert is_deferred("thing", "1.0.10", "bbbb") is False
        assert is_deferred("thing", "1.0.11", "aaaa") is False

    def test_drop_deferred_filters_only_the_deferred_build(self):
        self._defer()
        server = {
            "thing": {"version": "1.0.10", "file_hash": "aaaa"},
            "other": {"version": "2.0.0", "file_hash": "cccc"},
        }
        assert list(drop_deferred(server)) == ["other"]

    @pytest.mark.asyncio
    async def test_check_for_updates_skips_a_deferred_build(self):
        self._defer()
        loader = ModuleLoader()

        async def _versions():
            return {"modules": {"thing": {"version": "1.0.10", "file_hash": "aaaa"}}}

        loader.query_server_versions = _versions
        loader._get_cached_module_version = lambda code: "1.0.9"
        assert await loader.check_for_updates() == []


class TestApiReportsTheDeferral:
    @pytest.mark.asyncio
    async def test_pending_updates_and_kind_are_returned(self):
        # pylint: disable=import-outside-toplevel
        from backend.api.license_management import get_module_compatibility

        TestNoRedownloadLoop._defer()  # pylint: disable=protected-access
        session = MagicMock()
        session.execute.return_value.fetchall.return_value = [(KNOWN_REV,)]
        check_module_compatibility(
            "thing", {"min_oss_alembic_revision": UNKNOWN_REV}, session, ALEMBIC_CFG
        )
        response = await get_module_compatibility(current_user="u@example.com")
        assert [
            e.kind for e in response.incompatibilities if e.module_code == "thing"
        ] == [KIND_SERVER_TOO_OLD]
        [pending] = response.pending_updates
        assert (pending.version, pending.kept_version) == ("1.0.10", "1.0.9")
