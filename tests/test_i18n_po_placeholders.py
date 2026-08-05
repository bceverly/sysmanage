# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Guards for the backend half of the placeholder-integrity gate.

``scripts/i18n_check_translations.py --placeholders`` used to read only the
frontend JSON locales.  The backend gettext catalogs went unchecked, and four
entries accumulated in which the machine translator had emitted a SECOND
``%s`` the msgid does not have — for example::

    msgid  "Marked message as processing: %s"
    msgstr "메시지 '%s'를 처리 중으로 변경했습니다: %s"

Every one of those raises ``TypeError: not enough arguments for format
string`` the first time that log line runs in that locale, and the gate
reported "placeholder integrity holds".  These tests pin the .po reader and
the extra-token case specifically, since a checker that only notices MISSING
placeholders would still wave all four through.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "i18n_check_translations.py"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("i18n_check_translations", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_po(tmp_path, body):
    path = tmp_path / "messages.po"
    path.write_text('msgid ""\nmsgstr ""\n\n' + body, encoding="utf-8")
    return path


def test_reader_skips_the_catalog_header(checker, tmp_path):
    """The header is an entry with an empty msgid; treating it as a real one
    would compare placeholder sets on metadata."""
    path = _write_po(tmp_path, 'msgid "Hello"\nmsgstr "Hallo"\n')
    assert checker._load_po(path) == {"Hello": "Hallo"}


def test_reader_handles_multiline_entries(checker, tmp_path):
    """gettext wraps long strings across continuation lines; a reader that
    only handles the single-line shape silently skips the longest messages —
    exactly the ones most likely to carry several placeholders."""
    path = _write_po(
        tmp_path,
        'msgid ""\n"Enqueued message: id=%(message_id)s, "\n"type=%(message_type)s"\n'
        'msgstr ""\n"Nachricht: id=%(message_id)s, "\n"typ=%(message_type)s"\n',
    )
    entries = checker._load_po(path)
    assert entries == {
        "Enqueued message: id=%(message_id)s, type=%(message_type)s": (
            "Nachricht: id=%(message_id)s, typ=%(message_type)s"
        )
    }


def test_reader_ignores_untranslated_entries(checker, tmp_path):
    """An empty msgstr is a gap, not a mismatch — ``i18n-complete`` owns it."""
    path = _write_po(tmp_path, 'msgid "Untranslated"\nmsgstr ""\n')
    assert checker._load_po(path) == {}


def test_an_extra_placeholder_is_a_mismatch(checker):
    """The bug that got through: a DUPLICATED token, not a missing one."""
    msgid = "Marked message as processing: %s"
    msgstr = "메시지 '%s'를 처리 중으로 변경했습니다: %s"
    assert checker._placeholders(msgid) != checker._placeholders(msgstr)


def test_a_dropped_placeholder_is_also_a_mismatch(checker):
    assert checker._placeholders("Host {host_id} not found") != checker._placeholders(
        "호스트를 찾을 수 없습니다"
    )


def test_shipped_catalogs_are_clean(checker):
    """The real catalogs, checked the way the gate checks them.  This is what
    would have failed before the four entries were repaired."""
    assert checker.check_po_placeholders() == 0
