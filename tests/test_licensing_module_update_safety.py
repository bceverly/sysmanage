# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A module update must never leave the machine worse than it found it.

Both rules here were written after a routine ``make migrate`` on 2026-08-29
rolled five working licensed engines back to pre-signing builds that then
refused to load. ``alerting_engine`` went from a loading 1.0.19 to an
unloadable 1.0.8, the feature silently vanished, and the command exited 0.

Two independent defects combined, so there are two independent guards:

  * the updater treated ANY version difference as an update, so the older
    version on the license server looked like something to install; and
  * the live directory was overwritten BEFORE the bundle's signature was
    checked, so failing that check destroyed the working install.

Either one alone is survivable. Together they brick a licensed feature.
"""

import io
import os
import tarfile
from unittest.mock import patch

import pytest

from backend.licensing.module_loader import ModuleLoader
from backend.licensing.module_loader_mixin import _is_newer, _version_tuple
from backend.licensing.module_signature import ModuleSignatureError


def _async_return(value):
    """A zero-arg async callable returning ``value``."""

    async def _call():
        return value

    return _call


class TestVersionComparison:
    def test_a_later_patch_is_newer(self):
        assert _is_newer("1.0.19", "1.0.8") is True

    def test_an_earlier_patch_is_not_newer(self):
        # THE bug: string comparison puts "1.0.8" after "1.0.19", so the
        # license server's older build looked like an upgrade.
        assert _is_newer("1.0.8", "1.0.19") is False

    def test_the_same_version_is_not_newer(self):
        assert _is_newer("1.0.19", "1.0.19") is False

    def test_components_are_compared_numerically_not_as_text(self):
        assert _version_tuple("1.0.19") > _version_tuple("1.0.8")
        assert _version_tuple("2.0.1") > _version_tuple("1.9.9")

    def test_a_non_numeric_component_does_not_raise(self):
        # A malformed version from the server must not take down the check.
        assert _is_newer("1.0.0", "1.0.dev") is True

    def test_differing_lengths_compare_sanely(self):
        assert _is_newer("1.1", "1.0.9") is True


def _bundle_with_so(tmp_path, name="thing.abi3.so", body=b"\x7fELF-not-really"):
    """A tar.gz shaped like a real module bundle."""
    path = tmp_path / "bundle.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
        meta = b'{"version": "9.9.9"}'
        minfo = tarfile.TarInfo("metadata.json")
        minfo.size = len(meta)
        tar.addfile(minfo, io.BytesIO(meta))
    return str(path)


class TestVerificationHappensBeforeTheSwap:
    """The live directory must survive a bundle that fails verification.

    ``_extract_module_bundle`` documents itself as leaving "a previously-working
    install intact" when a download is bad. It honoured that for a corrupt
    archive but NOT for an inauthentic one, because the signature was checked
    later, at load time -- after the swap had already happened.
    """

    @staticmethod
    def _existing_install(modules_path, code="thing", pyver="3.14"):
        live = os.path.join(modules_path, f"{code}_{pyver}")
        os.makedirs(live)
        marker = os.path.join(live, "WORKING")
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("the version that already loads")
        return live, marker

    def test_an_unsigned_bundle_does_not_replace_a_working_install(self, tmp_path):
        modules_path = str(tmp_path / "modules")
        os.makedirs(modules_path)
        live, marker = self._existing_install(modules_path)
        bundle = _bundle_with_so(tmp_path)

        loader = ModuleLoader()
        with patch(
            "backend.licensing.module_loader.verify_module_dir",
            side_effect=ModuleSignatureError("unsigned module: MANIFEST.json missing"),
        ):
            result = loader._extract_module_bundle(  # pylint: disable=protected-access
                bundle, modules_path, "thing", "3.14"
            )

        assert result is None, "an unverifiable bundle must not be installed"
        assert os.path.exists(marker), "the working install was destroyed"
        with open(marker, encoding="utf-8") as handle:
            assert handle.read() == "the version that already loads"
        assert not os.path.exists(live + ".incoming"), "staging dir leaked"

    def test_a_verified_bundle_is_installed(self, tmp_path):
        # The guard must not block legitimate updates.
        modules_path = str(tmp_path / "modules")
        os.makedirs(modules_path)
        live, marker = self._existing_install(modules_path)
        bundle = _bundle_with_so(tmp_path)

        loader = ModuleLoader()
        with patch("backend.licensing.module_loader.verify_module_dir"):
            result = loader._extract_module_bundle(  # pylint: disable=protected-access
                bundle, modules_path, "thing", "3.14"
            )

        assert result is not None and result.endswith("thing.abi3.so")
        assert not os.path.exists(marker), "the old install should be replaced"
        assert os.path.exists(os.path.join(live, "thing.abi3.so"))

    def test_a_first_install_still_works_with_nothing_to_preserve(self, tmp_path):
        modules_path = str(tmp_path / "modules")
        os.makedirs(modules_path)
        bundle = _bundle_with_so(tmp_path)

        loader = ModuleLoader()
        with patch("backend.licensing.module_loader.verify_module_dir"):
            result = loader._extract_module_bundle(  # pylint: disable=protected-access
                bundle, modules_path, "thing", "3.14"
            )
        assert result is not None

    def test_verification_is_given_the_staging_dir_not_the_live_one(self, tmp_path):
        # Verifying the LIVE directory would pass on the old contents and prove
        # nothing about what is being installed.
        modules_path = str(tmp_path / "modules")
        os.makedirs(modules_path)
        self._existing_install(modules_path)
        bundle = _bundle_with_so(tmp_path)

        seen = {}

        def _record(module_dir, code, so_path, platform_info=None):
            seen["dir"] = module_dir
            seen["so"] = so_path

        loader = ModuleLoader()
        with patch(
            "backend.licensing.module_loader.verify_module_dir", side_effect=_record
        ):
            loader._extract_module_bundle(  # pylint: disable=protected-access
                bundle, modules_path, "thing", "3.14"
            )

        assert seen["dir"].endswith(".incoming")
        assert seen["so"].startswith(seen["dir"])

    def test_a_bundle_with_no_compiled_module_is_still_rejected(self, tmp_path):
        # The pre-existing structural guard must survive the new one.
        modules_path = str(tmp_path / "modules")
        os.makedirs(modules_path)
        _live, marker = self._existing_install(modules_path)
        empty = tmp_path / "empty.tar.gz"
        with tarfile.open(empty, "w:gz") as tar:
            info = tarfile.TarInfo("README")
            info.size = 2
            tar.addfile(info, io.BytesIO(b"hi"))

        loader = ModuleLoader()
        with patch("backend.licensing.module_loader.verify_module_dir"):
            result = loader._extract_module_bundle(  # pylint: disable=protected-access
                str(empty), modules_path, "thing", "3.14"
            )
        assert result is None
        assert os.path.exists(marker)


class TestFailuresAreRecordedForTooling:
    """Operator tooling must be able to turn a failed update into an exit code.

    The server keeps booting on a failed update (a network blip must not take
    the product down, and the existing install is still intact). But `make
    migrate` printing five REFUSING errors and then exiting 0 is how a broken
    deployment ships.
    """

    def test_a_fresh_loader_starts_with_no_failures(self):
        assert ModuleLoader().last_update_failures == []

    @pytest.mark.asyncio
    async def test_failed_updates_are_recorded(self):
        loader = ModuleLoader()
        with patch.object(
            loader,
            "update_modules",
            return_value={"good_engine": True, "bad_engine": False},
        ):
            await loader.check_and_update_on_startup()
        assert loader.last_update_failures == ["bad_engine"]

    @pytest.mark.asyncio
    async def test_a_clean_run_clears_previous_failures(self):
        loader = ModuleLoader()
        loader.last_update_failures = ["stale"]
        with patch.object(loader, "update_modules", return_value={"engine": True}):
            await loader.check_and_update_on_startup()
        assert loader.last_update_failures == []

    @pytest.mark.asyncio
    async def test_a_raising_update_check_is_recorded_not_swallowed(self):
        loader = ModuleLoader()
        with patch.object(loader, "update_modules", side_effect=RuntimeError("boom")):
            await loader.check_and_update_on_startup()
        assert loader.last_update_failures, "a raised failure must still be visible"


class TestTheDecisionPathRefusesDowngrades:
    """`check_for_updates` is where the downgrade actually happened.

    Testing `_is_newer` alone would not catch the real regression: the helper
    can be perfectly correct while the call site still asks `!=`. These drive
    the decision itself.
    """

    @staticmethod
    def _loader(server_version, local_version, server_hash="", local_hash=""):
        loader = ModuleLoader()
        loader.query_server_versions = _async_return(
            {
                "modules": {
                    "thing": {"version": server_version, "file_hash": server_hash}
                }
            }
        )
        loader._get_cached_module_version = lambda code: local_version
        loader._get_cached_module_hash = lambda code: local_hash
        return loader

    @pytest.mark.asyncio
    async def test_an_older_server_version_is_not_installed(self):
        # THE 2026-08-29 event: local 1.0.19, license server still advertising
        # 1.0.8 because it re-indexes on its own schedule. This must be a
        # no-op, not a rollback.
        loader = self._loader(server_version="1.0.8", local_version="1.0.19")
        assert await loader.check_for_updates() == []

    @pytest.mark.asyncio
    async def test_a_newer_server_version_is_still_installed(self):
        loader = self._loader(server_version="1.0.19", local_version="1.0.8")
        assert await loader.check_for_updates() == ["thing"]

    @pytest.mark.asyncio
    async def test_a_module_absent_locally_is_installed(self):
        loader = self._loader(server_version="1.0.1", local_version=None)
        assert await loader.check_for_updates() == ["thing"]

    @pytest.mark.asyncio
    async def test_a_rebuild_at_the_same_version_is_still_detected(self):
        # Hash-based rebuild detection must survive the no-downgrade rule.
        loader = self._loader(
            server_version="1.0.19",
            local_version="1.0.19",
            server_hash="aaaa",
            local_hash="bbbb",
        )
        assert await loader.check_for_updates() == ["thing"]

    @pytest.mark.asyncio
    async def test_an_identical_module_is_left_alone(self):
        loader = self._loader(
            server_version="1.0.19",
            local_version="1.0.19",
            server_hash="aaaa",
            local_hash="aaaa",
        )
        assert await loader.check_for_updates() == []
