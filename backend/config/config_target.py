# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which files the install-time ``--apply CONFIG`` tools may rewrite.

``install_secrets`` and ``pool_sizing`` run as root from every installer and
rewrite the file they are given.  An argument naming any other file -- a
typo, a symlink planted where the config should be, a path built from bad
input -- would have them overwrite it.  So the target must be an existing
regular file (not a symlink) with one of the names the installers actually
use: ``sysmanage.yaml``, ``sysmanage.yaml.example`` (macOS writes the
example first) and ``config.yaml`` (the FreeBSD and NetBSD packages) -- in one
of the directories the installers actually write to.

The returned path is rebuilt from those two allow-lists, never from the
argument itself, so nothing the caller passed reaches ``open()``.
"""

import os
import stat

CONFIG_FILE_NAMES = frozenset(
    {"sysmanage.yaml", "sysmanage.yaml.example", "config.yaml"}
)

# Where every installer keeps the server configuration: deb/rpm/macOS/OpenBSD
# (/etc), Alpine (/etc/sysmanage), FreeBSD (/usr/local/etc/sysmanage), NetBSD
# (/usr/pkg/etc/sysmanage) and Windows (C:\ProgramData\SysManage).
CONFIG_DIRS = (
    "/etc",
    "/etc/sysmanage",
    "/usr/local/etc/sysmanage",
    "/usr/pkg/etc/sysmanage",
    "C:\\ProgramData\\SysManage",
)


def _same_dir(first: str, second: str) -> bool:
    return os.path.normcase(os.path.realpath(first)) == os.path.normcase(
        os.path.realpath(second)
    )


def resolve_config_target(path: str) -> str:
    """The absolute path to rewrite; ValueError (or OSError) when refused."""
    absolute = os.path.abspath(path)
    name = os.path.basename(absolute)
    filename = next((n for n in sorted(CONFIG_FILE_NAMES) if n == name), None)
    if filename is None:
        raise ValueError(
            f"refusing {path}: not a SysManage configuration file "
            f"(expected one of {', '.join(sorted(CONFIG_FILE_NAMES))})"
        )
    directory = next(
        (d for d in CONFIG_DIRS if _same_dir(d, os.path.dirname(absolute))), None
    )
    if directory is None:
        raise ValueError(
            f"refusing {path}: not in a SysManage configuration directory "
            f"({', '.join(CONFIG_DIRS)})"
        )
    target = os.path.join(os.path.realpath(directory), filename)
    mode = os.lstat(target).st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ValueError(f"refusing {path}: not a regular file")
    return target
