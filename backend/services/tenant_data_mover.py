# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tenant data-mover — OSS shim (Pro+ relocation, Phase 2).

Idempotently relocates per-tenant data from the bootstrap database into each
tenant's database (the companion to per-domain data-plane routing, and the
verify step that gates the eventual "burn the ships" drop).  The mover logic
moved into the licensed engine — the OSS build has no copy — so this is a thin
delegator: with no engine loaded it's a no-op (single-database / unlicensed has
nowhere to move data to).
"""

from backend.multitenancy import seam


def move_all(*, apply: bool = False, delete_source: bool = False) -> dict:
    """Run every registered domain.  No-op (``_enabled`` False) without the engine."""
    engine = seam.engine_module()
    if engine is None:
        return {"_enabled": False}
    return engine.move_all(apply=apply, delete_source=delete_source)


def verify_source_drained() -> dict:
    """Per domain, how many rows REMAIN in the bootstrap DB (the burn-ships gate).

    Empty when the engine isn't loaded (nothing to drain).
    """
    engine = seam.engine_module()
    if engine is None:
        return {}
    return engine.verify_source_drained()


def check() -> dict:
    """Dry-run report: how many rows each domain WOULD move."""
    return move_all(apply=False, delete_source=False)
