# SysManage Translation Service

A small, self-contained GPU/LLM-backed localization service. You run it on the
GPU **"beast"** box; the per-project i18n backfill clients (in `sysmanage`,
`sysmanage-agent`, `sysmanage-professional-plus`, `sysmanage-docs`) call it over
the LAN to turn English source strings into the **13 non-English locales**
SysManage ships: `ar de es fr hi it ja ko nl pt ru zh_CN zh_TW`.

The service is a thin FastAPI wrapper around a local instruction LLM served by
**Ollama** — so there is no `torch`/`transformers`/CUDA in this directory; all
model work happens in Ollama.

## Why an instruction LLM (not classic MT)

Our strings are full of things that MUST survive translation byte-for-byte:
interpolation placeholders (`{{count}}`, `%s`, `%(name)s`, `${VAR}`), HTML/markup
(`<code>`, `&mdash;`), markdown, file paths, CLI commands, and brand names
(SysManage, OpenBAO, PostgreSQL…). A well-prompted LLM preserves these; dedicated
MT models routinely corrupt them. The system prompt in `translate_service.py`
enforces those rules.

## One-time setup on the beast box

1. **Install Ollama** (NVIDIA GPU auto-detected): https://ollama.com/download
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```
2. **Pull a translation-capable instruction model.** Pick by VRAM:
   | VRAM        | Model (set as `TRANSLATION_MODEL`)     |
   |-------------|----------------------------------------|
   | 12–16 GB    | `qwen2.5:14b-instruct`                 |
   | 24 GB       | `qwen2.5:32b-instruct`                 |
   | 48 GB+      | `qwen2.5:72b-instruct`                 |
   Qwen2.5 is strong across all 13 (incl. CJK, Arabic, Hindi). Gemma 2 / Llama 3.x
   instruct models also work.
   ```bash
   ollama pull qwen2.5:14b-instruct
   ```
3. **Install the service deps** (a venv is fine):
   ```bash
   cd scripts/translation-service
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   ```

## Run it

```bash
# Ollama is already running as a daemon after install; then:
TRANSLATION_MODEL=qwen2.5:14b-instruct python3 translate_service.py
# or, equivalently:
uvicorn translate_service:app --host 0.0.0.0 --port 8765
```

Bind `0.0.0.0` so the dev box can reach it over the LAN. Confirm it's healthy:

```bash
curl -s http://localhost:8765/health | python3 -m json.tool
```
`status: ok` means Ollama is reachable AND the model is pulled.

## Configuration (env vars)

| Var                 | Default                  | Meaning                                   |
|---------------------|--------------------------|-------------------------------------------|
| `TRANSLATION_MODEL` | `qwen2.5:14b-instruct`   | Ollama model tag                          |
| `OLLAMA_URL`        | `http://localhost:11434` | Where Ollama listens                      |
| `SERVICE_HOST`      | `0.0.0.0`                | Service bind address                      |
| `SERVICE_PORT`      | `8765`                   | Service port                              |
| `MAX_BATCH`         | `40`                     | Strings per LLM call (chunked above this) |
| `LANG_CONCURRENCY`  | `3`                      | Target languages translated in parallel   |
| `OLLAMA_TIMEOUT`    | `600`                    | Seconds per LLM call                      |
| `NUM_CTX`           | `8192`                   | Ollama context window                     |
| `OLLAMA_KEEP_ALIVE` | `30m`                    | Keep model resident in VRAM (`-1` = pin)  |

## VRAM & model residency (does it reload per language?)

**No.** There is **one** multilingual model. The target language is a prompt
parameter, not a different model — translating to all 13 locales reuses the same
resident weights with zero reloads between languages. (This is a key reason we
chose an instruction LLM over classic MT: NLLB/Opus-MT *are* per-language-pair
models and would swap per language.)

The only time weights leave VRAM is Ollama's **idle auto-unload** (default 5 min).
`OLLAMA_KEEP_ALIVE` (default `30m` here) keeps the model warm across a pass; set
`-1` to pin it for the box's lifetime. During an active pass requests are
continuous, so it stays warm regardless.

Sizing for a single resident model (rough Q4 footprints):
`qwen2.5:14b` ≈ 9 GB, `:32b` ≈ 20 GB, `:72b` ≈ 47 GB. If the model is larger than
VRAM, Ollama offloads layers to system RAM/CPU — **slower, but still no
per-request reload.** Note an actual RTX 4060 is 8 GB (4060 Ti is 16 GB); 32 GB of
VRAM is a bigger card (e.g. RTX 5090) or multi-GPU — confirm `nvidia-smi` and pick
the model row that fits.

## HTTP API

### `GET /health`
Liveness + whether the model is pulled.

### `GET /languages`
The 13 supported target locales.

### `POST /translate` — one string
```bash
curl -s http://BEAST:8765/translate -H 'content-type: application/json' -d '{
  "text": "Delete {{count}} host(s)?"
}'
```
```json
{ "source": "Delete {{count}} host(s)?",
  "translations": { "de": "{{count}} Host(s) löschen?", "fr": "...", "...": "..." } }
```

### `POST /translate/batch` — many strings (the efficient path)
Translate a whole list in one request. Optionally restrict `targets`.
```bash
curl -s http://BEAST:8765/translate/batch -H 'content-type: application/json' -d '{
  "texts": ["Save", "Settings", "Delete {{count}} host(s)?"],
  "targets": ["de", "ja"]
}'
```
```json
{ "count": 3, "targets": ["de","ja"],
  "results": [
    {"source":"Save","translations":{"de":"Speichern","ja":"保存"}},
    {"source":"Settings","translations":{"de":"Einstellungen","ja":"設定"}},
    {"source":"Delete {{count}} host(s)?","translations":{"de":"...","ja":"..."}}
  ] }
```

Always batch from the clients — one round-trip per chunk instead of per string.

## Robustness contract (so a translation pass never half-dies)

- **Placeholder/code/empty strings** (no letters) are returned unchanged without
  hitting the model.
- A chunk whose JSON comes back the wrong length is retried **one string at a
  time**; anything still failing falls back to the **English source**, so every
  result is complete and index-aligned. The clients then simply re-run later to
  pick up anything that fell back — the pass is resumable.

## How the clients use it (idempotent by design)

The backfill clients only ever send **untranslated** strings — `[TODO]`
placeholders (docs/frontend JSON), empty `msgstr` (backend/agent gettext `.po`),
or values still identical to English. Already-translated strings are never
re-sent, so re-running a pass is cheap and only fills genuine gaps.
