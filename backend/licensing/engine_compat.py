# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Keep a working Pro+ engine when its update needs a newer SysManage server.

The license server always offers the LATEST build of an engine.  A build made
for a server release that has not shipped yet declares a
``min_oss_alembic_revision`` whose migration file this server does not have.
Observed 2026-11-04: backup_engine 1.0.10 (needs ``q77ossbackupkeys``) was
swapped in over a working 1.0.9 on a server that ships only up to
``q75backuptagpolicy``; the load-time migration gate then refused it and the
UI told the operator to run ``alembic upgrade head`` -- which cannot reach a
migration the server does not have.  The engine was gone until a newer server
package shipped.

So, before a verified bundle replaces an installed engine, the staged engine is
asked (in a child process: it is the same signature-verified code the server is
about to load, but loading a second copy of an extension module in this process
is not possible) which revision it needs.  If that revision is not one of this
server's migrations, the swap is refused, the installed engine stays in use,
and the deferral is recorded:

  * for the UI/API ("an update to <engine> is waiting for a newer SysManage
    server", ``get_pending_updates``), and
  * for the update check, which skips that exact build (version + hash) until
    the license server offers a different one (``drop_deferred``), so every
    cycle does not re-download a bundle it will refuse again.

A fresh install (nothing installed to keep) is not deferred: the bundle is
installed as before and the load-time gate reports it as needing a newer
server (``migration_compat.KIND_SERVER_TOO_OLD``).  The license server's
versions endpoint offers only the latest build, so there is no older
compatible version to ask for.

Nothing here weakens a check: the staged bundle has already passed signature
verification when it is probed, and the kept engine is loaded through the same
``ModuleLoader._load_module_from_path`` gate as any other.
"""

import json
import os
import subprocess  # nosec B404  # runs this interpreter with a fixed argv
import sys
from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, List, Optional

from backend.licensing.migration_compat import is_known_revision
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.licensing.engine_compat")

# Importing an engine is fast; this only bounds a wedged child.
PROBE_TIMEOUT = 60

# Run by the child interpreter: import the staged engine under its own name and
# print the revision it declares.  ``-I`` keeps the child's sys.path free of the
# working directory and the environment; the repo root is added explicitly for
# an engine that imports server code.
_PROBE_SCRIPT = (
    "import importlib.util, json, sys\n"
    "so_path, code, root = sys.argv[1:4]\n"
    "sys.path.insert(0, root)\n"
    "spec = importlib.util.spec_from_file_location(code, so_path)\n"
    "module = importlib.util.module_from_spec(spec)\n"
    "sys.modules[code] = module\n"
    "spec.loader.exec_module(module)\n"
    "get_info = getattr(module, 'get_module_info', None)\n"
    "info = get_info() if callable(get_info) else {}\n"
    "if not isinstance(info, dict):\n"
    "    info = {}\n"
    "print(json.dumps({'min': info.get('min_oss_alembic_revision')}))\n"
)


class EngineTooNewError(Exception):
    """A verified bundle needs a newer server; the installed engine is kept."""

    def __init__(self, module_code: str, required_revision: str, live_path: str):
        super().__init__(
            f"{module_code} requires OSS alembic revision {required_revision}, "
            "which this server does not ship"
        )
        self.module_code = module_code
        self.required_revision = required_revision
        # The installed engine's compiled module, left in place.
        self.live_path = live_path


@dataclass
class PendingEngineUpdate:
    """An engine build that waits for a newer SysManage server."""

    module_code: str
    version: Optional[str]
    file_hash: Optional[str]
    required_revision: str
    kept_version: Optional[str]


class _PendingRegistry:
    """In-memory registry of deferred engine updates (per process)."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._entries: Dict[str, PendingEngineUpdate] = {}

    def record(self, entry: PendingEngineUpdate) -> None:
        with self._lock:
            self._entries[entry.module_code] = entry

    def clear(self, module_code: str) -> None:
        with self._lock:
            self._entries.pop(module_code, None)

    def get(self, module_code: str) -> Optional[PendingEngineUpdate]:
        with self._lock:
            return self._entries.get(module_code)

    def all(self) -> List[PendingEngineUpdate]:
        with self._lock:
            return list(self._entries.values())


_pending = _PendingRegistry()


def get_pending_updates() -> List[PendingEngineUpdate]:
    """Engine updates currently waiting for a newer SysManage server."""
    return _pending.all()


def clear_pending_update(module_code: str) -> None:
    """Forget a deferral (an update of that engine has since installed)."""
    _pending.clear(module_code)


def is_deferred_module(module_code: str) -> bool:
    """Whether some update of ``module_code`` is waiting for a newer server."""
    return _pending.get(module_code) is not None


def is_deferred(
    module_code: str, version: Optional[str], file_hash: Optional[str]
) -> bool:
    """Whether the license server's build is the one already deferred.

    The same version with a different hash is a rebuild (perhaps with a lower
    requirement), so it is fetched and checked again.
    """
    entry = _pending.get(module_code)
    if entry is None or entry.version != version:
        return False
    if file_hash and entry.file_hash:
        return file_hash.lower() == entry.file_hash.lower()
    return True


def drop_deferred(server_versions: Dict[str, Any]) -> Dict[str, Any]:
    """``server_versions`` without the builds already deferred.

    Run once per update check: a deferred build is not re-downloaded until the
    license server offers a different one, or this server is upgraded (a
    restart starts with an empty registry).
    """
    kept: Dict[str, Any] = {}
    for module_code, info in server_versions.items():
        version = info.get("version") if isinstance(info, dict) else None
        file_hash = info.get("file_hash") if isinstance(info, dict) else None
        if is_deferred(module_code, version, file_hash):
            logger.info(
                "Module %s %s still needs a newer SysManage server; "
                "not downloading it again",
                module_code,
                version,
            )
            continue
        kept[module_code] = info
    return kept


def _compiled_module_in(directory: str) -> Optional[str]:
    """The compiled engine (.so/.pyd) in ``directory``, or None."""
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return None
    for name in names:
        if name.endswith((".so", ".pyd")):
            return os.path.join(directory, name)
    return None


def installed_version(module_dir: str) -> Optional[str]:
    """The version recorded in an installed bundle's metadata.json, or None."""
    try:
        with open(
            os.path.join(module_dir, "metadata.json"), encoding="utf-8"
        ) as handle:
            version = json.load(handle).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return str(version) if version else None


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", ".."))


def probe_required_revision(so_path: str, module_code: str) -> Optional[str]:
    """The ``min_oss_alembic_revision`` a staged engine declares.

    None when it declares none OR the probe could not tell (it failed, timed
    out, or printed something unexpected) -- the caller then installs the
    bundle as it always has, and the load-time gate still applies.
    """
    try:
        result = subprocess.run(  # nosec B603
            [  # nosemgrep
                sys.executable,
                "-I",
                "-c",
                _PROBE_SCRIPT,
                so_path,
                module_code,
                _repo_root(),
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Could not probe staged %s: %s", module_code, exc)
        return None
    lines = (result.stdout or "").strip().splitlines()
    if result.returncode != 0 or not lines:
        logger.warning(
            "Could not probe staged %s (exit %s): %s",
            module_code,
            result.returncode,
            (result.stderr or "").strip()[-500:],
        )
        return None
    try:
        required = json.loads(lines[-1]).get("min")
    except (ValueError, AttributeError):
        logger.warning("Unexpected probe output for staged %s", module_code)
        return None
    return str(required) if required else None


def refuse_if_too_new(
    staged_so: str, module_code: str, module_dir: str, alembic_cfg_path: str
) -> None:
    """Raise ``EngineTooNewError`` rather than replace a working engine with
    one this server cannot run.

    Only when something is installed: with nothing to keep, refusing would
    just leave no engine at all.
    """
    live = _compiled_module_in(module_dir)
    if live is None:
        return
    required = probe_required_revision(staged_so, module_code)
    if required and is_known_revision(required, alembic_cfg_path) is False:
        raise EngineTooNewError(module_code, required, live)


def record_deferred(
    exc: EngineTooNewError,
    version: Optional[str],
    file_hash: Optional[str],
    cached_version: Optional[str],
) -> PendingEngineUpdate:
    """Record (and log) that ``version`` waits for a newer server."""
    kept = installed_version(os.path.dirname(exc.live_path)) or cached_version
    entry = PendingEngineUpdate(
        module_code=exc.module_code,
        version=version,
        file_hash=file_hash,
        required_revision=exc.required_revision,
        kept_version=kept,
    )
    _pending.record(entry)
    logger.warning(
        "%s %s needs a newer SysManage server (schema %s); keeping %s",
        exc.module_code,
        version or "(latest)",
        exc.required_revision,
        kept or "the installed version",
    )
    return entry
