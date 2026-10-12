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


def _strict():
    spec = importlib.util.spec_from_file_location(
        "i18n_strict_glossary", SCRIPTS / "i18n_strict.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_canonical_inside_the_forbidden_word_does_not_excuse_it():
    """nl "Hosten" contains "host"; fr "Simulation sèche" contains
    "simulation".  Both shipped past the gate until 2026-10-11."""
    strict = _strict()
    assert strict.glossary_hits("Hosts", "Hosten", "nl")
    assert strict.glossary_hits("Dry run: x", "Simulation sèche : x", "fr")


def test_a_canonical_elsewhere_in_the_value_still_excuses_it():
    """A sentence may use the agreed word AND an unrelated look-alike."""
    strict = _strict()
    assert not strict.glossary_hits("Hosts", "Hosts", "nl")
    assert not strict.glossary_hits("Dry run", "Simulation", "fr")


def test_a_forbidden_form_inside_the_agreed_word_is_no_match():
    """ja canonical エラータ (errata) contains the forbidden エラー (error)."""
    strict = _strict()
    assert not strict.glossary_hits("OpenBSD errata", "OpenBSD エラータ", "ja")
    assert strict.glossary_hits("OpenBSD errata", "OpenBSD エラー", "ja")


def test_korean_forbidden_forms_match_whole_words_with_particles():
    """수입 (trade imports) must not match 필수입니다 ("is required")."""
    matcher = glossary.forbidden_matcher("수입")
    assert matcher.search("CSV 수입")
    assert matcher.search("수입은 실패했습니다")
    assert not matcher.search("이 단계는 필수입니다")


# -- wrong language inside the CJK block (2026-10-12) -------------------------


def test_chinese_in_a_korean_value_is_the_wrong_language():
    import i18n_strict  # noqa: PLC0415

    assert i18n_strict.wrong_script("ko", "覆盖", "Override")
    assert i18n_strict.wrong_script(
        "ko", "등록 실패, %s 초后再尝试...", "Retrying in %s"
    )
    assert not i18n_strict.wrong_script("ko", "재정의", "Override")
    # A script the English itself contains stays legitimate.
    assert not i18n_strict.wrong_script("ko", "zh - 中文", "zh - 中文")


def test_simplified_chinese_in_a_japanese_value_is_the_wrong_language():
    import i18n_strict  # noqa: PLC0415

    assert i18n_strict.wrong_script("ja", "首席技术官", "Chief Technology Officer")
    assert i18n_strict.wrong_script(
        "ja", "CA证书バンドルの更新", "Updating CA certificate bundle"
    )
    for good in ("会社名", "最終使用日時", "時刻同期", "実行履歴", "設定"):
        assert not i18n_strict.wrong_script("ja", good, "x"), good
