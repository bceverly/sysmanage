# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The domain glossary must be internally consistent.

``i18n_strict`` finds a term in a source string through the GLOSSARY
definitions; a TERMS entry (canonical / forbidden renderings) for a term with
no definition is therefore never checked at all.  That is how "live query"
and "fact table" carried forbidden forms that no gate ever applied, until
2026-10-10.
"""

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location(
    "i18n_glossary", SCRIPTS / "i18n_glossary.py"
)
glossary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(glossary)

LOCALES = {
    "ar",
    "de",
    "es",
    "fr",
    "hi",
    "it",
    "ja",
    "ko",
    "nl",
    "pt",
    "ru",
    "zh_CN",
    "zh_TW",
}


def test_every_terms_entry_has_a_definition():
    assert sorted(set(glossary.TERMS) - set(glossary.GLOSSARY)) == []


def test_every_alias_belongs_to_a_defined_term():
    assert sorted(set(glossary.ALIASES) - set(glossary.GLOSSARY)) == []


def test_terms_use_only_shipped_locales():
    for term, spec in glossary.TERMS.items():
        for field in ("canonical", "forbid"):
            assert set(spec.get(field, {})) <= LOCALES, (term, field)


def test_a_canonical_rendering_is_never_itself_forbidden():
    # A forbidden form may be a PART of the canonical one (ja erratum: the
    # canonical エラータ contains the forbidden エラー, "error"); the gate checks
    # for the canonical word first, so that is safe.  The same string in both
    # lists is not.
    for term, spec in glossary.TERMS.items():
        for lang, bad in spec.get("forbid", {}).items():
            good = spec.get("canonical", {}).get(lang)
            assert good is None or good.lower() not in {b.lower() for b in bad}, (
                term,
                lang,
            )


def test_a_forbidden_form_never_matches_inside_a_word():
    tent = glossary.forbidden_matcher("टेंट")
    assert tent.search("एक टेंट में")  # the camping tent, standalone
    assert not tent.search("ऑफ़लाइन कंटेंट डिलीवरी")  # "content"
    guest = glossary.forbidden_matcher("ضيف")
    assert guest.search("ضيف جديد")
    assert not guest.search("مضيف جديد")  # host contains guest
    assert glossary.forbidden_matcher("Bestand").search("der Bestand ist")
