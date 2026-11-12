# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy bandwidth by the hour (ROADMAP 25.5 limits, 25.7 editions).

A target on restate-proxy may hold each client to a rate by the hour of the
storage host's own day, as restate-proxy's ``bandwidth`` grant lines say it:
``08-18 2MiB/s`` for those hours (``22-06`` runs across midnight), and one
``20MiB/s`` alone for every hour no range names; ``unlimited`` lifts it.  The
rules are kept on the target (``proxy_bandwidth``, JSON list of those lines)
and every one of the target's grants carries them.

* **Professional+.**  Setting rules needs the Pro+ backup engine (402
  without it).  Without the engine the rules are kept but not sent, so a
  lapsed license only lifts the cap: proxy backups themselves are Community
  and carry on unchanged.
* **Only to a proxy that reads them.**  restate-proxy refuses a grant with a
  key it does not know, and an older storage agent refuses one too.  The
  storage host's agent reports ``proxy_bandwidth`` among its storage
  abilities once its restate lists ``bandwidth`` in ``grant_keys``; the
  rules go only to such a storage host, and the Backups page says when the
  storage host is too old to apply them.
"""

import json
import re
from typing import Any, Dict, List, Optional

from backend.persistence import models

ABILITY = "proxy_bandwidth"
MAX_RULES = 25
MIN_RATE = 64 << 10  # restate-proxy's least rate, 64 KiB/s
_SCALE = {"KiB": 1 << 10, "MiB": 1 << 20, "GiB": 1 << 30}
_RULE = re.compile(r"^(?:(\d{2})-(\d{2}) )?(unlimited|([1-9]\d{0,6})(KiB|MiB|GiB)/s)$")
HOURS = 24


class BandwidthRefused(ValueError):
    """Bandwidth rules that restate-proxy would refuse; the message says why."""


def _hours(start: int, end: int) -> int:
    """The hours from ``start`` up to ``end`` (across midnight when
    ``end`` <= ``start``), as a bit mask -- restate's own reading."""
    mask, hour = 0, start
    while hour != end % HOURS or mask == 0:
        mask |= 1 << hour
        hour = (hour + 1) % HOURS
    return mask


def check_rules(value: Any) -> List[str]:
    """The rules, checked as restate-proxy checks a grant's ``bandwidth``
    lines: each ``RATE`` or ``HH-HH RATE``, a rate of at least 64KiB/s (or
    ``unlimited``), no hour in two ranges, at most one rate for the rest."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_RULES:
        raise BandwidthRefused("Give at most 25 bandwidth rules")
    out: List[str] = []
    taken, default = 0, False
    for rule in value:
        rule = rule.strip() if isinstance(rule, str) else rule
        match = _RULE.match(rule) if isinstance(rule, str) else None
        if not match:
            raise BandwidthRefused(
                "A bandwidth rule is a rate (512KiB/s, 2MiB/s, 1GiB/s or "
                "unlimited), or hours and a rate (08-18 2MiB/s)"
            )
        start, end, _rate, number, unit = match.groups()
        if number and int(number) * _SCALE[unit] < MIN_RATE:
            raise BandwidthRefused("A bandwidth rate must be at least 64KiB/s")
        if start is None:
            if default:
                raise BandwidthRefused("Give one rate for every other hour, not two")
            default = True
        else:
            first, last = int(start), int(end)
            if first > 23 or last > 24 or first == last:
                raise BandwidthRefused(
                    "Bandwidth hours run from 00 to 24, from one hour to another"
                )
            hours = _hours(first, last)
            if hours & taken:
                raise BandwidthRefused("An hour is in two bandwidth rules")
            taken |= hours
        out.append(rule)
    return out


def rules_of(target: Optional[models.BackupTarget]) -> List[str]:
    """The target's saved rules; none when they cannot be read."""
    text = getattr(target, "proxy_bandwidth", None)
    if not text:
        return []
    try:
        return check_rules(json.loads(text))
    except (ValueError, TypeError):
        return []


def licensed() -> bool:
    """Whether the Professional+ backup engine is loaded."""
    # pylint: disable=import-outside-toplevel
    from backend.licensing.module_loader import module_loader  # noqa: PLC0415

    return module_loader.get_module("backup_engine") is not None


def _abilities(policy: models.BackupPolicy) -> List[str]:
    try:
        value = json.loads(policy.storage_abilities or "[]")
    except ValueError:
        return []
    return [a for a in value if isinstance(a, str)] if isinstance(value, list) else []


def grant_rules(policy: models.BackupPolicy, target: models.BackupTarget) -> List[str]:
    """The lines this policy's grants carry: the target's rules when the
    license allows them and this storage host can apply them, else none."""
    rules = rules_of(target)
    if not rules or not licensed() or ABILITY not in _abilities(policy):
        return []
    return rules


def with_rules(grants: List[Dict[str, Any]], rules: List[str]) -> List[Dict[str, Any]]:
    """Each grant with the rules, when there are any (otherwise unchanged, so
    an older storage agent never sees the key)."""
    if not rules:
        return grants
    return [{**grant, "bandwidth": list(rules)} for grant in grants]


def view(
    target: models.BackupTarget, storage_abilities: Optional[List[str]]
) -> Dict[str, Any]:
    """The rules for the Backups page, with whether they apply now and, when
    not, why: ``unlicensed`` or ``storage_too_old``."""
    rules = rules_of(target)
    out: Dict[str, Any] = {"rules": rules, "licensed": licensed(), "applied": False}
    if not rules:
        return out
    if not out["licensed"]:
        out["reason"] = "unlicensed"
    elif storage_abilities is not None and ABILITY not in storage_abilities:
        out["reason"] = "storage_too_old"
    else:
        out["applied"] = storage_abilities is not None
    return out
