# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Every security role has a console translation key.

Role names come from the database in English.  The console shows them through
roleLabel() (frontend/src/Services/securityRoles.tsx), which looks up
securityRoles.role.<slug> and falls back to the English name.  A new role with
no key would silently show English in all 13 other languages, and no i18n gate
would notice because the key is built at runtime.  This test is that gate.
"""

import json
import re
from pathlib import Path

from backend.security.roles import SecurityRoles

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "frontend" / "public" / "locales"


def _slug(name: str) -> str:
    """Mirror slug() in frontend/src/Services/securityRoles.tsx."""
    return re.sub(r"^_+|_+$", "", re.sub(r"[^a-z0-9]+", "_", name.lower()))


def _locale(lang: str) -> dict:
    with open(LOCALES / lang / "translation.json", encoding="utf-8") as handle:
        return json.load(handle)


def test_every_role_has_an_english_key_matching_its_name():
    roles = _locale("en")["securityRoles"]["role"]
    missing = [r.value for r in SecurityRoles if roles.get(_slug(r.value)) != r.value]
    assert not missing, (
        "These roles have no securityRoles.role.<slug> entry in "
        "frontend/public/locales/en/translation.json (or its English differs): "
        f"{missing}. Add the key, then run the translation backfill."
    )


def test_every_locale_has_every_role_and_group_key():
    english = _locale("en")["securityRoles"]
    langs = sorted(p.name for p in LOCALES.iterdir() if p.is_dir() and p.name != "en")
    gaps = []
    for lang in langs:
        local = _locale(lang).get("securityRoles", {})
        for section in ("role", "group"):
            for key in english[section]:
                if not local.get(section, {}).get(key):
                    gaps.append(f"{lang}: securityRoles.{section}.{key}")
    assert not gaps, f"Missing role/group translations: {gaps}"
