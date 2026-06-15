# Relocating multi-tenancy into a licensed Pro+ engine

**Goal:** make multi-tenancy a commercial-only capability that cannot be run by
a fork of the OSS product — a true *technical* moat, not just a license flag —
by moving the implementation into a compiled Cython engine
(`multitenancy_engine`) distributed only under a new `MULTITENANT_SAAS` license
tier.

## How Pro+ engines work here (the model we're matching)
- An engine is authored under `sysmanage-professional-plus/module-source/<name>_engine/`,
  **compiled to Cython** (`.so`), signed, and served by the license server.
- The OSS server downloads + verifies + dynamically loads an engine only when
  the license grants it (`backend/licensing/module_loader.py`).
- OSS carries **stubs/seams** (e.g. `backend/api/proplus_routes.py`) that mount
  the engine's routes when it's loaded and return `{licensed: false}` otherwise.
- **Schema stays in OSS.** Federation's models (`models/federation.py`) and
  migrations live in OSS; only the *logic* is the engine. The public schema is
  harmless — the value (and the hard part) is the orchestration logic.

## The boundary for multi-tenancy

### Stays in OSS (seams + schema — public, inert without the engine)
- **Models + migrations:** `models/tenancy.py` (registry/shared/tenant tables)
  and the `r*registry` / `o12mgttenant` / `n11cfgsettings` migrations. Schema is
  public; harmless without the logic.
- **The partition-resolver seam** (`persistence/partitions.py`): keeps the
  collapsed default (`resolve_engine`/`get_request_engine` → `db.get_engine()`),
  and **defers to a registered engine hook** for tenant routing when one is
  loaded. With no engine: behaves exactly like today (single DB).
- **The gate:** `config.is_multitenancy_enabled()` returns True only when the
  config flag is set **AND** the `multitenancy_engine` is loaded under a valid
  `MULTITENANT_SAAS` license. Off → control-plane router never mounts, resolver
  stays collapsed, data plane never routes.
- **Stub control-plane routes** (return `licensed: false` / 404 when no engine).
- **Inert primitives:** `tenant_context` (the active-tenant ContextVar) can stay
  — it's a harmless no-op without the engine.

### Moves to `multitenancy_engine` (Pro+, compiled, license-gated)
The licensed logic — the hard, valuable parts:
- Control-plane API **logic** (tenant/user/grant/email-domain/placement/
  enrollment-token/auto-provision/delete/migration-status endpoint bodies).
- Orchestration: `tenant_orchestration`, `enrollment_service`,
  `tenant_provisioning`, `tenant_data_mover`, `migration_status`,
  `host_tenant_index`, `tenant_directory`.
- The **OpenBAO TenantEngineManager** (`persistence/tenant_engine.py`,
  `services/openbao_db_secrets.py`) — dynamic per-tenant credential leasing.
- The **tenant-routing implementation** behind the resolver seam.
- Per-tenant config/email resolution + the active-tenant middleware.
- Account switching (`/auth/switch-account` logic).
- The per-tenant fan-out + data-mover used by `sysmanage-migrate`.

### Frontend
The Tenants page, tenant switcher, and the tenant-migration banner become a
**Pro+ JS bundle** (built in `sysmanage-professional-plus/frontend`, downloaded
like other Pro+ bundles). OSS keeps the nav gate (the "Tenants" link is hidden
unless `multitenancy_engine` is licensed).

### License server
Add the `MULTITENANT_SAAS` tier + the `multitenancy_engine` module to the
license server; issue it to no one but yourself. (`sysmanage-professional-plus`.)

## The genuinely hard parts (and how we handle them)
1. **The resolver seam must be airtight.** OSS data-plane code calls
   `get_request_engine(tenant_id)`. With no engine it MUST collapse to
   `db.get_engine()` (today's behavior); with the engine it routes per-tenant.
   We add an engine-registration hook the engine fills on load.
2. **Migration tooling.** The registry/shared/tenant alembic chains stay in OSS
   (schema). The per-tenant *fan-out* (needs OpenBAO + TenantEngineManager) is
   engine logic; `sysmanage-migrate` defers to the engine when loaded, and is a
   pure single-DB chain runner otherwise.
3. **No cross-boundary imports.** OSS must never import engine modules directly
   — only via the loader/hook registry — or the build breaks for OSS-only users.
4. **Tests.** Engine tests move to the Pro+ repo; OSS keeps seam tests (verifies
   collapsed behavior + that stubs return `licensed: false`).

## Phased execution (incremental, OSS stays green throughout)
- **Phase 0 — OSS seam. ✅ DONE.** `backend/multitenancy/seam.py` is the engine
  registry (`register_engine` / `active_engine` / `is_engine_present`) + the
  `MultitenancyEngine` protocol. Two decision points defer to it with an OSS
  fallback: per-tenant engine resolution (`partitions.resolve_engine` tenant
  path) and control-plane router mounting (`route_registration`). With no engine
  registered, OSS is byte-for-byte today's behavior (verified — the full MT
  suite still passes). `is_multitenancy_enabled` stays config-based for now; its
  gate-flip (require the engine) happens once the logic has moved (later phase),
  so the running system isn't broken mid-relocation.
- **Phase 1 — engine skeleton.** Create `module-source/multitenancy_engine`
  that, on load, registers the hooks + mounts the control-plane router (initially
  re-exporting today's logic).
- **Phase 2 — move logic file-by-file** from OSS into the engine, replacing each
  OSS file with a stub/seam. Run both test suites after each move.
- **Phase 3 — frontend bundle.** Move the MT UI to the Pro+ frontend bundle;
  OSS keeps the nav gate.
- **Phase 4 — license tier + packaging.** Add `MULTITENANT_SAAS` +
  `multitenancy_engine` to the license server; wire bundle download/verify.
- **Phase 5 — migration/tooling boundary** + final cleanup; verify an OSS-only
  build has zero multi-tenancy capability.

## Recommended start
**Phase 0** — the OSS-side seam. It's the foundation, it's safe (OSS keeps
working exactly as today since no engine is registered), and it's the contract
every later phase plugs into. Everything else is mechanical once the seam exists.
