# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The staleness sidecar, maintained by the translator instead of by hand.

WHY THIS EXISTS
---------------
``i18n_strict.py`` detects a stale JSON translation by keeping
``sha256(english)[:16]`` per key beside the locales and flagging a translation
whose recorded source hash no longer matches.  Nothing wrote that sidecar
except a manual, global ``--baseline``, and that produced two failures that
cost real time:

1. **The unbreakable loop.**  Editing an English string makes the key stale.
   The gate says "requeue, then make translate" -- but neither of those touches
   the sidecar, so the key reports stale *forever* no matter how many times the
   cycle runs.  Hit 2026-08-12 on docs ``roadmap.edition.community``: 13
   perfectly good fresh translations, reported stale, unfixable by the two
   commands the failure message recommended.

2. **Unprotected new keys.**  The stale test is
   ``key in hashes and hashes[key] != digest(src)`` -- a key with no recorded
   hash is silently exempt.  Since only ``--baseline`` ever wrote hashes, every
   newly added string shipped unprotected.  Measured the same day: 41 unchecked
   keys in docs, 49 in the sysmanage frontend.

Both vanish if the sidecar is a *byproduct of translating* rather than a
separate step someone has to know about.

THE RULE, AND WHY IT IS SAFE
----------------------------
A blanket ``--baseline`` is dangerous: it records today's English for every
key, including keys whose translations are of *older* English, permanently
blessing exactly the drift the gate exists to catch.  So this records a key
only when BOTH hold:

  * the translator **wrote a translation for that key in this run** -- so the
    translation was produced from the English being recorded, seconds earlier;
    and
  * the key has **no remaining gap in any locale** -- no missing value, no
    lingering ``[TODO]``.

A key nobody touched is never re-recorded, so a genuinely stale key stays
stale and keeps failing the gate.  A partially-translated key (some locales
still ``[TODO]``) is not recorded either, so it stays visible.  The result can
only ever be a hash that some locale set was demonstrably just translated
from -- which is the precise claim the sidecar is supposed to make.

Dry runs write nothing: with no service configured the translator never
writes, so ``translated_keys`` is empty and this is a no-op.
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Set

# The sidecar lives in the locales root for every surface that has one
# (docs ``assets/locales``, frontend ``public/locales``), so callers never
# need to plumb a path through.
SIDECAR_NAME = ".i18n-source-hashes.json"


def digest(text: str) -> str:
    """MUST match ``i18n_strict.digest`` -- a divergence silently marks
    everything stale, which looks exactly like real drift."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def sidecar_path(base: Path) -> Path:
    return Path(base) / SIDECAR_NAME


def load(path: Path) -> Dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A corrupt sidecar must not take the translation run down with it.
        # Returning {} degrades to "nothing recorded", which the gate reports
        # as unchecked rather than as a false stale.
        return {}


def _is_gap(value: Optional[str]) -> bool:
    """Missing, blank, or still queued -- i.e. not a translation yet."""
    if value is None or not isinstance(value, str):
        return True
    stripped = value.strip()
    return not stripped or stripped.startswith("[TODO]")


def record_translated(
    base: Path,
    en_flat: Mapping[str, str],
    locale_flats: Mapping[str, Mapping[str, str]],
    translated_keys: Iterable[str],
) -> int:
    """Record source hashes for keys this run fully translated.

    Args:
        base: locales root; the sidecar sits directly inside it.
        en_flat: ``{dotted key: English source}``.
        locale_flats: ``{lang: {dotted key: value}}`` AFTER writing.  Only
            locales actually processed need appear -- a locale whose file is
            missing is the completeness gate's problem, not this one's.
        translated_keys: keys the translator wrote a value for in this run.

    Returns:
        How many keys were newly recorded or updated.
    """
    keys: Set[str] = {k for k in translated_keys if k in en_flat}
    if not keys:
        return 0

    path = sidecar_path(base)
    hashes = load(path)
    changed = 0
    for key in sorted(keys):
        # Every processed locale must now hold a real value for this key.
        if any(_is_gap(flat.get(key)) for flat in locale_flats.values()):
            continue
        new = digest(en_flat[key])
        if hashes.get(key) != new:
            hashes[key] = new
            changed += 1

    if changed:
        path.write_text(
            json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return changed
