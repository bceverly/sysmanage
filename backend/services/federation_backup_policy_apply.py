# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet-wide backup policies through federation (ROADMAP 27.3).

A site is its own server with its own backup targets, so the controller
never names a site's storage.  It defines a ``backup_tag_policy`` once --
the hosts with a tag, their schedule and retention, and optionally which
target by NAME -- and each site it is assigned to materializes it as one of
its own backup tag policies (Pro+ 24.6), resolving the target there: the
site's target with that name, else the one at that location, else the
site's default.  The site's tick then gives every tagged host its policy as
it does for a local tag policy.

Definition::

    {"name": "Web servers", "tag": "web", "priority": 50, "enabled": true,
     "settings": {<a host policy's fields>},
     "target": {"name": "Offsite", "location": "DC2"}}   # optional

A pushed tag policy is marked ``managed_by = "federation"``: it is changed
at the controller (a new version is pushed), never at the site, and a site's
own tag policy with the same name is never overwritten.  Pausing one is a
push with ``"enabled": false``.  Without the Professional+ backup engine at
the site the policy is refused and retried, like any policy a site cannot
apply yet.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_tag_policies as tag_policies
from backend.services.federation_policy_apply_service import (
    PolicyApplyError,
    register_applier,
)

POLICY_TYPE = "backup_tag_policy"
MANAGED = "federation"


def _text(definition: Dict[str, Any], key: str, limit: int) -> str:
    value = definition.get(key)
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise PolicyApplyError(f"backup_tag_policy needs '{key}'")
    if len(text) > limit:
        raise PolicyApplyError(f"backup_tag_policy '{key}' is too long")
    return text


def resolve_target(session: Session, spec: Any) -> Optional[models.BackupTarget]:
    """This site's target for ``spec`` (``{"name", "location"}``): by name,
    else by location (case does not matter), else None -- the default."""
    if not isinstance(spec, dict):
        return None
    every = jobs.targets(session)
    for key in ("name", "location"):
        wanted = spec.get(key)
        if not isinstance(wanted, str) or not wanted.strip():
            continue
        for target in every:
            if (getattr(target, key) or "").strip().lower() == wanted.strip().lower():
                return target
    return None


def _tag(session: Session, name: str) -> models.Tag:
    """The site's tag by that name, made if missing so hosts can be tagged."""
    tag = (
        session.query(models.Tag)
        .filter(func.lower(models.Tag.name) == name.lower())
        .first()
    )
    if tag is None:
        now = jobs.now()
        tag = models.Tag(
            name=name,
            description="Backup tag policy from the federation controller",
            created_at=now,
            updated_at=now,
        )
        session.add(tag)
        session.flush()
    return tag


def _checked(session: Session, definition: Dict[str, Any], name: str, tag, target):
    """The settings to store, checked as a site operator's would be."""
    # pylint: disable-next=import-outside-toplevel
    from backend.api import backups_tag_policies as tag_api  # noqa: PLC0415

    settings = definition.get("settings") or {}
    if not isinstance(settings, dict):
        raise PolicyApplyError("backup_tag_policy 'settings' must be an object")
    priority = definition.get("priority", 100)
    if not isinstance(priority, int) or isinstance(priority, bool):
        raise PolicyApplyError("backup_tag_policy 'priority' must be a whole number")
    try:
        body = tag_api.TagPolicyBody(
            name=name,
            tag_id=str(tag.id),
            priority=priority,
            enabled=definition.get("enabled", True) is not False,
            settings=tag_api.PolicyBody(**settings),
            target_id=str(target.id) if target is not None else None,
        )
        return body, tag_api.checked_settings(session, body)
    except HTTPException as refused:
        raise PolicyApplyError(str(refused.detail)) from refused
    except ValueError as bad:  # pydantic: a field of the wrong kind
        raise PolicyApplyError(f"backup_tag_policy settings: {bad}") from bad


def apply_backup_tag_policy(session: Session, definition: Dict[str, Any]) -> None:
    """Materialize a ``backup_tag_policy`` as this site's own tag policy."""
    if not tag_policies.engine_loaded():
        raise PolicyApplyError(
            "backup tag policies need the Professional+ backup engine at this site"
        )
    name = _text(definition, "name", 255)
    tag = _tag(session, _text(definition, "tag", 100))
    target = resolve_target(session, definition.get("target"))
    body, settings = _checked(session, definition, name, tag, target)
    row = (
        session.query(models.BackupTagPolicy)
        .filter(models.BackupTagPolicy.name == name)
        .first()
    )
    if row is not None and row.managed_by != MANAGED:
        raise PolicyApplyError(
            f"this site already has its own backup tag policy named '{name}'"
        )
    now = jobs.now()
    if row is None:
        row = models.BackupTagPolicy(
            name=name, created_at=now, created_by=MANAGED, managed_by=MANAGED
        )
        session.add(row)
    row.tag_id = tag.id
    row.priority = body.priority
    row.enabled = body.enabled
    row.settings = json.dumps(settings)
    # None follows the site's default; a named target is used while the
    # Enterprise engine is there (backup_tag_policies.tag_target).
    row.target_id = target.id if target is not None else None
    row.updated_at = now
    session.flush()


register_applier(POLICY_TYPE, apply_backup_tag_policy)
