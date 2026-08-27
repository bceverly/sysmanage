# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Obtain an execution spec for a licensed engine (Phase 20.1).

The OSS server knows WHICH engines are licensed but not HOW to drive them: the
flags, the workarounds and the result mappings for Puppet, Salt and Chef live
in the Pro+ ``config_management_engine``. This is the thin shim between the
two, following the same shape as ``api/handlers/child_host/`` -- OSS keeps a
delegating stub, the engine supplies the behaviour.

WHY THE DISTINCTION BETWEEN "NOT LICENSED" AND "NOT LOADED" MATTERS
------------------------------------------------------------------
They look identical to a user and mean opposite things to an operator. A
licence the customer does not have is a sales conversation; a licence they DO
have with a module that failed to load is a broken install -- typically the
engine missing a build for this Python version on the licence server, which
``check_engine_codes.py`` exists to catch. Returning one message for both sends
people to the wrong place, so the caller gets 403 and 503 respectively.
"""

import logging
from typing import Any, Dict, Optional

from backend.licensing.module_loader import module_loader

logger = logging.getLogger(__name__)

ENGINE_CODE = "config_management_engine"


def build_licensed_spec(
    engine: str,
    profile: str,
    check_mode: bool = False,
    timeout: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Ask the Pro+ engine for an execution spec.

    Returns ``None`` when the engine is not loaded, or when it declines to
    build a spec for this input. The caller has already established that the
    licence permits this engine -- see ``feature_gate.require_module`` -- so a
    None here means the module is absent or the input is unusable, never that
    the customer is unlicensed.
    """
    engine_module = module_loader.get_module(ENGINE_CODE)
    if engine_module is None:
        logger.warning(
            "Module '%s' is licensed but not loaded; cannot build a spec for %s",
            ENGINE_CODE,
            engine,
        )
        return None

    builder = getattr(engine_module, "build_spec", None)
    if builder is None:
        logger.error("Module '%s' exposes no build_spec()", ENGINE_CODE)
        return None

    try:
        return builder(engine, profile, check_mode=check_mode, timeout=timeout)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # An engine that raises must not take the request down with it: the
        # operator gets a clear refusal and the traceback goes to the log.
        logger.exception("Pro+ config-management engine raised: %s", exc)
        return None


def engine_available() -> bool:
    """Whether the Pro+ config-management module is licensed AND loaded.

    Both halves matter and neither implies the other: a licence without the
    module is a broken install, and a loaded module without a licence cannot
    happen because the loader only fetches what the licence grants. Callers use
    this to decide whether to OFFER an action, never to authorise one -- the
    authorisation is ``feature_gate.require_module``, which raises.
    """
    return module_loader.get_module(ENGINE_CODE) is not None
