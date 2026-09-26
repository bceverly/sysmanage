# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Curated advisor rule packs: engine content -> the shared catalog (ROADMAP 21.2 S6).

The curated packs SHIP IN THE ENGINE (``advisor_engine.curated_packs()``), so
a new engine bundle carries new rules and an air-gapped install receives them
the way it receives every engine update. This module copies them into the
SHARED partition -- one copy for every tenant -- and per-tenant choice lives
in ``advisor_pack_setting``, never in a copy of the pack.

WHEN A PACK IS WRITTEN
----------------------
Only when the engine's pack ``version`` is NEWER than the catalog's (or the
pack is new): re-writing on every tick would churn the shared table under
every tenant's evaluation, and an OLDER engine (a server not yet upgraded,
sharing the catalog with one that is) must never roll content back.

A pack the engine no longer ships is DEPRECATED, not deleted: its rules stop
being evaluated and the tick's prune withdraws their results and proposals,
but the row remains for anything still pointing at it.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from backend.persistence import models
from backend.persistence.partitions import PARTITION_SHARED, partition_session
from backend.services import advisor_proposals

logger = logging.getLogger(__name__)

ENGINE_SOURCE = "advisor_engine"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _write_rules(shared, pack_row, rules) -> None:
    shared.query(models.SharedAdvisorRule).filter(
        models.SharedAdvisorRule.shared_pack_id == pack_row.id
    ).delete(synchronize_session=False)
    for rule in rules:
        shared.add(
            models.SharedAdvisorRule(
                id=uuid.uuid4(),
                shared_pack_id=pack_row.id,
                rule_key=rule["id"],
                contract_version=rule.get("contract", 1),
                rule_version=rule.get("version", 1),
                lens=rule.get("lens"),
                scope=rule.get("scope", "host"),
                title=rule.get("title"),
                definition=rule,
            )
        )


def sync_shared_catalog(engine) -> Dict[str, Any]:
    """Bring the shared catalog up to the engine's packs. Never raises."""
    summary = {"written": 0, "unchanged": 0, "deprecated": 0, "skipped_older": 0}
    if engine is None or not hasattr(engine, "curated_packs"):
        return summary
    try:
        packs = list(engine.curated_packs())
        shipped = {p["slug"] for p in packs}
        with partition_session(PARTITION_SHARED) as shared:
            existing = {
                row.slug: row
                for row in shared.query(models.SharedAdvisorRulePack).all()
            }
            for pack in packs:
                row = existing.get(pack["slug"])
                if row is not None and not row.deprecated:
                    if (row.version or 0) > pack["version"]:
                        summary["skipped_older"] += 1  # never roll content back
                        continue
                    if (row.version or 0) == pack["version"]:
                        summary["unchanged"] += 1
                        continue
                if row is None:
                    row = models.SharedAdvisorRulePack(
                        id=uuid.uuid4(), slug=pack["slug"], created_at=_now()
                    )
                    shared.add(row)
                row.name = pack["name"]
                row.description = pack.get("description")
                row.version = pack["version"]
                row.default_enabled = bool(pack.get("default_enabled"))
                row.deprecated = False
                row.source = ENGINE_SOURCE
                row.updated_at = _now()
                shared.flush()
                _write_rules(shared, row, pack.get("rules") or [])
                summary["written"] += 1
            for slug, row in existing.items():
                if (
                    row.source == ENGINE_SOURCE
                    and slug not in shipped
                    and not row.deprecated
                ):
                    row.deprecated = True
                    row.updated_at = _now()
                    summary["deprecated"] += 1
            shared.commit()
        if summary["written"] or summary["deprecated"]:
            logger.info(
                "Advisor catalog synced from the engine: %d pack(s) written, "
                "%d deprecated",
                summary["written"],
                summary["deprecated"],
            )
    except Exception:  # pylint: disable=broad-except
        # The previous catalog keeps working; the next tick tries again.
        logger.exception("Advisor catalog sync failed; the previous catalog stays")
    return summary


# ---------------------------------------------------------------------------
# per-tenant choice
# ---------------------------------------------------------------------------


def tenant_settings(db) -> Dict[str, Any]:
    """``{pack_slug: AdvisorPackSetting}`` for this tenant."""
    return {row.pack_slug: row for row in db.query(models.AdvisorPackSetting).all()}


def pack_enabled(setting, default_enabled: bool) -> bool:
    """A tenant's explicit choice, else the pack's default."""
    if setting is not None and setting.enabled is not None:
        return bool(setting.enabled)
    return bool(default_enabled)


def rule_enabled(setting, default_enabled: bool, rule_key: str) -> bool:
    """Is this curated rule active for the tenant?"""
    if not pack_enabled(setting, default_enabled):
        return False
    return rule_key not in set((setting.disabled_rules or []) if setting else [])


def list_packs(db) -> list:
    """Every curated pack with this tenant's effective state, rule by rule."""
    settings = tenant_settings(db)
    out = []
    with partition_session(PARTITION_SHARED) as shared:
        packs = (
            shared.query(models.SharedAdvisorRulePack)
            .order_by(models.SharedAdvisorRulePack.slug)
            .all()
        )
        for pack in packs:
            setting = settings.get(pack.slug)
            rules = (
                shared.query(models.SharedAdvisorRule)
                .filter(models.SharedAdvisorRule.shared_pack_id == pack.id)
                .order_by(models.SharedAdvisorRule.rule_key)
                .all()
            )
            out.append(
                {
                    "slug": pack.slug,
                    "name": pack.name,
                    "description": pack.description,
                    "version": pack.version,
                    "deprecated": bool(pack.deprecated),
                    "default_enabled": bool(pack.default_enabled),
                    # The tenant's own choice; None = follow the default.
                    "choice": setting.enabled if setting is not None else None,
                    "enabled": pack_enabled(setting, pack.default_enabled)
                    and not pack.deprecated,
                    "disabled_rules": sorted(
                        (setting.disabled_rules or []) if setting else []
                    ),
                    "rules": [
                        {
                            "key": r.rule_key,
                            "title": r.title,
                            "lens": r.lens,
                            "scope": r.scope,
                            "enabled": rule_enabled(
                                setting, pack.default_enabled, r.rule_key
                            )
                            and not pack.deprecated,
                        }
                        for r in rules
                    ],
                }
            )
    return out


def pack_rule_keys(slug: str):
    """The rule keys of a curated pack, or None when there is no such pack."""
    with partition_session(PARTITION_SHARED) as shared:
        pack = (
            shared.query(models.SharedAdvisorRulePack)
            .filter(models.SharedAdvisorRulePack.slug == slug)
            .first()
        )
        if pack is None:
            return None
        keys = [
            key
            for (key,) in shared.query(models.SharedAdvisorRule.rule_key).filter(
                models.SharedAdvisorRule.shared_pack_id == pack.id
            )
        ]
        return {"keys": keys, "default_enabled": bool(pack.default_enabled)}


def set_choice(db, slug: str, changes: Dict[str, Any], userid: str, pack) -> Any:
    """Record a tenant's choice about a pack, and clear what it switched off
    NOW -- its outcomes and open proposals -- rather than leaving them in the
    feed until the next tick prunes them."""
    setting = tenant_settings(db).get(slug)
    if setting is None:
        setting = models.AdvisorPackSetting(id=uuid.uuid4(), pack_slug=slug)
        db.add(setting)
    if "enabled" in changes:
        setting.enabled = changes["enabled"]
    if "disabled_rules" in changes:
        setting.disabled_rules = sorted(set(changes["disabled_rules"] or []))
    setting.updated_by = userid
    setting.updated_at = _now()
    for key in pack["keys"]:
        if not rule_enabled(setting, pack["default_enabled"], key):
            db.query(models.AdvisorResult).filter(
                models.AdvisorResult.rule_source == models.ADVISOR_RULE_SOURCE_SHARED,
                models.AdvisorResult.rule_key == key,
            ).delete(synchronize_session=False)
            advisor_proposals.withdraw_for(db, models.ADVISOR_RULE_SOURCE_SHARED, key)
    return setting
