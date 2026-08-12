# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The staleness sidecar must be a byproduct of translating, not a manual step.

``i18n_strict.py`` flags a stale JSON translation by comparing a recorded
``sha256(english)[:16]`` against the current English.  Nothing wrote that
sidecar except a global ``--baseline``, which produced two distinct failures on
2026-08-12:

  * docs ``roadmap.edition.community`` reported stale through an unbounded
    requeue -> ``make translate`` -> still-stale loop, because neither of those
    two commands (the ones the failure message recommended) touches the
    sidecar; and
  * 41 docs keys and 49 sysmanage frontend keys had no recorded hash at all,
    and the stale test is ``key in hashes and ...`` -- so an unrecorded key is
    silently exempt forever.

``i18n_hashes.record_translated`` closes both by recording as part of the
translation run.  The tests that matter are the NEGATIVE ones: a recorder that
blesses everything would make both symptoms disappear while destroying the
gate, so most of what follows pins what must NOT be recorded.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "translation-service" / "i18n_hashes.py"
STRICT_PATH = REPO_ROOT / "scripts" / "i18n_strict.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


i18n_hashes = _load("i18n_hashes", MODULE_PATH)
i18n_strict = _load("i18n_strict_for_hashes", STRICT_PATH)


ENGLISH = {"a.new": "New string", "b.partial": "Partial", "c.stale": "EDITED English"}


@pytest.fixture(name="base")
def _base(tmp_path):
    """A locales root whose sidecar already records c.stale's OLD English."""
    (tmp_path / i18n_hashes.SIDECAR_NAME).write_text(
        json.dumps({"c.stale": i18n_hashes.digest("OLD English")}), encoding="utf-8"
    )
    return tmp_path


@pytest.fixture(name="locales")
def _locales():
    return {
        "fr": {"a.new": "Nouvelle", "b.partial": "Partiel", "c.stale": "vieux texte"},
        "de": {
            "a.new": "Neue",
            "b.partial": "[TODO] Partial",  # translation did not land
            "c.stale": "alter Text",
        },
    }


def _sidecar(base):
    return json.loads((base / i18n_hashes.SIDECAR_NAME).read_text(encoding="utf-8"))


def test_digest_matches_the_gate():
    """A divergence marks every key stale, which looks exactly like real drift."""
    assert i18n_hashes.digest("hello") == i18n_strict.digest("hello")


def test_fully_translated_key_is_recorded(base, locales):
    """The fix for unprotected new keys: translating one records it."""
    i18n_hashes.record_translated(base, ENGLISH, locales, {"a.new"})
    assert _sidecar(base)["a.new"] == i18n_hashes.digest("New string")


def test_partially_translated_key_is_not_recorded(base, locales):
    """de still holds [TODO]; recording would hide that from the stale check.

    The sidecar is per KEY, not per key-per-language, so a key is only safe to
    record once EVERY locale has a real value.
    """
    i18n_hashes.record_translated(base, ENGLISH, locales, {"b.partial"})
    assert "b.partial" not in _sidecar(base)


def test_untouched_stale_key_is_never_blessed(base, locales):
    """The property a blanket --baseline destroys.

    c.stale's English was edited and nobody retranslated it.  Its locale values
    are non-empty and carry no [TODO], so a naive "record everything that looks
    finished" would declare it current and permanently hide the drift.
    """
    i18n_hashes.record_translated(base, ENGLISH, locales, {"a.new"})
    recorded = _sidecar(base)["c.stale"]
    assert recorded == i18n_hashes.digest("OLD English")
    assert recorded != i18n_hashes.digest(ENGLISH["c.stale"]), "drift was masked"


def test_dry_run_writes_nothing(base, locales):
    """No service configured means no writes, so nothing may be recorded."""
    before = (base / i18n_hashes.SIDECAR_NAME).read_text(encoding="utf-8")
    assert i18n_hashes.record_translated(base, ENGLISH, locales, set()) == 0
    assert (base / i18n_hashes.SIDECAR_NAME).read_text(encoding="utf-8") == before


def test_keys_absent_from_english_are_ignored(base, locales):
    """A stray key must never invent a sidecar entry."""
    i18n_hashes.record_translated(base, ENGLISH, locales, {"does.not.exist"})
    assert "does.not.exist" not in _sidecar(base)


def test_missing_sidecar_is_created(tmp_path, locales):
    """First run in a fresh surface must not require a pre-existing file."""
    assert i18n_hashes.record_translated(tmp_path, ENGLISH, locales, {"a.new"}) == 1
    assert (tmp_path / i18n_hashes.SIDECAR_NAME).exists()


def test_corrupt_sidecar_degrades_to_unrecorded(tmp_path, locales):
    """A corrupt sidecar must not take the translation run down.

    Degrading to {} reports keys as unchecked, which is visible; raising would
    abort a long translation run partway through.
    """
    (tmp_path / i18n_hashes.SIDECAR_NAME).write_text("{not json", encoding="utf-8")
    assert i18n_hashes.record_translated(tmp_path, ENGLISH, locales, {"a.new"}) == 1


def test_recording_is_idempotent(base, locales):
    """A second identical run reports nothing new rather than churning."""
    assert i18n_hashes.record_translated(base, ENGLISH, locales, {"a.new"}) == 1
    assert i18n_hashes.record_translated(base, ENGLISH, locales, {"a.new"}) == 0


def test_recorded_hash_satisfies_the_gate(base, locales):
    """End to end: what this writes is what i18n_strict accepts as current."""
    i18n_hashes.record_translated(base, ENGLISH, locales, {"a.new"})
    hashes = _sidecar(base)
    # i18n_strict's stale test, verbatim: `hashes[key] != digest(src)`
    assert hashes["a.new"] == i18n_strict.digest(ENGLISH["a.new"])
