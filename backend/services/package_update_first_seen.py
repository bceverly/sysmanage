# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""When each pending update was first seen on a host (ROADMAP 26.3).

Every update report replaces a host's ``package_update`` rows, and the rows
were re-created with ``discovered_at`` = now -- so "first seen" was really
"last scanned", and a waiting period counted from it would never end.  The
report keeps each update's first sighting now: the same package, package
manager and available version keep the time they were first seen; a newer
version starts its own clock.
"""

from typing import Dict, Tuple

from backend.persistence.models import PackageUpdate

Key = Tuple[str, str, str]


def first_seen(db, host_id) -> Dict[Key, object]:
    """``{(package, manager, available version): discovered_at}`` for the
    host's current rows, read before the report replaces them."""
    rows = db.query(
        PackageUpdate.package_name,
        PackageUpdate.package_manager,
        PackageUpdate.available_version,
        PackageUpdate.discovered_at,
    ).filter(PackageUpdate.host_id == host_id)
    return {(name, manager, version): seen for name, manager, version, seen in rows}


def keep(seen: Dict[Key, object], package_update: dict, version, now):
    """The time this update was first seen: kept from the previous report
    when it is the same update, else ``now``."""
    key = (
        package_update.get("package_name"),
        package_update.get("package_manager", "unknown"),
        version,
    )
    return seen.get(key) or now
