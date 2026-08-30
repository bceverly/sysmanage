# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Server-side view of the config-management engines (Phase 20.1).

WHY THIS IS DUPLICATED FROM THE AGENT
-------------------------------------
The agent has its own registry (``sysmanage_agent.operations.config_mgmt_engines``)
because it must answer "is this engine installed here" without the server.  The
server cannot import agent code, so the ENGINE IDENTITIES live in both places
and are pinned by tests on both sides.

Only the identities are shared.  The agent knows about BINARIES; this module
knows about PACKAGES.  That split is deliberate -- it is what lets Chef move to
``cinc-client`` by editing the agent's binary list without the server, the
stored run rows or any profile document changing.

PACKAGE NAMES ARE MEASURED, NEVER GUESSED
-----------------------------------------
Guessing cost us twice on ansible-core (``py311-`` that does not exist on
FreeBSD; plain ``ansible`` on the BSDs pulling a ~14.x bundle).  So a cell is
filled in ONLY where the name was observed on a real box, and ``None`` means
"we do not know how to install this here" -- which the caller reports honestly
rather than firing a package manager at a name that may not exist.

Measured on Ubuntu 2026-08-27:
    puppet   -> ``puppet-agent``   (the package named ``puppet`` DOES NOT
                                    EXIST; ``/usr/bin/puppet`` ships in
                                    ``puppet-agent``, confirmed with dpkg -S)
    chef     -> ``chef`` 18.11.11-1
    salt     -> NOT PACKAGED in Ubuntu's repos at all, so there is no apt cell
                to fill.  It is installed instead by bootstrapping the Salt
                Project repository -- see ``_salt_apt_install_plan`` in
                config_mgmt_plan_builder, which is consulted BEFORE this matrix
                for that one combination.
"""

from typing import Dict, Optional, Tuple

# Identities.  These MUST match the agent's module of the same name; a test
# pins the list so the two cannot drift silently.
ANSIBLE = "ansible-core"
PUPPET = "puppet"
SALT = "salt"
CHEF = "chef"
DSC = "dsc"

ALL_ENGINES: Tuple[str, ...] = (ANSIBLE, PUPPET, SALT, CHEF, DSC)

# Engines that ship with the agent rather than being installed.
VENDORED = frozenset({DSC})

# The one genuinely platform-bound engine.  Puppet, Salt and Chef all ship
# Windows agents, so Windows is NOT restricted to DSC -- DSC is simply what we
# vendor there.
WINDOWS_ONLY = frozenset({DSC})

DEFAULT_ENGINE_BY_PLATFORM = {"windows": DSC}
DEFAULT_ENGINE = ANSIBLE

# (engine, package-manager family) -> package name, or None where unmeasured.
#
# A missing KEY and an explicit None mean the same thing to callers ("we cannot
# install this here"); None is used where we have positively established that
# the distro does not carry it, so the knowledge is not lost.
_PACKAGES: Dict[Tuple[str, str], Optional[str]] = {
    # ansible-core: measured across every platform 2026-08-26.
    (ANSIBLE, "apt"): "ansible-core",
    (ANSIBLE, "dnf"): "ansible-core",
    (ANSIBLE, "apk"): "ansible-core",
    (ANSIBLE, "zypper"): "ansible",
    # puppet: apt measured 2026-08-27. The binary is /usr/bin/puppet but the
    # PACKAGE is puppet-agent -- getting this backwards installs nothing.
    (PUPPET, "apt"): "puppet-agent",
    # chef: apt measured 2026-08-27.
    (CHEF, "apt"): "chef",
    # salt: positively established as ABSENT from Ubuntu's repos, so an apt
    # install cannot work from the matrix. Left explicit so nobody "fixes" it
    # by guessing a package name -- the real install bootstraps the vendor
    # repository first (``_salt_apt_install_plan``), which is why this stays
    # None rather than naming salt-common: that package does not exist until
    # the repository has been added.
    (SALT, "apt"): None,
}


def default_engine(platform_kind: Optional[str] = None) -> str:
    """The engine a host gets when a profile does not name one."""
    return DEFAULT_ENGINE_BY_PLATFORM.get((platform_kind or "").lower(), DEFAULT_ENGINE)


def is_known(engine: Optional[str]) -> bool:
    """Whether ``engine`` is one we implement."""
    return (engine or "").strip().lower() in ALL_ENGINES


def applicable(platform_kind: Optional[str]) -> Tuple[str, ...]:
    """Engines that could run on this platform at all."""
    kind = (platform_kind or "").lower()
    return tuple(
        engine
        for engine in ALL_ENGINES
        if engine not in WINDOWS_ONLY or kind == "windows"
    )


def package_for(engine: str, manager: str) -> Optional[str]:
    """The package that installs ``engine`` under ``manager``, or None.

    ``None`` covers both "never measured" and "measured, and the distro does
    not carry it". Callers must treat it as "cannot install here" either way.
    """
    return _PACKAGES.get((engine, manager))


# --- licensing ---------------------------------------------------------------
#
# DECIDED 2026-08-27 (Bryan). Which engines an OSS build may drive.
#
# The line is NOT "config management is Enterprise". ansible-core stays free
# because the OSS user's job-to-be-done is thin -- somebody with three hosts
# already has `ansible-playbook` -- and single-host apply is the direct
# analogue of execute_script, which is free. Gating that would be unenforceable
# (wrap the playbook in a shell script) as well as mean-spirited.
#
# Puppet, Salt and Chef are different. Their value is proportional to an
# existing estate of manifests and cookbooks that nobody accumulates at three
# hosts, so the adapter is a MIGRATION BRIDGE for an organisation -- the
# classic thing you sell rather than give away. They also carry a permanent
# maintenance surface across four upstreams (the Salt `result: None`, Puppet
# `--noop` and Chef missing-JSON traps found during the 2026-08-27 spike are
# the shape of that churn), which is far easier to justify against revenue.
#
# DSC is free for the same reason ansible is: it is what we vendor on Windows,
# so it is the default single-host path there.
OSS_ENGINES = frozenset({ANSIBLE, DSC})

LICENSED_ENGINES = frozenset(ALL_ENGINES) - OSS_ENGINES


def requires_license(engine: Optional[str]) -> bool:
    """Whether driving ``engine`` needs the config_management_engine module.

    Deliberately the single source of truth: the apply endpoint, the install
    endpoint and the UI all consult this, so the rule cannot drift between the
    place that offers a button and the place that refuses the request.
    """
    return (engine or "").strip().lower() in LICENSED_ENGINES
