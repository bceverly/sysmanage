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
2. **Pull the model the service picks.** By default the service is turnkey: it
   detects your VRAM on startup and **auto-selects** the model (or a CPU model if
   there's no GPU) — you do **not** set `TRANSLATION_MODEL` unless you want to pin
   one. The startup banner prints the chosen tag and, if it isn't pulled yet, the
   exact `ollama pull` line to run. Easiest path: start the service once, read the
   banner, run the pull it prints, restart.

   Auto-selection tiers (largest model that fits with headroom for KV-cache):
   | Total VRAM   | Auto-selected model     |
   |--------------|-------------------------|
   | none (CPU)   | `qwen2.5:7b-instruct`   |
   | < 6 GB       | `qwen2.5:3b-instruct`   |
   | 6–10 GB      | `qwen2.5:7b-instruct`   |
   | 11–21 GB     | `qwen2.5:14b-instruct`  |
   | 22–45 GB     | `qwen2.5:32b-instruct`  |
   | 46 GB+       | `qwen2.5:72b-instruct`  |
   Qwen2.5 is strong across all 13 (incl. CJK, Arabic, Hindi). To pin a different
   model — any Ollama tag, e.g. Gemma 2 / Llama 3.x — set `TRANSLATION_MODEL` and
   pull that one instead:
   ```bash
   ollama pull qwen2.5:14b-instruct     # or whatever the banner tells you
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
python3 translate_service.py                       # auto-selects model from VRAM
# pin a model instead of auto-selecting:
TRANSLATION_MODEL=qwen2.5:32b-instruct python3 translate_service.py
# or run via uvicorn:
uvicorn translate_service:app --host 0.0.0.0 --port 8765
```

The banner on startup prints the chosen model and why (e.g.
`model : qwen2.5:14b-instruct [auto-selected for 16.0 GiB VRAM]`), plus the GPU
and free VRAM.

Bind `0.0.0.0` so the dev box can reach it over the LAN. Confirm it's healthy:

```bash
curl -s http://localhost:8765/health | python3 -m json.tool
```
`status: ok` means Ollama is reachable AND the model is pulled.

## Configuration (env vars)

| Var                 | Default                  | Meaning                                   |
|---------------------|--------------------------|-------------------------------------------|
| `TRANSLATION_MODEL` | *auto (from VRAM)*       | Pin an Ollama tag; unset = auto-select    |
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

**The service does this sizing for you** (see the auto-selection table above) —
this is just the reasoning. Single-resident-model footprints (rough Q4):
`qwen2.5:7b` ≈ 5 GB, `:14b` ≈ 9 GB, `:32b` ≈ 20 GB, `:72b` ≈ 47 GB. If a pinned
model is larger than VRAM, Ollama offloads layers to system RAM/CPU — **slower,
but still no per-request reload.** (For reference, an RTX 4060 is 8 GB, a 4060 Ti
is 16 GB; bigger numbers mean a bigger card or multi-GPU — `nvidia-smi` confirms.)

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

## The backfill client (`i18n_backfill.py`)

One tool backfills every project's locale store. Run it **from your dev box**
(where all the repos are checked out as siblings), pointed at the service:

```bash
pip install polib          # only needed for the .po projects (backend, agent)

python3 i18n_backfill.py --project docs     --service http://beast:8765
python3 i18n_backfill.py --project frontend --service http://beast:8765
python3 i18n_backfill.py --project proplus  --service http://beast:8765
python3 i18n_backfill.py --project backend  --service http://beast:8765
python3 i18n_backfill.py --project agent    --service http://beast:8765
```

| `--project` | Store | Format | Gap |
|-------------|-------|--------|-----|
| `docs`      | `sysmanage-docs/assets/locales/<lang>.json` | JSON | `[TODO] …` |
| `frontend`  | `sysmanage/frontend/public/locales/<lang>/translation.json` | JSON | `[TODO] …` |
| `proplus`   | `sysmanage-professional-plus/frontend/public/locales/<lang>/translation.json` | JSON | `[TODO] …` |
| `backend`   | `sysmanage/backend/i18n/locales/<lang>/LC_MESSAGES/messages.po` | gettext | empty `msgstr` |
| `agent`     | `sysmanage-agent/src/i18n/locales/<lang>/LC_MESSAGES/messages.po` | gettext | empty `msgstr` |

Useful flags: `--dry-run` (report gap counts, no service/writes), `--langs de,ja`
(subset), `--limit 20` (cap per language for a smoke test), `--root <dir>` (where
the repos live; defaults to the parent of the `sysmanage` repo),
`--client-batch N` (strings per request, default 100). Service URL also reads
`TRANSLATION_SERVICE_URL`.

**Idempotent by design** — it only ever sends **untranslated** strings (`[TODO]`
placeholders or empty `msgstr`). Already-translated entries are never re-sent, so
re-running is cheap and only fills genuine gaps.

**Conservative** — if the service returns the English source for a string (its
placeholder guard couldn't translate it safely), the client **leaves that entry a
gap** rather than writing English, so a later run retries it. Pure-placeholder
strings (no letters) are written through unchanged as normal.

### Going forward (new English strings)
The normal i18n flow already seeds new strings as `[TODO] …` (JSON, via each
project's `i18n_autotag`/`i18n_validate`) or empty `msgstr` (gettext, via
`xgettext`/`msgmerge`). So after adding English UI/doc/log strings, run the
relevant `--project` backfill and the new strings get translated automatically —
nothing else to wire up.
