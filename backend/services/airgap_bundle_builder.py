"""
Air-gap install bundle build runner.

Runs ``scripts/buildAirGapBundle.sh server|agent`` as a background
subprocess and reports progress through the ``airgap_bundle`` table.
Designed to be invoked from the bundle API endpoint as a fire-and-
forget thread so the API call returns immediately with a job id.

The actual build is slow — Docker container per Linux distro, pip
wheel compilation, ISO generation.  Expect 5-30 minutes depending on
how many platforms are enabled.  The caller polls the row's
``status`` (or watches the build log) for progress.
"""

import logging
import os
import subprocess  # nosec B404 - intentional: we exec the bundled build script (path + arg fully controlled below)
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import sessionmaker

from backend.persistence import db, models

logger = logging.getLogger(__name__)

# Where built ISOs live on the sysmanage server.  Owned by the
# sysmanage system user; the postinst should chown -R sysmanage:sysmanage
# this directory.
BUNDLE_DIR = Path("/var/lib/sysmanage/airgap-bundles")

# Serialize bundle builds across the whole process.  Each build spins up
# a Docker container per platform, downloads full dependency closures,
# and assembles a multi-GB ISO; running several at once (e.g. an operator
# kicking off server + agent + proplus together) multiplies peak memory
# and disk and OOM-kills the backend that launched them.  A plain
# module-level lock makes concurrent build requests queue and run one at
# a time — the extra daemon threads just block until their turn.
_BUILD_LOCK = threading.Lock()

# Where the build script lives relative to the repo root / install root.
# In a /opt/sysmanage install the script is at /opt/sysmanage/scripts/...;
# in a dev tree it's relative to the cwd.  Resolve dynamically.
_SCRIPT_NAMES = (
    "/opt/sysmanage/scripts/buildAirGapBundle.sh",
    "scripts/buildAirGapBundle.sh",
)


def _resolve_script() -> Optional[Path]:
    for candidate in _SCRIPT_NAMES:
        p = Path(candidate)
        if p.is_file() and os.access(p, os.X_OK):
            return p
    return None


def _now_naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_session():
    return sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())


def _update_bundle(bundle_id: uuid.UUID, **fields) -> None:
    """Update an airgap_bundle row in its own short-lived session.

    Spawned threads can't safely share the request-scoped session, so
    every state transition opens a new session.
    """
    SessionLocal = _make_session()
    with SessionLocal() as session:
        row = (
            session.query(models.AirGapBundle)
            .filter(models.AirGapBundle.id == bundle_id)
            .first()
        )
        if row is None:
            logger.warning("airgap_bundle %s vanished mid-build", bundle_id)
            return
        for key, value in fields.items():
            setattr(row, key, value)
        session.commit()


def _run_build(bundle_id: uuid.UUID, product: str) -> None:
    """Subprocess runner.  Runs in a background thread."""
    script = _resolve_script()
    if script is None:
        _update_bundle(
            bundle_id,
            status=models.BUNDLE_STATUS_FAILED,
            completed_at=_now_naive_utc(),
            error_message=(
                f"buildAirGapBundle.sh not found.  Looked in: "
                f"{', '.join(_SCRIPT_NAMES)}"
            ),
        )
        return

    # Only one build at a time — see _BUILD_LOCK.  Extra concurrent
    # build requests (their own daemon threads) block here until the
    # in-flight build finishes, instead of all running at once and
    # exhausting memory/disk.
    with _BUILD_LOCK:
        _execute_build(bundle_id, product, script)


def _execute_build(bundle_id: uuid.UUID, product: str, script: Path) -> None:
    """Run the build script + record the result.  Holds ``_BUILD_LOCK``."""
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = BUNDLE_DIR / f"{bundle_id}.log"
    iso_path = BUNDLE_DIR / f"sysmanage-{product}-bundle-{bundle_id}.iso"
    # The build script writes the upstream release version (e.g.
    # "2.4.0.2") to this file once it has resolved the package
    # source.  We read it back after the run to stamp the bundle row.
    version_path = BUNDLE_DIR / f"{bundle_id}.version"

    _update_bundle(
        bundle_id,
        status=models.BUNDLE_STATUS_BUILDING,
        started_at=_now_naive_utc(),
        log_path=str(log_path),
    )

    env = os.environ.copy()
    env["DEST_DIR"] = str(BUNDLE_DIR)
    env["BUNDLE_VERSION_FILE"] = str(version_path)
    # Override the script's hardcoded output filename so concurrent
    # builds don't collide.  The script's default is
    # sysmanage-<product>-bundle.iso; we rename after the run.
    try:
        with open(log_path, "wb") as log_f:
            proc = subprocess.run(  # nosec B603 - args are fully controlled
                [str(script), product],
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=env,
                check=False,
            )
    except OSError as exc:
        _update_bundle(
            bundle_id,
            status=models.BUNDLE_STATUS_FAILED,
            completed_at=_now_naive_utc(),
            error_message=f"Failed to launch build script: {exc}",
        )
        return

    if proc.returncode != 0:
        # Pull the last 200 chars of the log as the error preview.
        try:
            tail = log_path.read_bytes()[-1024:].decode("utf-8", errors="replace")
        except OSError:
            tail = ""
        _update_bundle(
            bundle_id,
            status=models.BUNDLE_STATUS_FAILED,
            completed_at=_now_naive_utc(),
            error_message=f"buildAirGapBundle.sh exited {proc.returncode}.\n{tail}",
        )
        return

    # Script writes to DEST_DIR/sysmanage-<product>-bundle.iso (its
    # default name).  Rename to a per-bundle id so multiple bundles
    # can coexist on disk.
    default_iso = BUNDLE_DIR / f"sysmanage-{product}-bundle.iso"
    if default_iso.is_file():
        default_iso.replace(iso_path)
    if not iso_path.is_file():
        _update_bundle(
            bundle_id,
            status=models.BUNDLE_STATUS_FAILED,
            completed_at=_now_naive_utc(),
            error_message=f"Build claimed success but no ISO at {iso_path}",
        )
        return

    version: Optional[str] = None
    if version_path.is_file():
        try:
            version = version_path.read_text(encoding="utf-8").strip() or None
        except OSError:
            version = None
        # Tidy up — the per-bundle version marker file is consumed.
        try:
            version_path.unlink()
        except OSError:
            pass

    _update_bundle(
        bundle_id,
        status=models.BUNDLE_STATUS_READY,
        completed_at=_now_naive_utc(),
        file_path=str(iso_path),
        size_bytes=iso_path.stat().st_size,
        version=version,
    )
    logger.info(
        "airgap_bundle %s ready at %s (version=%s)", bundle_id, iso_path, version
    )


def start_build(bundle_id: uuid.UUID, product: str) -> None:
    """Kick off a build in a background thread and return immediately."""
    thread = threading.Thread(
        target=_run_build,
        args=(bundle_id, product),
        name=f"airgap-bundle-{bundle_id}",
        daemon=True,
    )
    thread.start()
