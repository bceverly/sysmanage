"""Locate and load the real compiled Pro+ engine ``.so`` files for the running
interpreter and platform, from the canonical ``sysmanage-professional-plus``
build-artifact tree.

Why this exists
---------------
Every Pro+ engine test used to carry its own ad-hoc loader, and they drifted
out of sync with what ``make build`` actually produces:

* the artifact path hardcoded ``linux/x86_64`` — never matches darwin/aarch64,
  so the engines were undiscoverable on macOS;
* the build emits a ``<engine>.tar.gz`` *bundle* (``.so`` + ``metadata.json``),
  not a bare ``.so`` on disk, so the ``*.so`` globs found nothing;
* the multitenancy loader imported from ``module-source`` and picked up a
  stale, wrong-ABI ``.so`` (e.g. a cpython-314 build under a 3.13 venv).

The net effect was ~57 multitenancy/federation tests *silently skipping* no
matter how many times the engines were rebuilt and pushed.  This module is the
single source of truth: detect platform/arch/py the same way the build lays the
tree out, read the ``.tar.gz`` bundle, extract the matching-ABI ``.so`` once,
and load it — with the production and dev-build locations as fallbacks.

``require_engine`` additionally encodes the *policy*: a genuine OSS-only run
(no Pro+ checkout) still skips, but a Pro+ checkout that can't yield a loadable
engine for this platform/interpreter now **fails loudly** instead of hiding.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
import sysconfig
import tarfile
import tempfile
from pathlib import Path

# Where the Pro+ build writes per-platform artifacts (sibling dev checkout).
_PROPLUS_ROOT = Path.home() / "dev" / "sysmanage-professional-plus"
_STORAGE_MODULES = _PROPLUS_ROOT / "storage" / "modules"
# Production-deployed raw ``.so`` location (license-server download target).
_PROD_MODULES = Path("/var/lib/sysmanage/modules")
# Session cache for ``.so`` files extracted from bundles.
# Namespaced by pytest-xdist worker: several workers extract the same engine
# concurrently under -n auto, and a shared cache path races — one worker's write
# hits a file another worker already holds open/loaded (on Windows the loaded .pyd
# is a locked DLL -> PermissionError). A per-worker dir gives each its own copy.
_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "main")
_EXTRACT_DIR = Path(tempfile.gettempdir()) / "sysmanage-test-engines" / _WORKER

# Engine modules already loaded this session, keyed by name.
_loaded: dict[str, object] = {}


def proplus_present() -> bool:
    """True when a sibling Pro+ checkout exists (so engines are *expected*)."""
    return _PROPLUS_ROOT.is_dir()


def _plat_arch_py() -> tuple[str, str, str]:
    """Platform / arch / ``X.Y`` exactly as the build lays out its tree.

    The Makefile normalizes ``arm64 -> aarch64`` and ``amd64 -> x86_64``; macOS
    reports ``arm64`` from ``platform.machine()``, so mirror that mapping here
    or nothing matches on Apple Silicon.
    """
    plat = platform.system().lower()  # darwin / linux / freebsd / ...
    machine = platform.machine().lower()
    arch = {"arm64": "aarch64", "amd64": "x86_64"}.get(machine, machine)
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    return plat, arch, py


def _bundle_for(name: str) -> Path | None:
    """Newest ``<engine>.tar.gz`` bundle for this interpreter/platform, or None."""
    plat, arch, py = _plat_arch_py()
    base = _STORAGE_MODULES / name
    if not base.is_dir():
        return None
    for version in sorted(base.iterdir(), reverse=True):  # newest version wins
        # ``abi3`` is the current canonical layout (the abi3 bundle loads on every
        # CPython 3.10+); ``<py>`` (e.g. ``3.13``) is the legacy per-version layout,
        # kept as a fallback. The bundle is the committed deliverable — the loader
        # falls back to it when no loose per-arch binary has been built locally.
        for sub in ("abi3", py):
            bundle = version / plat / arch / sub / f"{name}.tar.gz"
            if bundle.is_file():
                return bundle
    return None


def _abi3_binary_for(name: str) -> Path | None:
    """Newest abi3 engine binary under ``<version>/<plat>/<arch>/abi3/``, or None.

    The Pro+ build migrated from a per-Python-version ``.tar.gz`` bundle to a
    single **abi3** (CPython limited-API) binary that loads on 3.10+, laid out as
    ``<version>/<plat>/<arch>/abi3/<name><ext>`` — a bare ``.pyd`` on Windows, a
    ``.so`` elsewhere. This is now the canonical layout; prefer it over the
    legacy per-version bundle.
    """
    plat, arch, _py = _plat_arch_py()
    base = _STORAGE_MODULES / name
    if not base.is_dir():
        return None
    suffix = ".pyd" if sys.platform == "win32" else ".so"
    for version in sorted(base.iterdir(), reverse=True):  # newest version wins
        abi3_dir = version / plat / arch / "abi3"
        if not abi3_dir.is_dir():
            continue
        for cand in sorted(abi3_dir.glob(f"{name}*{suffix}")):
            return cand
    return None


def _abi3_bundle_for(name: str) -> Path | None:
    """Newest abi3 ``<name>.tar.gz`` bundle under ``<version>/<plat>/<arch>/abi3/``.

    ``make build`` runs ``package-bundles``, which replaces the bare abi3 ``.so``
    with a ``<name>.tar.gz`` bundle (the ``.so`` + gettext catalog + metadata) in
    the same ``abi3/`` dir and removes the bare binary.  Handle that alongside the
    bare-``.so`` case so a full ``make build`` (not just ``make build-modules``)
    still yields a loadable engine.
    """
    plat, arch, _py = _plat_arch_py()
    base = _STORAGE_MODULES / name
    if not base.is_dir():
        return None
    for version in sorted(base.iterdir(), reverse=True):  # newest version wins
        bundle = version / plat / arch / "abi3" / f"{name}.tar.gz"
        if bundle.is_file():
            return bundle
    return None


def _cache_copy(name: str, src: Path) -> Path:
    """Copy an engine binary into the session cache and return the copy.

    Loading the ``.pyd`` directly from ``storage/modules`` would lock that file on
    Windows (an in-use DLL cannot be deleted), which then breaks a subsequent
    ``make build-modules`` — its clear-stale step can't unlink the loaded artifact.
    Load from a throwaway copy instead, mirroring ``_so_from_bundle``'s extract.
    """
    dest = _EXTRACT_DIR / name
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / src.name
    if not target.exists() or target.stat().st_mtime < src.stat().st_mtime:
        target.write_bytes(src.read_bytes())
    return target


def _so_from_bundle(name: str, bundle: Path) -> Path | None:
    """Extract the matching-ABI ``.so`` member from ``bundle`` into the cache.

    Copies the member's bytes via ``extractfile`` rather than ``tar.extract``
    so we don't trip the Python 3.14 tar-extraction-filter ``DeprecationWarning``
    (the test suite runs with ``filterwarnings = error``), and so this works
    unchanged on 3.10–3.14 (the ``filter=`` arg only exists from 3.12).
    """
    # Match the compiled member by its generic platform suffix (``.so`` /
    # ``.pyd``): an abi3 bundle carries ``<name>.abi3.so`` while a legacy
    # per-version bundle carries ``<name>.cpython-<py>-<plat>.so`` — both end in
    # ``.so`` (``.pyd`` on Windows), so this finds either without pinning the
    # interpreter-specific ``EXT_SUFFIX`` (which never matches an abi3 build).
    suffix = ".pyd" if sys.platform == "win32" else ".so"
    dest = _EXTRACT_DIR / name
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle) as tar:
        member = next((m for m in tar.getmembers() if m.name.endswith(suffix)), None)
        if member is None:
            return None
        target = dest / Path(member.name).name  # flatten any leading path
        # Re-extract only if missing or older than the bundle.
        if not target.exists() or target.stat().st_mtime < bundle.stat().st_mtime:
            src = tar.extractfile(member)
            if src is None:
                return None
            with src:
                target.write_bytes(src.read())
    return target


def _raw_so_candidates(name: str) -> list[Path]:
    """Fallback raw ``.so`` locations: dev build dir, then prod deploy dir."""
    plat, arch, py = _plat_arch_py()
    ext = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
    out: list[Path] = []
    # setuptools build intermediate, e.g. build/lib.macosx-15.0-arm64-cpython-313/.
    build_root = _PROPLUS_ROOT / "module-source" / name / "build"
    if build_root.is_dir():
        for libdir in sorted(build_root.glob("lib.*"), reverse=True):
            out.extend(sorted(libdir.glob(f"{name}*{ext}")))
    # Production-deployed raw ``.so``.
    out.append(_PROD_MODULES / f"{name}_{py}.so")
    return out


def resolve_so(name: str) -> Path | None:
    """Return a loadable ``.so`` Path for this interpreter, or None.

    Order: canonical abi3 binary → abi3 ``.tar.gz`` bundle (extracted) → legacy
    per-version ``.tar.gz`` bundle (extracted) → dev build dir → prod
    ``/var/lib/sysmanage/modules``.
    """
    abi3 = _abi3_binary_for(name)
    if abi3 is not None:
        return _cache_copy(name, abi3)
    abi3_bundle = _abi3_bundle_for(name)
    if abi3_bundle is not None:
        so = _so_from_bundle(name, abi3_bundle)
        if so is not None:
            return so
    bundle = _bundle_for(name)
    if bundle is not None:
        so = _so_from_bundle(name, bundle)
        if so is not None:
            return so
    for cand in _raw_so_candidates(name):
        if cand.exists():
            return cand
    return None


def load_engine(name: str):
    """Load and return the compiled engine module, or None if unavailable.

    The module is registered in ``sys.modules`` under ``name`` (before exec) so
    the engine's own intra-package imports and any ``import <name>`` elsewhere
    resolve to this same object.
    """
    if name in _loaded:
        return _loaded[name]
    so = resolve_so(name)
    if so is None:
        return None
    spec = importlib.util.spec_from_file_location(name, so)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    _loaded[name] = mod
    return mod


def require_engine(name: str):
    """Return the engine module, or apply the correct pytest outcome.

    * No sibling Pro+ checkout      -> ``skip`` (legitimate OSS-only run).
    * Pro+ present but no loadable
      engine for this platform/py   -> ``fail`` — a build/discovery problem we
      want visible, not silently skipped.
    """
    import pytest  # local import: keeps this module importable outside pytest

    mod = load_engine(name)
    if mod is None:
        # No loadable engine: skip on a genuine OSS-only run, else fail loudly.
        if not proplus_present():
            pytest.skip(
                f"{name}: no sysmanage-professional-plus checkout — OSS-only run"
            )
        plat, arch, py = _plat_arch_py()
        ext = ".pyd" if sys.platform == "win32" else ".so"
        pytest.fail(
            f"{name}: Pro+ checkout present but no loadable engine for "
            f"{plat}/{arch}/py{py}.\n"
            f"Expected an abi3 build at "
            f"{_STORAGE_MODULES}/{name}/<version>/{plat}/{arch}/abi3/{name}{ext} "
            f"(or the legacy per-version {py}/{name}.tar.gz bundle).\n"
            f"Build the Pro+ engines for this platform (make build-modules), or "
            f"check the layout — this path used to skip silently."
        )
    return mod
