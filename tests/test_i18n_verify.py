# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The translation verifier and its deterministic checks.

``scripts/i18n_quality.py`` decides, with no model, that a value cannot be a
translation; ``scripts/i18n_verify.py`` accepts a value only when its exact
(locale, English, translation) is in the ledger.  The cases below are the
real values that motivated both (sysmanage-docs, 2026-10-08) plus the correct
translations that a careless rule would reject -- the negative cases matter as
much, because a gate that cries wolf on good Dutch gets switched off.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


quality = _load("i18n_quality")


# --------------------------------------------------------------------------
# i18n_quality.problem: the defects
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lang,source,value,kind",
    [
        # Word-substitution "Franglais" from the old docs scripts.
        (
            "fr",
            'Click "Add Repository" to apply to all compatible hosts',
            "Cliquer Ajouter Dépôt to appliquer to tous compatible hôtes",
            "untranslated English",
        ),
        # English spliced into Korean word by word.
        (
            "ko",
            "The compliance engine is accessible through the REST API:",
            "The 규정 준수 엔진 is accessible 을(를) 통해 the REST API:",
            "untranslated English",
        ),
        # A whole English sentence under an Arabic key.
        (
            "ar",
            "Encryption and authentication with high strength",
            "Encryption and authentication with high strength",
            "untranslated English",
        ),
        # A Python list literal written as the value.
        (
            "pt",
            "Main Config File",
            "['Main Config File', 'Arquivo de Configuração Principal']",
            "a list literal",
        ),
        # A pipeline marker that a later run translated.
        (
            "fr",
            "Why an Install Ended That Way",
            "[RAPPORT DE PROVISIONNING BAREMETAL MANQUANT:pro_plus.x]",
            "a pipeline marker",
        ),
        (
            "ar",
            "Offline operation",
            "[ MISSING : عنوان العملية بدون اتصال بالإنترنت ]",
            "a pipeline marker",
        ),
        # A placeholder duplicated.
        (
            "hi",
            "vm stop {vm_name} before destroy",
            "{vm_name} को बंद करने से पहले {vm_name} को बंद करें",
            "placeholders",
        ),
        # A placeholder dropped.
        ("de", "Delete {{count}} hosts?", "Hosts löschen?", "placeholders"),
    ],
)
def test_defects_are_rejected(lang, source, value, kind):
    why = quality.problem(lang, source, value)
    assert why is not None and why.startswith(kind), why


def test_a_non_string_value_is_rejected():
    assert quality.problem("de", "Hosts", ["Hosts"]).startswith("not a string")
    assert quality.problem("de", "Hosts", 3).startswith("not a string")


# --------------------------------------------------------------------------
# i18n_quality.problem: correct translations that must pass
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lang,source,value",
    [
        # Dutch "is", "of" (or) and "in" are Dutch words.
        (
            "nl",
            "Verify the bridge is active",
            "Controleer of de bridge actief is in de omgeving",
        ),
        # German "in", "was" (what) and "will" (wants) are German words.
        (
            "de",
            "What the service wants in the config",
            "Was der Dienst in der Konfiguration will",
        ),
        # IT terms kept in English carry no function words.
        ("de", "Adaptive rate limiting", "Adaptives Rate Limiting"),
        ("nl", "Backup and restore", "Backup & Herstel"),
        # Code, quotes and status values are SUPPOSED to stay English.
        (
            "ja",
            'After a restart, look for "Database pool reduced to fit the server".',
            '再起動後、"Database pool reduced to fit the server" を確認してください。',
        ),
        (
            "fr",
            "Run <code>systemctl status the-service</code> to check it",
            "Exécutez <code>systemctl status the-service</code> pour le vérifier",
        ),
        (
            "ru",
            "Task status: pending, running, completed, failed",
            "Статус задачи: pending, running, completed, failed",
        ),
        # Placeholders preserved, reordered.
        (
            "ja",
            "{{vulnerable}} of {{total}} hosts",
            "{{total}} 台中 {{vulnerable}} 台のホスト",
        ),
        # "100%ige" is German, not a %i placeholder.
        ("de", "100% coverage", "100%ige Abdeckung"),
    ],
)
def test_good_translations_pass(lang, source, value):
    assert quality.problem(lang, source, value) is None


def test_one_stray_function_word_is_tolerated():
    # A single hit is too weak a signal: product names such as "Infrastructure
    # as Code" carry one.  Two is where the calibration found only real defects.
    assert (
        quality.problem("es", "Infrastructure as Code", "Infrastructure as Code (IaC)")
        is None
    )


# --------------------------------------------------------------------------
# i18n_verify: the ledger
# --------------------------------------------------------------------------


@pytest.fixture
def verify(tmp_path, monkeypatch):
    """The verifier, pointed at a throwaway docs-shaped locale tree."""
    module = _load("i18n_verify")
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "en.json").write_text(
        json.dumps({"a": {"save": "Save the configuration", "name": "SysManage"}})
    )
    (locales / "fr.json").write_text(
        json.dumps({"a": {"save": "Enregistrer la configuration", "name": "SysManage"}})
    )
    surface = {"name": "t", "kind": "json-flat", "root": locales, "file": None}
    monkeypatch.setattr(module.strict, "SURFACES", [surface])
    monkeypatch.setattr(module, "plugins", None)
    monkeypatch.setattr(module, "LEDGER", tmp_path / ".i18n-verified")
    # A product name kept in English is a reviewed decision, recorded the way
    # the real repos record it.
    (tmp_path / "allow.txt").write_text("re:^SysManage$\n")
    allow = module.strict.Allow(tmp_path / "allow.txt")
    return module, locales, allow


def test_an_unledgered_value_is_pending_not_passed(verify):
    module, _locales, allow = verify
    failed, pending = module.classify(allow, module.load_ledger())
    assert failed == []
    assert [i.key for i in pending] == ["a.save"]


def test_a_ledgered_value_passes_and_an_edit_unledgers_it(verify):
    module, locales, allow = verify
    _f, pending = module.classify(allow, {})
    module.save_ledger({module.ident(pending[0]): "model"})
    assert module.classify(allow, module.load_ledger()) == ([], [])

    # Edit the translation: the digest no longer matches, so it must be
    # verified again rather than inheriting the old verdict.
    doc = json.loads((locales / "fr.json").read_text())
    doc["a"]["save"] = "Sauvegarder la configuration"
    (locales / "fr.json").write_text(json.dumps(doc))
    _f, pending = module.classify(allow, module.load_ledger())
    assert [i.key for i in pending] == ["a.save"]


def test_a_ledger_entry_does_not_excuse_a_deterministic_failure(verify):
    module, locales, allow = verify
    doc = json.loads((locales / "fr.json").read_text())
    doc["a"]["save"] = "Save the configuration to the server"
    (locales / "fr.json").write_text(json.dumps(doc))
    _f, _p = module.classify(allow, {})
    item = next(i for i in module.translated_values(allow) if i.key == "a.save")
    failed, _pending = module.classify(allow, {module.ident(item): "model"})
    assert [i.key for i, _why in failed] == ["a.save"]


def test_a_human_acceptance_is_honored_and_needs_a_reason(verify, capsys):
    module, locales, allow = verify
    doc = json.loads((locales / "fr.json").read_text())
    doc["a"]["save"] = "Save the configuration to the server"
    (locales / "fr.json").write_text(json.dumps(doc))
    assert module.do_accept("fr", "a.save", "", allow) == 1
    assert module.do_accept("fr", "a.save", "quoted UI label", allow) == 0
    assert module.classify(allow, module.load_ledger()) == ([], [])
    assert "human quoted UI label" in (module.LEDGER).read_text()


def test_an_english_identical_value_is_a_failure_not_a_pass(verify):
    module, locales, allow = verify
    doc = json.loads((locales / "fr.json").read_text())
    doc["a"]["save"] = "Save the configuration"
    (locales / "fr.json").write_text(json.dumps(doc))
    failed, _pending = module.classify(allow, {})
    assert [(i.key, why) for i, why in failed] == [
        ("a.save", "identical to the English source")
    ]


def test_a_non_locale_json_file_is_not_read_as_a_locale(verify):
    module, locales, allow = verify
    (locales / "missing_keys_analysis.json").write_text(
        json.dumps({"a": {"save": ["not", "a", "translation"]}})
    )
    failed, pending = module.classify(allow, {})
    assert failed == [] and [i.lang for i in pending] == ["fr"]


def test_only_an_http_service_url_is_accepted(verify):
    # urllib would happily open file:///etc/passwd; the verifier must not.
    module, _locales, _allow = verify
    assert module.main(["--service", "file:///etc/passwd"]) == 2
