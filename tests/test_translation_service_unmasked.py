# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The unmasked retry added 2026-11-06.

aya-expanse:8b drops the ⟦n⟧ markers around an inline phrase it reorders, so
docs strings carrying <strong> sat at "fallback:placeholders" run after run.
Shown the real tags, the model keeps them; the ladder now tries that before
giving up.
"""

import asyncio
import sys
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1] / "scripts" / "translation-service"
sys.path.insert(0, str(SERVICE))
sys.path.insert(0, str(SERVICE.parent))

import translate_service as ts  # noqa: E402  pylint: disable=wrong-import-position

SRC = "A <strong>Red Hat Satellite alternative</strong> for mixed fleets."
GOOD = "Une <strong>alternative à Red Hat Satellite</strong> pour les flottes mixtes."
NO_TAGS = "Une alternative à Red Hat Satellite pour les flottes mixtes."


def _fake_model(monkeypatch, unmasked_answers):
    """Masked calls always lose the markup; unmasked ones answer in turn."""
    calls = []
    answers = list(unmasked_answers)

    async def raw_chunk(_client, _lang, sources, correction=None, mask=True):
        calls.append({"mask": mask, "correction": correction})
        if mask:
            return [NO_TAGS for _ in sources]
        return [answers.pop(0) for _ in sources]

    monkeypatch.setattr(ts, "_raw_chunk", raw_chunk)
    return calls


def _translate(sources):
    return asyncio.run(
        ts._ollama_translate_chunk(  # pylint: disable=protected-access
            None, "fr", sources
        )
    )


def test_dropped_markers_are_retried_with_the_tags_shown(monkeypatch):
    calls = _fake_model(monkeypatch, [GOOD])
    assert _translate([SRC]) == [(GOOD, "ok")]
    assert [c["mask"] for c in calls][-1] is False


def test_the_unmasked_retry_gets_one_correction(monkeypatch):
    calls = _fake_model(monkeypatch, [NO_TAGS, GOOD])
    assert _translate([SRC]) == [(GOOD, "ok")]
    unmasked = [c for c in calls if not c["mask"]]
    assert unmasked[0]["correction"] is None
    assert "<strong>" in unmasked[1]["correction"]


def test_still_dropped_keeps_the_english(monkeypatch):
    _fake_model(monkeypatch, [NO_TAGS, NO_TAGS])
    assert _translate([SRC]) == [(SRC, "fallback:placeholders")]


def test_plain_text_never_takes_the_unmasked_path(monkeypatch):
    calls = _fake_model(monkeypatch, [])
    _translate(["Mixed fleets."])
    assert all(c["mask"] for c in calls)


def test_added_backticks_are_refused(monkeypatch):
    src = "Columns such as <code>host_id</code> are indexed."
    quoted = "Les colonnes comme `<code>host_id</code>` sont indexées."
    clean = "Les colonnes comme <code>host_id</code> sont indexées."
    answers = [quoted, quoted, clean]

    async def raw_chunk(_client, _lang, sources, correction=None, mask=True):
        del correction, mask
        return [answers.pop(0) for _ in sources]

    monkeypatch.setattr(ts, "_raw_chunk", raw_chunk)
    assert _translate([src]) == [(clean, "ok")]
