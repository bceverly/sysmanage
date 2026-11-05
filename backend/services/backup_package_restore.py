# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Package-level restore (Pro+ backup_engine, ROADMAP 24.6).

restate ``restore --packages`` puts the snapshot's packages back before its
files: its repositories and their keys, each apt package at the version
recorded, what was installed by hand and what as a dependency -- and apt
then REMOVES what the snapshot did not have -- plus its snaps and flatpaks.
It installs onto the running system, so it runs in place only.

Plan first: a preview (``dry_run``) is restate's ``plan`` from the index,
whose result carries the script it would run (``packages.script``); the
engine summarizes it for the dialog, which shows it before the real run is
offered.  The real run needs its own acknowledgment, and is audited.
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException

from backend.i18n import _
from backend.licensing.migration_compat import missing_engine_detail
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.services import backup_jobs as jobs


def engine():
    """The Pro+ backup engine when it can summarize a package script."""
    module = module_loader.get_module("backup_engine")
    if module is not None and hasattr(module, "package_script_summary"):
        return module
    return None


def check(body: Any, policy: models.BackupPolicy) -> None:
    """Refuse a package restore this server or host cannot run, or one the
    operator has not confirmed.  A restore without ``packages`` passes."""
    if not getattr(body, "packages", False):
        return
    if engine() is None:
        raise HTTPException(
            status_code=402,
            detail=missing_engine_detail(
                "backup_engine",
                _("Restoring packages needs the Professional+ backup engine"),
            ),
        )
    if "packages" not in jobs.abilities(policy):
        raise HTTPException(
            status_code=409,
            detail=_(
                "This host's restate cannot restore packages yet; upgrade restate"
            ),
        )
    if body.dry_run:
        return
    if not body.in_place:
        raise HTTPException(
            status_code=422,
            detail=_("Packages are restored onto the host itself: choose into place"),
        )
    if not getattr(body, "acknowledge_packages", False):
        raise HTTPException(
            status_code=409,
            detail=_(
                "Confirm that packages will be installed, and packages the "
                "snapshot did not have removed, to match the snapshot"
            ),
        )


def audit_text(body: Any) -> Optional[str]:
    """The audit line for a package restore, or None for a plain one."""
    if not getattr(body, "packages", False):
        return None
    if body.dry_run:
        return "Backup package restore previewed"
    return "Backup package restore requested"


def summary(result: Any) -> Optional[Dict[str, Any]]:
    """The engine's reading of a package restore's script, for the dialog."""
    packages = result.get("packages") if isinstance(result, dict) else None
    script = packages.get("script") if isinstance(packages, dict) else None
    module = engine()
    if not isinstance(script, str) or module is None:
        return None
    return module.package_script_summary(script)
