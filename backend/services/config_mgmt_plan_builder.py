# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Deployment plans for the Phase 20.1 config-management prerequisite.

WHAT THIS IS FOR
----------------
20.1 executes desired state PULL-style: the server ships a profile down the
existing WebSocket and the agent applies it locally.  That needs an executor
present on the host, and which executor depends on the platform:

  * POSIX  -> ``ansible-core``, invoked as ``ansible-playbook`` with
              ``connection: local``.
  * Windows -> DSC v3 (``dsc.exe``), because ansible-core declares
              ``Operating System :: POSIX`` and Windows is a managed node, never
              a control node.

This module builds the plan that installs the POSIX half.  **Windows needs no
plan at all** -- ``dsc.exe`` is vendored with the agent (decided 2026-08-26), so
a Windows host is ready the moment the agent is, and the UI shows it satisfied
rather than offering a button that does nothing.

PACKAGE NAMES ARE MEASURED, NOT GUESSED
---------------------------------------
Every name below came from running ``scripts/probe-ansible-support.sh`` on a
real box.  That matters because guessing was wrong twice: ``py311-ansible-core``
does not exist on FreeBSD (the prefix tracks the default Python, currently
py312), and plain ``ansible`` on OpenBSD/NetBSD pulls the full ~14.x bundle
rather than core.  Verified 2026-08-26:

    Linux (apt)     ansible-core   2.20.1
    FreeBSD 14.4    py312-ansible-core  2.21.1   (also pinned -core218..221)
    OpenBSD 7.9     ansible-core   2.20.4
    NetBSD 10.1     ansible-core   2.21.0
    macOS 15        ansible (brew bundles core)  2.21.3

PRIVILEGE
---------
No packaging change was needed for any of this: the agent's sudoers already
grant the bare package manager on Linux/FreeBSD/NetBSD, and OpenBSD's doas
grants ``/usr/sbin/pkg_add``.  macOS needs no packaging change either -- the
agent runs as root there and its existing brew path already drops to the
Homebrew prefix owner, so this plan just uses that path.
"""

from typing import Any, Dict, List, Optional

from backend.services import config_mgmt_engines as engines

# The floor the 20.1 executor targets.  Every platform we ship on packages
# 2.20+ today (measured, see module docstring), and 2.20 already requires
# Python >= 3.12 -- so the old-core/old-Python compatibility problem is a
# Linux-LTS concern rather than a cross-platform one.
MIN_ANSIBLE_CORE = "2.20"

# Windows ships its executor with the agent; nothing to install.
WINDOWS_EXECUTOR = "dsc"
POSIX_EXECUTOR = "ansible-core"


def _platform_kind(host_info: Dict[str, Any]) -> str:
    """Normalize the host's platform into the buckets this module branches on."""
    platform = (host_info.get("platform") or "").strip().lower()
    if platform.startswith("win"):
        return "windows"
    if platform in ("darwin", "macos", "mac os x"):
        return "darwin"
    if platform in ("freebsd", "openbsd", "netbsd"):
        return platform
    return "linux"


def _linux_distro_family(host_info: Dict[str, Any]) -> str:
    """Map a distro to its package manager family."""
    distro = (
        host_info.get("platform_release")
        or host_info.get("distribution")
        or host_info.get("os_name")
        or ""
    ).lower()
    if any(d in distro for d in ("ubuntu", "debian", "mint", "pop")):
        return "apt"
    if any(d in distro for d in ("suse", "sles")):
        return "zypper"
    if any(d in distro for d in ("alpine",)):
        return "apk"
    if any(d in distro for d in ("fedora", "rhel", "centos", "rocky", "alma")):
        return "dnf"
    # Unknown Linux: dnf/apt are the two big families and we cannot tell.
    # Returning "" makes the caller report "unsupported" rather than firing a
    # package manager that is not there -- a failed install is worse than an
    # honest "we do not know how to do this here".
    return ""


def platform_kind(host_info: Dict[str, Any]) -> str:
    """Public form of the platform bucket.

    Exposed because the per-engine evaluator needs the same normalisation and
    reaching into another module's private helper is how two copies of the
    rules start disagreeing.
    """
    return _platform_kind(host_info)


def linux_distro_family(host_info: Dict[str, Any]) -> str:
    """Public form of the package-manager family (empty when undeterminable)."""
    return _linux_distro_family(host_info)


def executor_for(host_info: Dict[str, Any]) -> str:
    """Which executor this host's config-management path uses."""
    return (
        WINDOWS_EXECUTOR if _platform_kind(host_info) == "windows" else POSIX_EXECUTOR
    )


def requires_install(host_info: Dict[str, Any]) -> bool:
    """True when this platform needs a prerequisite installed at all.

    Windows does not: ``dsc.exe`` is vendored with the agent, so offering an
    install button there would be offering a no-op.
    """
    return _platform_kind(host_info) != "windows"


def build_engine_install_plan(
    engine: str, host_info: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Build the plan that installs a NAMED engine.

    ``build_install_plan`` below answers for ansible-core, which carries
    per-platform quirks measured on real boxes (FreeBSD's py3* glob, Homebrew's
    bundle name, macOS needing the agent's own brew path). The other engines
    have no such quirks yet -- only apt names, measured 2026-08-27 -- so they
    go through the package matrix.

    ``None`` means "we do not know how to install this here" and the caller
    must report that honestly rather than firing a package manager at a name
    that may not exist. Salt on Ubuntu is the live example: it is genuinely
    absent from the distro's repositories, so there is no plan to build.
    """
    name = (engine or "").strip().lower()
    if name in ("", engines.ANSIBLE):
        return build_install_plan(host_info)

    kind = _platform_kind(host_info)
    if kind == "windows":
        # Windows installs for these engines are MSI/choco affairs nobody has
        # measured yet; refusing beats guessing.
        return None

    family = _linux_distro_family(host_info) if kind == "linux" else kind
    if not family:
        return None

    package = engines.package_for(name, family)
    if not package:
        return None

    return {
        "platform": kind,
        "executor": name,
        "packages": [{"manager": family, "name": package}],
    }


def build_install_plan(host_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build the plan that installs the config-management executor.

    Returns ``None`` when the platform needs no install (Windows) or when we
    cannot determine how to install it (unknown Linux distro).  ``None`` is a
    deliberate signal to the caller to report an honest "not available here"
    rather than to dispatch a plan that will fail on the far end.
    """
    kind = _platform_kind(host_info)

    if kind == "windows":
        return None

    if kind == "freebsd":
        # The pkg name carries the DEFAULT PYTHON prefix (py312- today), which
        # moves when FreeBSD moves.  Pinning it is how the first draft of the
        # probe broke, so match with pkg's glob instead of hardcoding a
        # version that will rot.  ``-y`` because there is no operator at the
        # far end to answer a prompt.
        #
        # This is the ONE platform that needs a raw command step rather than
        # ``packages``: the agent's ``_install_with_pkg`` runs
        # ``pkg install -y <name>`` with no ``-g``, so a glob handed to it
        # would be taken literally and match nothing.  Verified by dry run on
        # FreeBSD 14.4 (2026-08-26): ``pkg install -n -g 'py3*-ansible-core'``
        # resolves unambiguously and does NOT also match the version-pinned
        # ``py312-ansible-core218..221`` ports.
        return {
            "platform": "freebsd",
            "executor": POSIX_EXECUTOR,
            "commands": [
                {
                    "argv": ["pkg", "install", "-y", "-g", "py3*-ansible-core"],
                    "sudo": True,
                    "timeout": 900,
                    "description": "install ansible-core (glob matches the current py3XX prefix)",
                }
            ],
        }

    if kind == "openbsd":
        return {
            "platform": "openbsd",
            "executor": POSIX_EXECUTOR,
            "packages": ["ansible-core"],
        }

    if kind == "netbsd":
        return {
            "platform": "netbsd",
            "executor": POSIX_EXECUTOR,
            "packages": ["ansible-core"],
        }

    if kind == "darwin":
        # Homebrew has NO ansible-core formula -- only ``ansible``, which
        # bundles core (verified against formulae.brew.sh).
        #
        # This goes through ``packages`` rather than a raw ``brew install``
        # command step, and that is not cosmetic.  The macOS agent is a
        # LaunchDaemon with no ``UserName`` key, so it runs as ROOT, and
        # Homebrew refuses to run as root -- a raw command step would fail on
        # every Mac.  The agent's package path already solves this: its
        # ``_get_brew_command`` reads the owner of the Homebrew prefix and
        # emits ``sudo -u <owner> brew`` when privileged.  Reusing that means
        # this plan inherits a mechanism that is already in service for
        # inventory and updates instead of reinventing a worse one.
        return {
            "platform": "darwin",
            "executor": POSIX_EXECUTOR,
            "packages": [{"manager": "brew", "name": "ansible"}],
        }

    family = _linux_distro_family(host_info)
    if not family:
        return None
    # openSUSE packages it as ``ansible``; the rest use ``ansible-core``.
    package = "ansible" if family == "zypper" else "ansible-core"
    return {
        "platform": "linux",
        "executor": POSIX_EXECUTOR,
        "packages": [{"manager": family, "name": package}],
    }


def expected_package_pattern(host_info: Dict[str, Any]) -> Optional[str]:
    """The installed-package name to look for, as an fnmatch pattern.

    Returned as a PATTERN rather than a literal because FreeBSD's package name
    carries the default-Python prefix (``py312-ansible-core`` today) and that
    moves.  Literal names match themselves under fnmatch, so callers need only
    one code path.

    ``None`` means "nothing to look for": Windows vendors its executor, so
    there is no package to find.
    """
    kind = _platform_kind(host_info)
    if kind == "windows":
        return None
    if kind == "freebsd":
        return "py3*-ansible-core"
    if kind == "darwin":
        # Homebrew installs the bundle, which reports as ``ansible``.
        return "ansible"
    if kind in ("openbsd", "netbsd"):
        return "ansible-core"
    family = _linux_distro_family(host_info)
    if not family:
        return None
    return "ansible" if family == "zypper" else "ansible-core"


def install_targets() -> List[Dict[str, str]]:
    """The measured per-platform install matrix, for docs and the UI's help text."""
    return [
        {"platform": "linux/apt", "package": "ansible-core"},
        {"platform": "linux/dnf", "package": "ansible-core"},
        {"platform": "linux/zypper", "package": "ansible"},
        {"platform": "linux/apk", "package": "ansible-core"},
        {"platform": "freebsd", "package": "py3*-ansible-core"},
        {"platform": "openbsd", "package": "ansible-core"},
        {"platform": "netbsd", "package": "ansible-core"},
        {"platform": "darwin", "package": "ansible (brew)"},
        {"platform": "windows", "package": "(vendored dsc.exe — no install)"},
    ]
