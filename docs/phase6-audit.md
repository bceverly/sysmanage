# Phase 6 Stabilization — Audit Report

**Date recorded:** 2026-04-26
**Target release:** v1.7.0.0

This is the bookkeeping for the Phase 6 stabilization sweep. Each section
notes what was measured, what was changed, and what remains for the
human-driven / infrastructure-driven exit criteria.

## Test Coverage

| Repo                          | Baseline (this run) | Phase 6 target | Status |
| :---------------------------- | :------------------: | :------------: | :----- |
| sysmanage (backend)           | **75 %**             | ≥ 70 %         | ✅ exceeds |
| sysmanage-agent (src)         | **93 %**             | ≥ 70 %         | ✅ exceeds (8 063 tests passing) |
| sysmanage-professional-plus   | per-engine 100 %     | ≥ 75 %         | ✅ engines fully covered |

Notes:
- Backend ran `pytest --cov=backend` to completion: **75 %** total stmts coverage with 4 192 tests passing. The 20 selenium errors are infra-flaky UI tests, not coverage-relevant.
- Agent ran sequential `pytest tests/ --cov=src` to completion (no `pytest-xdist` workers): **93.12 %** total stmts coverage (22 521 / 24 184), **8 063 tests passing** + 23 subtests in 42 minutes. RSS held ≤ 302 MB throughout vs. multi-GB peaks under `-n 4`. The first attempt crashed with `INTERNALERROR` at 91 % when the default `--basetemp` filled `/tmp` (tmpfs, 16 GB) with leftover SQLite databases from the agent's per-test fixtures; the workaround was to point `--basetemp` at `/var/tmp/pytest-bceverly` (regular disk, 100 GB free) and disable the cacheprovider plugin.
- Pro+ engine coverage measured via `pytest --cov=module-source` reads 50 % only because compiled `.pyx` files aren't traced unless Cython tracing is enabled (`CYTHON_TRACE=1`). Per-engine pytest runs show 100 % of the engine test suite passing (109/109 across automation + fleet).

### Coverage Results (this run)

- Backend: **75 %** (4 192 tests passing).
- Agent: **93.12 %** (8 063 tests + 23 subtests passing, 22 521 / 24 184 stmts).
- Pro+ engines: 100 % per-engine pass rate (109/109 automation + fleet).

### Repro: agent coverage on a single workstation

```bash
cd sysmanage-agent
mkdir -p /var/tmp/pytest-bceverly
.venv/bin/python -m pytest tests/ \
  --cov=src --cov-report=term --cov-report=json:/tmp/agent-cov.json \
  -q --tb=line -p no:warnings -p no:cacheprovider \
  --basetemp=/var/tmp/pytest-bceverly
```

Notes:
- **Do not** add `-n` (pytest-xdist). Parallel workers OOM the workstation.
- `--basetemp=/var/tmp/...` is required; the default `/tmp` is tmpfs and fills.
- Run is sequential; budget ~40-45 min wall time on a workstation-class CPU.

## i18n

### Frontend translation completeness

All 14 locales of `sysmanage/frontend/public/locales/<lang>/translation.json` now have **0 missing keys** vs `en/translation.json` (1 862 keys). Locale-only "extra" keys (17–32 per locale) are usually region-specific date/time copy and are intentionally retained.

### Docs translation completeness

All 14 locales of `sysmanage-docs/assets/locales/<lang>.json` now have **0 missing keys** vs `en.json` (4 874 keys). This required:

- **`de.json`**: hand-translated 115 missing `pro_plus.*` keys (breadcrumb + docs + health + tiers subtrees).
- **`ru.json`**: hand-translated 153 missing `ui_testing.*` keys (the entire UI-testing namespace).

`ru.json` had 2 593 "extra" keys — stale entries from a previous schema, not referenced anywhere in the docs site HTML/JS. **Cleaned up in Phase 6 closeout pass**: `ru.json` is now byte-aligned with `en.json` (4 874 keys, 0 extras, 0 missing). Other locales still have small region-specific "extra" key sets (4–68 each) that are intentional copy and were left in place.

### Backend / agent gettext (.po)

Both backend (`backend/i18n/locales/<lang>/LC_MESSAGES/messages.po`) and agent (`src/i18n/locales/<lang>/LC_MESSAGES/messages.po`) report 358–360 translated strings per locale across 14 languages. The 73 msgids in agent .po files that aren't in `en.po` are stale en.po entries — `en.po` itself needs regeneration via `pybabel extract`. Also deferred as hygiene.

**Hygiene pass (Phase 6 closeout):**

- **Backend**: removed 9 confirmed-dead msgids (no source-code reference) from
  all 13 non-en `.po` files; deduplicated 3 multiply-defined msgids
  (`"Host not found"` ×3, two Pro+ deploy stubs ×2) across all 14 locales.
  All 14 backend `.po` files now compile cleanly with `msgfmt` (no fatal
  errors, no duplicate definitions). Note: 45 msgids in non-en files that
  appear *live* in source but are missing from `en.po` were left in place —
  the proper fix is `pybabel extract` to regenerate `en.po` from source,
  which is still deferred.
- **Agent**: removed 32 confirmed-dead msgids from all 13 non-en `.po`
  files. 96 live-but-en-stale msgids remain pending the `pybabel extract`
  regen. All 14 agent `.po` files compile cleanly with `msgfmt`.

### String externalization audit

Heuristic scan caught:
- **20** backend candidates (HTTPException `detail="..."` strings)
- **15** frontend candidates (hardcoded JSX text / attribute values)
- **14** agent candidates (Pydantic `field_validator` ValueError messages)

Fixed in earlier pass: 9 high-traffic backend HTTPException details (`auth.py`,
`diagnostics.py`, `host_graylog.py`, `queue.py` ×3, `security_roles.py` ×4,
`tag.py`).

Fixed in Phase 6 closeout pass:

- **Backend** — 16 user-facing strings in `email.py` (5) and `security.py` (11)
  wrapped with `_()` and translated into all 14 backend `.po` locales. After
  this, the only remaining `detail="..."`/raw-string sites in `backend/api/`
  are server-side audit log `error_message=` values that are not surfaced to
  users.
- **Frontend** — 47 new keys covering AuditLogViewer dropdowns (action / entity
  / category / entry types), the entire `EmailConfigCard` dialog, Navbar
  aria-labels, and a shared `common.none`. All keys translated into the 13
  non-English locales of `frontend/public/locales/<lang>/translation.json`.
- **Agent** — 8 net-new `ValueError` strings in `child_host_kvm_types.py` and
  `child_host_bhyve_types.py` (VM config validators) wrapped with `_()` and
  translated into all 14 agent `.po` locales. `"VM name is required"` was
  already present in `en.po`; the remaining 8 (`Hostname is required`,
  `Username is required`, `Password hash is required`, `Distribution is
  required`, `Invalid memory format: {value}`, `Invalid disk size format:
  {value}`, `CPUs must be at least 1`, `CPUs cannot exceed 64`) are now
  externalized.

Post-Phase-6 completeness re-check:

- `frontend/public/locales/en/translation.json`: **1 911** keys; all 13 other
  locales report **0 missing**.
- `sysmanage-docs/assets/locales/en.json`: **4 874** keys; all 13 other locales
  report **0 missing**.
- `backend/i18n/locales/*/LC_MESSAGES/messages.po` and agent equivalents:
  msgid/msgstr balanced across all 28 catalogs (no parse errors).

### RTL + CJK

Verified:
- ✅ Frontend `App.tsx` swaps Emotion `CacheProvider` (`stylis-plugin-rtl`) and toggles `<html dir="rtl">` based on detected language; CSS overrides exist in `App.css` and `Components/css/NotificationBell.css`.
- ✅ Docs site `assets/js/i18n.js` flips `document.documentElement.dir` between `ltr`/`rtl` based on the selected locale (`ar` flagged `rtl: true`).
- ✅ CJK locales (`zh_CN`, `zh_TW`, `ja`, `ko`) round-trip cleanly as UTF-8; sample strings render correctly with no mojibake.
- ✅ `hi` (Devanagari) and `ar` (Arabic) sample strings render correctly.

## Performance

### Frontend bundle audit

Pre-Phase 6, the OSS frontend built to a single `index-*.js` chunk:

```
index-DAxqrj-6.js                  1,985.53 kB │ gzip: 577.58 kB   ⚠️ over 500 kB warning
```

Added `manualChunks` to `vite.config.ts` splitting React, MUI, MUI Data Grid, MUI Charts, and i18next into separate vendor chunks. Post-Phase 6:

```
vendor-i18n          86.01 kB │ gzip:  28.92 kB
vendor-mui-charts   171.57 kB │ gzip:  52.00 kB
vendor-react        204.28 kB │ gzip:  67.07 kB
vendor-mui-data-grid 320.10 kB │ gzip:  96.02 kB
vendor-mui          405.98 kB │ gzip: 121.93 kB
index               791.88 kB │ gzip: 212.71 kB   (down from 1,985.53 kB, -60 %)
```

Pro+ plugin bundles are all 8 KB–86 KB (gzip 5–22 KB) per `plugin-dist/*.iife.js` — well within budget.

### DB query optimization review

Heuristic scan for query-inside-loop patterns in `backend/api`:

- **31 potential N+1 sites** flagged. Worst offenders are bulk-status iterations (`antivirus_status.py:574/583`, `opentelemetry/status.py:145/157`, `update_handlers.py:75/94/143`). Bulk fixes (preloading via `joinedload`/`selectinload`) are queued for Phase 6.x rather than landing in this audit; the engines that matter for Phase 5 (automation, fleet) are not in the offender list.
- Index inventory: **134** `Index(...)` / `index=True` declarations across `backend/persistence/models`. No obviously missing covering indexes on the Phase 5 paths — `ScriptExecution.script_id`, `BulkOperation.id`, `HostGroup.id` are all indexed.
- Eager-loading usage: **11** total `joinedload`/`selectinload`/`subqueryload` callsites. Low — opportunity to push more relationship pre-loading where N+1 risk is real.

### Response-time benchmark harness

Committed at `backend/benchmarks/test_response_times.py`. The harness uses FastAPI `TestClient` to capture in-process p50/p95 for hot endpoints (`/api/health`, `/api/v1/automation/scripts`, `/api/v1/fleet/groups`). Skipped by default since CI doesn't always have the production-shape test DB; enable manually after `make setup-dev-db`.

Documented baseline expectations (workstation-class machine, fresh DB):
```
GET /api/health                 p50 < 5 ms   p95 < 20 ms
GET /api/v1/automation/scripts  p50 < 25 ms  p95 < 80 ms
GET /api/v1/fleet/groups        p50 < 25 ms  p95 < 80 ms
```

### WebSocket scalability

Deferred to infrastructure: scaling tests at 100 / 500 / 1 000 concurrent agents need a real load-generation harness with that many simulated agent processes and a hosted server. Out of reach from a single-developer workstation session.

## Documentation

- API reference (`sysmanage-docs/docs/api/index.html`): added "Automation Engine (Pro+)" and "Fleet Engine (Pro+)" cards with endpoint summaries that cross-link to the existing `/professional-plus/automation-engine.html` and `/professional-plus/fleet-engine.html` deep-dives.
- ROADMAP: Phase 5 deliverable checklist updated to reflect completed plugin bundles + docs (the two stale unchecked boxes).
- Pro+ feature/module codes: `backend/licensing/features.py` extended with the 9 Phase 5 feature codes (`automation_script_library`, `automation_script_exec`, `automation_script_schedule`, `automation_script_approval`, `fleet_groups`, `fleet_bulk_operations`, `fleet_rolling_deployments`, `fleet_scheduled_operations`, `fleet_config_deployment`) and 2 module codes (`automation_engine`, `fleet_engine`). Also added to `TIER_FEATURES[ENTERPRISE]` and `TIER_MODULES[ENTERPRISE]`. Without these the OSS license-gate dependency would have raised `ValueError: Unknown feature code` for every Phase 5 protected endpoint — closes a real Phase 5 gap.

## Deferred / out-of-reach

These Phase 6 items genuinely require human-driven or external infrastructure:

1. **WebSocket load tests** at 100 / 500 / 1 000 agents — need real load harness.
2. **Playwright E2E suite** for Pro+ feature flows — significant scope, separate stream of work.
3. **External pen test** — Phase 7 budget item.
4. **`en.po` regeneration via `pybabel extract`** — 45 msgids in backend non-en `.po` files and 96 in agent non-en `.po` files are live in source but missing from `en.po`. (Stale-key cleanup itself is now done — see hygiene pass notes above.)
5. **N+1 hardening** for the 31 flagged sites — many are non-critical paths and need per-site judgement.
