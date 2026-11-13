# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Where an air-gapped repository keeps the tree nginx serves (2026-11-13).

The ingest used to write ``/var/lib/sysmanage/airgap-repo`` on every
platform, while each platform's nginx serves ``/airgap-repo/`` from its own
place (``scripts/render_nginx_configs.py``): FreeBSD and OpenBSD from
``/var/db/sysmanage``, Windows from ``C:/ProgramData/SysManage``, the snap
from ``$SNAP_DATA``.  There the repository served an empty tree.  This is
the one answer the server uses, and a test holds it to the nginx table.
The SysManage tools repository sits beside it (``airgap_tools.tools_root``).
"""

import os
import platform
from typing import Mapping, Optional

_DEFAULT = "/var/lib/sysmanage/airgap-repo"
_BY_SYSTEM = {
    "freebsd": "/var/db/sysmanage/airgap-repo",
    "openbsd": "/var/db/sysmanage/airgap-repo",
    "windows": "C:/ProgramData/SysManage/airgap-repo",
}


def repo_root(
    system: Optional[str] = None, environ: Optional[Mapping[str, str]] = None
) -> str:
    """The air-gap repository root on this platform (no trailing slash)."""
    environ = os.environ if environ is None else environ
    snap_data = environ.get("SNAP_DATA")
    if snap_data and environ.get("SNAP_NAME", "sysmanage") == "sysmanage":
        return snap_data.rstrip("/") + "/airgap-repo"
    system = (system or platform.system()).lower()
    return _BY_SYSTEM.get(system, _DEFAULT)
