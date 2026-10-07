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
example first) and ``config.yaml`` (the FreeBSD and NetBSD packages).
"""

import os
import stat

CONFIG_FILE_NAMES = frozenset(
    {"sysmanage.yaml", "sysmanage.yaml.example", "config.yaml"}
)


def resolve_config_target(path: str) -> str:
    """The absolute path to rewrite; ValueError (or OSError) when refused."""
    absolute = os.path.abspath(path)
    name = os.path.basename(absolute)
    if name not in CONFIG_FILE_NAMES:
        raise ValueError(
            f"refusing {path}: not a SysManage configuration file "
            f"(expected one of {', '.join(sorted(CONFIG_FILE_NAMES))})"
        )
    mode = os.lstat(absolute).st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ValueError(f"refusing {path}: not a regular file")
    return os.path.join(os.path.realpath(os.path.dirname(absolute)), name)
