#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Write +COMPACT_MANIFEST and +MANIFEST for the FreeBSD server package.

The release builds the FreeBSD .pkg on a Linux runner with bsdtar, so it
cannot run FreeBSD's ``pkg create``; it writes the manifests itself.  Until
2026-11-05 a hand-kept +MANIFEST did that, and the package could not work
on a current FreeBSD (the same defects the agent package had):

  * no ``files`` section -- ``pkg`` registers and extracts only the files
    the manifest lists, so the package installed nothing;
  * Python 3.11 dependencies (``py311-*``) -- FreeBSD's repository builds
    these modules for Python 3.12 only, so the install stopped at
    "Missing dependency";
  * a post-install that pip-installed requirements.txt into a venv, which
    on FreeBSD means compiling pydantic-core and cryptography from source.

This script lists every staged file with its SHA-256 (``1$<hex>``, a
checksum form ``pkg`` accepts) and takes the dependencies from the FreeBSD
port's RUN_DEPENDS (packaging/freebsd-ports/sysutils/sysmanage/Makefile),
so the port and the package declare the same set.  The server then runs on
those system packages, as the port does.  The archive must be packed with
ABSOLUTE member paths (``bsdtar -P -s ',^usr,/usr,'``): ``pkg`` matches
archive entries to the manifest by full path, and a relative ``usr/...``
entry matches nothing.

Usage: build_pkg_manifest.py <staging dir> <version>
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT_MAKEFILE = (
    HERE.parent.parent / "packaging/freebsd-ports/sysutils/sysmanage/Makefile"
)

# FreeBSD's default Python flavor; the port's ${PY_FLAVOR} resolves to it.
PY_PREFIX = "py312-"

# Not in the port's RUN_DEPENDS (it uses USES=python and USES=pgsql), but a
# binary package has to name them.  PostgreSQL itself is left out on
# purpose: the database may be on another host.
EXTRA_DEPS = {"python312": "lang/python312"}

# Files that need something other than 0644 / 0755.
PERMS = {"/usr/local/etc/openbao/openbao.hcl": "0640"}

COMMON = {
    "name": "sysmanage",
    "origin": "sysutils/sysmanage",
    "comment": "Centralized system management server with web-based interface",
    "arch": "FreeBSD:*:amd64",
    "maintainer": "bryan@theeverlys.com",
    "prefix": "/usr/local",
    "www": "https://sysmanage.org",
}

DEP = re.compile(
    r"^\s*(\$\{PYTHON_PKGNAMEPREFIX\})?([A-Za-z0-9._-]+)>[^:]*:([a-z0-9-]+/[A-Za-z0-9._-]+)"
)


def port_deps() -> dict:
    """The port's RUN_DEPENDS as binary package names and origins."""
    text = PORT_MAKEFILE.read_text(encoding="utf-8")
    block = text[text.index("RUN_DEPENDS=") :].split("\n\n", 1)[0]
    deps = {}
    for line in block.replace("RUN_DEPENDS=", " ").splitlines():
        match = DEP.match(line)
        if match:
            python, name, origin = match.groups()
            deps[(PY_PREFIX if python else "") + name] = origin.split("@")[0]
    return {**EXTRA_DEPS, **deps}


def file_entries(staging: Path) -> dict:
    """Every staged file, keyed by its installed path."""
    entries = {}
    for path in sorted((staging / "usr").rglob("*")):
        if not path.is_file():
            continue
        installed = "/" + str(path.relative_to(staging))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        perm = PERMS.get(installed) or ("0755" if os.access(path, os.X_OK) else "0644")
        # pkg extracts each file with the mode the ARCHIVE carries, so make
        # the staged file match what the manifest says.
        path.chmod(int(perm, 8))
        entries[installed] = {
            "sum": f"1${digest}",
            "uname": "root",
            "gname": "wheel",
            "perm": perm,
        }
    return entries


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[-1])
        return 2
    staging, version = Path(sys.argv[1]), sys.argv[2]
    files = file_entries(staging)
    if not files:
        print(
            f"ERROR: no files under {staging}/usr -- refusing to build an empty package"
        )
        return 1
    deps = port_deps()
    if len(deps) < 10:
        print(f"ERROR: read only {len(deps)} dependencies from {PORT_MAKEFILE}")
        return 1
    flatsize = sum((staging / path.lstrip("/")).stat().st_size for path in files)
    compact = {**COMMON, "version": version, "flatsize": flatsize}
    full = {
        **compact,
        "desc": "SysManage server: one web console and API for inventory, updates, "
        "security and automation across Linux, Windows, macOS and the BSDs.",
        "categories": ["sysutils", "python", "www"],
        "licenselogic": "single",
        "licenses": ["AGPLv3"],
        "deps": {name: {"origin": origin} for name, origin in deps.items()},
        "files": files,
        "scripts": {
            "post-install": (HERE / "post-install.sh").read_text(encoding="utf-8"),
            "pre-deinstall": "#!/bin/sh\nservice sysmanage stop 2>/dev/null || true\n",
            "post-deinstall": (HERE / "post-deinstall.sh").read_text(encoding="utf-8"),
        },
    }
    (staging / "+COMPACT_MANIFEST").write_text(
        json.dumps(compact, indent=2) + "\n", encoding="utf-8"
    )
    (staging / "+MANIFEST").write_text(
        json.dumps(full, indent=2) + "\n", encoding="utf-8"
    )
    print(f"+MANIFEST: {len(files)} files, {len(deps)} dependencies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
