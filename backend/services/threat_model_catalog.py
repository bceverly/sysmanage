# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The curated threat-model questionnaire: engine content -> the shared catalog
(ROADMAP 21.4 S2).

The questionnaire SHIPS IN THE ENGINE (``advisor_engine.curated_questionnaires``)
for the same reason curated rule packs do: a new engine bundle carries a new
version, and an air-gapped install receives it the way it receives every
engine update. This module copies each version into the SHARED partition --
one copy for every tenant; answers live in the tenant's ``threat_model``.

Unlike rule packs, every VERSION is kept, never replaced: a saved threat model
names the version it was answered against, and re-reading those answers under
a different version would silently change what they meant.

Curated only in v1 (decided 2026-09-26): operators cannot author questions.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.persistence import models
from backend.persistence.partitions import PARTITION_SHARED, partition_session

logger = logging.getLogger(__name__)

ENGINE_SOURCE = "advisor_engine"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sync_questionnaires(engine) -> Dict[str, Any]:
    """Add every questionnaire version the engine ships that the catalog lacks.

    Never raises: the previous catalog keeps working and the next tick tries
    again. A version the engine REJECTS is not written -- the catalog must
    never hold a questionnaire the engine that evaluates it would refuse.
    """
    summary = {"written": 0, "unchanged": 0, "invalid": 0}
    if engine is None or not hasattr(engine, "curated_questionnaires"):
        return summary
    try:
        with partition_session(PARTITION_SHARED) as shared:
            have = {
                (row.slug, row.version)
                for row in shared.query(
                    models.SharedThreatQuestionnaire.slug,
                    models.SharedThreatQuestionnaire.version,
                )
            }
            for questionnaire in engine.curated_questionnaires():
                key = (questionnaire.get("id"), questionnaire.get("version"))
                if key in have:
                    summary["unchanged"] += 1
                    continue
                if engine.validate_questionnaire(questionnaire):
                    logger.error(
                        "Engine questionnaire %s v%s fails its own contract; not synced",
                        key[0],
                        key[1],
                    )
                    summary["invalid"] += 1
                    continue
                shared.add(
                    models.SharedThreatQuestionnaire(
                        id=uuid.uuid4(),
                        slug=key[0],
                        version=key[1],
                        contract_version=questionnaire.get("contract", 1),
                        definition=questionnaire,
                        source=ENGINE_SOURCE,
                        synced_at=_now(),
                    )
                )
                summary["written"] += 1
            shared.commit()
        if summary["written"]:
            logger.info(
                "Threat-model questionnaire catalog: %d version(s) added",
                summary["written"],
            )
    except Exception:  # pylint: disable=broad-except
        logger.exception("Threat-model questionnaire sync failed; the catalog stays")
    return summary


def load_questionnaire(slug: str, version: Optional[int] = None) -> Optional[Dict]:
    """A questionnaire definition from the shared catalog: the given version,
    or the newest when ``version`` is None. None when the catalog lacks it."""
    with partition_session(PARTITION_SHARED) as shared:
        query = shared.query(models.SharedThreatQuestionnaire).filter(
            models.SharedThreatQuestionnaire.slug == slug
        )
        if version is not None:
            query = query.filter(models.SharedThreatQuestionnaire.version == version)
        row = query.order_by(models.SharedThreatQuestionnaire.version.desc()).first()
        return dict(row.definition) if row is not None else None
