# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Shared OSS services handed to the licensed engines (Phase 21.1 S6).

WHY A BUNDLE RATHER THAN ANOTHER PARAMETER
-------------------------------------------
Every engine router factory takes a fixed dependency list --
``db_dependency, auth_dependency, feature_gate, module_gate, models,
http_exception, status_codes, logger`` -- eight positional concerns already.
Adding a ninth for ``host_facts`` would work exactly once: the next shared
service means editing every engine signature again, version-bumping each one
and republishing every bundle.

So this is ONE parameter that can grow. An engine reads what it needs off it
by name and ignores the rest.

WHAT IT IS NOT
--------------
Not a grab-bag, and not a way for an engine to reach arbitrary server
internals. Each attribute is a deliberate, documented service with a stable
shape, and the call site stays explicit -- ``services.host_facts.answerable(
host, "mounts")`` still says plainly what the engine depends on. A bundle
whose contents nobody can enumerate is worse than the eight parameters it
replaced.

VERSIONING
----------
``version`` lets an engine state what it needs rather than discover a missing
attribute at request time. Bump it when an attribute is REMOVED or changes
shape; adding a new one is backward-compatible and does not.

COMPATIBILITY -- the part that matters operationally
-----------------------------------------------------
Engines are prebuilt binaries pulled from the license server, and the mount
sites call their factories with KEYWORD arguments. Passing ``services=`` to an
engine compiled before this existed raises ``TypeError: got an unexpected
keyword argument``, which would break every engine on an install that has not
republished -- the "stale runtime engine" failure that has bitten this project
before. ``proplus_routes_mounts`` therefore passes it only to factories whose
signature accepts it, and logs the ones that do not.
"""

from dataclasses import dataclass
from types import ModuleType

from backend.services import host_facts as _host_facts

# Bump on a REMOVAL or a shape change, never on an addition.
SERVICES_VERSION = 1


@dataclass(frozen=True)
class ProPlusServices:
    """Server-side services a licensed engine may use.

    Frozen: an engine must not be able to swap a service out from under the
    server, and a shared mutable object passed to twenty-two mount sites is a
    debugging problem waiting to happen.
    """

    version: int

    # Phase 21.1 S6. What a host CAN answer, four-valued -- served /
    # not_applicable / unsupported / unknown. The reason every consumer needs
    # it is the same: reporting a finding built on a table the host cannot
    # serve is a confident wrong answer, and reporting nothing is
    # indistinguishable from "measured, found none".
    #
    # UNKNOWN means PROCEED AS BEFORE: a pre-21.1 agent has not denied
    # anything, and an engine that treats unknown as uncovered switches itself
    # off for every host that has not upgraded yet.
    host_facts: ModuleType


def build_services() -> ProPlusServices:
    """The bundle handed to every engine that accepts one."""
    return ProPlusServices(version=SERVICES_VERSION, host_facts=_host_facts)
