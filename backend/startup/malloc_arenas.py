# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Cap glibc's malloc arenas in each server process.

WHY
---
glibc gives each thread that allocates at once an arena of its own, up to
eight per core, and memory freed inside an arena mostly stays with the
process.  The server reads some feeds many files at a time on a thread pool
(Red Hat's CSAF advisories: ~15,800 files, 32 threads), and each thread's
arena kept its high-water mark: one read took the process to 1.2 GB, and a
6 GB collector with ClamAV on it was OOM-killed (2026-11-24).  With two
arenas the same read peaks at ~310 MB and runs as fast.

An operator's own MALLOC_ARENA_MAX (glibc reads it at start) is left alone.
Anything but glibc (the BSDs, macOS, musl) has no mallopt arena setting and
is left alone too.
"""

import ctypes
import os
import platform

M_ARENA_MAX = -8  # glibc malloc.h
ARENAS = 2


def cap_arenas(arenas: int = ARENAS) -> bool:
    """Limit this process to ``arenas`` malloc arenas; True when set."""
    if os.environ.get("MALLOC_ARENA_MAX"):
        return False
    if platform.system() != "Linux" or platform.libc_ver()[0] != "glibc":
        return False
    try:
        libc = ctypes.CDLL(None)
        return bool(libc.mallopt(M_ARENA_MAX, arenas))
    except (OSError, AttributeError):
        return False
