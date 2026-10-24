# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Translation-service guards added 2026-10-11 after the asset-tags docs page.

The service returned French page titles holding a sentence from another key
(the batch came back in the right NUMBER but the wrong ORDER), and translated
the text inside <code> (/sys/class/dmi/id, "To Be Filled By O.E.M.").
"""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

SERVICE = Path(__file__).resolve().parents[1] / "scripts" / "translation-service"
sys.path.insert(0, str(SERVICE))
sys.path.insert(0, str(SERVICE.parent))

import translate_service as ts  # noqa: E402  pylint: disable=wrong-import-position
import translate_verify as tv  # noqa: E402  pylint: disable=wrong-import-position


def test_a_whole_code_span_is_one_mask():
    masked, originals = ts._mask_markup(  # pylint: disable=protected-access
        "Read <code>/sys/class/dmi/id</code> as <strong>root</strong>."
    )
    assert originals[0] == "<code>/sys/class/dmi/id</code>"
    assert "dmi" not in masked
    assert ts._unmask_markup(
        masked, originals
    ).startswith(  # pylint: disable=protected-access
        "Read <code>/sys/class/dmi/id</code>"
    )


def test_translated_code_content_fails_the_placeholder_guard():
    src = "Placeholder <code>To Be Filled By O.E.M.</code> identifies nothing."
    good = "Le substitut <code>To Be Filled By O.E.M.</code> n'identifie rien."
    bad = "Le substitut <code>A remplir par l'OEM</code> n'identifie rien."
    assert ts._placeholders_ok(src, good)  # pylint: disable=protected-access
    assert not ts._placeholders_ok(src, bad)  # pylint: disable=protected-access


class _Embedder:
    """A stand-in Ollama /api/embed: each text maps to a fixed vector."""

    def __init__(self, vectors=None, fail=False):
        self.vectors = vectors or {}
        self.fail = fail

    async def post(self, _url, json, timeout):  # pylint: disable=redefined-outer-name
        del timeout
        if self.fail:
            raise httpx.ConnectError("down")
        request = httpx.Request("POST", "http://ollama/api/embed")
        body = {"embeddings": [self.vectors[t] for t in json["input"]]}
        return httpx.Response(200, json=body, request=request)


VECTORS = {
    "Asset Tags": [1.0, 0.0, 0.0],
    "Export CSV writes every machine.": [0.0, 1.0, 0.0],
    "Etiquettes d'actif": [0.98, 0.05, 0.0],
    "Export CSV ecrit chaque machine.": [0.03, 0.99, 0.0],
}


def _aligned(client, sources, answers):
    return asyncio.run(tv.aligned(client, "http://ollama", "1m", 5.0, sources, answers))


def test_answers_in_order_are_accepted():
    sources = ["Asset Tags", "Export CSV writes every machine."]
    answers = ["Etiquettes d'actif", "Export CSV ecrit chaque machine."]
    assert _aligned(_Embedder(VECTORS), sources, answers)


def test_answers_in_the_wrong_order_are_rejected():
    """The measured failure: a title holding the neighbor's sentence."""
    sources = ["Asset Tags", "Export CSV writes every machine."]
    answers = ["Export CSV ecrit chaque machine.", "Etiquettes d'actif"]
    assert not _aligned(_Embedder(VECTORS), sources, answers)


@pytest.mark.parametrize(
    "client,sources", [(_Embedder(fail=True), ["a", "b"]), (_Embedder(), ["only"])]
)
def test_the_guard_never_blocks_translation(client, sources):
    """No embedder, or a single item: accept rather than stall the run."""
    assert _aligned(client, sources, list(sources))


def test_the_judge_is_told_the_products_terms():
    """23.4: the judge rejected the glossary's own zh_TW "fleet" term as "a
    collection of vehicles"; it is now told what the term means and how the
    product renders it -- as a correct rendering, not an instruction."""
    terms = tv.judge_terms("Fleet compliance report", "zh_TW", "Traditional Chinese")
    assert terms.startswith("DOMAIN TERMS.")
    assert "fleet" in terms and "主機群" in terms
    assert tv.judge_terms("Hello there", "zh_TW", "Traditional Chinese") == ""


class _Judge:
    """A stand-in Ollama: records each chat payload, always says yes, and
    fails the test if anything is embedded."""

    def __init__(self):
        self.chats = []

    async def post(self, url, json, timeout):  # pylint: disable=redefined-outer-name
        request = httpx.Request("POST", "http://ollama" + url)
        assert url == tv.CHAT_PATH, "judge_only must not embed"
        self.chats.append(json)
        body = {"message": {"content": '{"answer": "yes", "reason": "ok"}'}}
        return httpx.Response(200, json=body, request=request)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.parametrize("glossary,messages", [(True, 3), (False, 2)])
def test_judge_only_calibration_path(monkeypatch, glossary, messages):
    fake = _Judge()
    clients = []
    monkeypatch.setattr(
        tv.httpx, "AsyncClient", lambda **kw: clients.append(kw) or fake
    )
    router = tv.make_router(
        "http://ollama", "judge", {"zh_TW": "Traditional Chinese"},
        lambda text: (text, []), 5.0, "1m",
    )  # fmt: skip
    verify = next(r.endpoint for r in router.routes if r.path == "/verify/batch")
    request = tv.VerifyRequest(
        lang="zh_TW",
        items=[tv.VerifyItem(source="Fleet", value="主機群")],
        judge_only=True,
        glossary=glossary,
    )
    result = asyncio.run(verify(request))["results"][0]
    assert result["ok"] and result["judge"] and result["cos"] is None
    assert len(fake.chats[0]["messages"]) == messages
    # The Ollama URL comes from the service's configuration, not the request.
    assert clients == [{"base_url": "http://ollama"}]
