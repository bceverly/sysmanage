# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""SysManage server package.

On Windows the ARM64 MSI uses pure-Python psycopg (there is no psycopg-binary
wheel for win_arm64), which loads libpq through ``ctypes.util.find_library``
-- and on Windows that searches PATH and nothing else.  The installer puts
the DLLs in the venv's Scripts folder (and in ``<install>\\libpq``), but no
service, script or shell puts those on PATH, so every process died with
"no pq wrapper available: libpq library not found".  Found 2026-10-07 on a
real Windows ARM64 machine, where the server had never reached its database.

Every entry point (``backend.main``, ``scripts/sysmanage_migrate.py``, the
Alembic environment) imports this package before psycopg, so exposing the
bundled folders here covers all of them.
"""

import os
import sys


def _expose_bundled_libpq() -> None:
    if sys.platform != "win32":
        return
    install_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = (os.path.dirname(sys.executable), os.path.join(install_root, "libpq"))
    found = [d for d in candidates if os.path.isfile(os.path.join(d, "libpq.dll"))]
    path = os.environ.get("PATH", "")
    missing = [d for d in found if d.lower() not in path.lower().split(os.pathsep)]
    if missing:
        os.environ["PATH"] = os.pathsep.join(missing + [path])


_expose_bundled_libpq()
