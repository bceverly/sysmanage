# Phase 13.1 — Multi-Tenancy: Architecture & Isolation Design

**Status:** Design / proposal (June 2026)
**Scope:** Account isolation for SysManage (Phase 13.1, Enterprise GA / v3.0.0.0)
**Provenance:** Distilled from a design session grounded in a read-only audit of
the current schema + auth layer. The recommended direction is a **control plane +
silo** model — the same architecture the author shipped at PeopleStrategy (c.
2000), which the industry later standardized (AWS SaaS Lens "silo + tenant
catalog").

> **Reading guide.** Sections 1–3 frame the problem and the isolation-model
> decision. Sections 4–11 are the design proper (registry, partitions, config,
> credentials, auth, backup). Section 12 is the migration/Alembic plan and the
> hard rules. Section 13 is the implementation slicing. Section 14 lists the
> decisions still open for Bryan.

---

## 1. Problem statement

Phase 13.1 calls for an *account model with isolation*, *account switching for
users with multiple accounts*, *per-account settings and limits*, and *data
isolation verification*. Today the deployment is single-tenant:

- ~140 SQLAlchemy tables in **one shared schema**, one `Base`, one connection URL
  (SQLite in test, PostgreSQL in prod) — `backend/persistence/db.py:22-52`.
- **No** `tenant_id` / `org_id` / `account_id` anywhere — greenfield.
- The only existing org boundary is the **AccessGroup** hierarchy
  (`backend/persistence/models/access_groups.py`), enforced purely at the
  query/API layer — no DB-level isolation, no FK to a tenant.
- Auth is JWT carrying only `user_id` (`backend/auth/auth_bearer.py:63-79`); RBAC
  is `SecurityRoles` checked manually via `auth_user.has_role(...)`
  (`backend/security/roles.py`). No tenant in the token, no row scoping.

## 2. Federation ≠ Multi-Tenancy (keep them hard-separated)

These are **orthogonal axes** and must stay separate in code, config, and docs:

- **Federation = multi-*site*.** One organization's fleet distributed across
  locations (coordinator + sites, Phase 12). A large on-prem customer uses it for
  scale/distribution and wants **none** of the multi-tenancy machinery.
- **Multi-tenancy = multi-*customer*.** Distinct organizations isolated behind a
  control plane.

They **compose** (a SaaS tenant could itself be internally federated) but neither
requires the other. Multi-tenancy is an **opt-in deployment topology**
(`multitenancy.enabled`, default **false**) — when off, the install behaves
exactly as today and the control-plane API does not even mount. Terminology must
not collide: federation owns *coordinator* / *site*; multi-tenancy owns *control
plane* / *registry* / *tenant*.

## 3. Isolation-model decision

Standard SaaS isolation tiers: **pool** (shared schema + `tenant_id` column),
**bridge** (schema-per-tenant, one DB), **silo** (DB-/instance-per-tenant).

| Dimension | Pool (`tenant_id`) | Bridge (schema/tenant) | **Silo (DB/tenant)** |
|---|---|---|---|
| Isolation | Logical (row) | Logical (namespace) | **Physical** |
| Blast radius of a missing `WHERE` | All tenants | One tenant | **One tenant** |
| Per-tenant point-in-time restore | Very hard (surgical row extract) | Moderate | **Easy (`pg_restore` one DB)** |
| Provable erasure / offboarding | `DELETE WHERE`, hard to prove | Drop schema | **Drop database** |
| Noisy-neighbor / residency | No | No | **Yes** |
| SQLite-compatible (test suite) | Yes | **No** (no schemas) | Yes |
| Migrations | Once | × N schemas | × N databases |
| Cross-tenant analytics | Trivial | N-way UNION | Fan-out / rollup |
| Op. overhead | Low | Medium-high | High (automatable) |

**Decision: silo (database-per-tenant) + a control-plane registry — recommended
primary.** Reasons:

1. **Backup/restore is the deciding factor.** Per-tenant restore is invisible in
   the architecture review and a five-alarm fire the first time it's real. In
   pool you restore a scratch copy and surgically re-extract one tenant's rows
   across ~70 tables in FK order at 2am; in silo you `pg_restore`/PITR one
   database. This single property forces many SaaS shops to re-architect pool→silo
   mid-life — the most miserable migration in SaaS. Designing for it up front is
   cheap insurance.
2. **It's the only model that truthfully answers the enterprise security battery**
   — physical separation, one-tenant blast radius, per-tenant restore, provable
   erasure, residency.
3. **SysManage already owns the silo primitive.** Federation is silo at the
   instance level (coordinator = control plane, site = tenant). Multi-tenancy
   reuses those mental models with a lighter-weight realization (per-tenant *DB*,
   shared app tier).

**Bridge is rejected** — SQLite has no schema namespace, so the test suite could
never exercise it (violates the hard SQLite+Postgres rule).

**Pool + PostgreSQL RLS is retained as a secondary tier** — but **DEFERRED past
v3.0 GA (Bryan, June 2026): GA ships silo-only.** The registry / grant / identity
layer is designed so a `tier: pool` can be added later under the same control plane
without rework; it is built only when a real price-sensitive long-tail segment
materializes. Rationale for the tier (when built): for a price-sensitive **SMB long
tail** where standing up a DB per tenant isn't economical, run those tenants pooled
in a shared DB with Row-Level Security as the DB-enforced backstop — **under the
same registry**. The registry's email→tenant
catalog maps a user to their tenants regardless of whether a given tenant lives in
its own DB (silo) or in the shared pool, and a tenant can be **migrated between
tiers** as it grows. Enterprise accounts get silo; the long tail gets pool+RLS;
one identity + grant layer over both.

## 4. The control plane (the "registry")

A small **registry** database is the control plane / source of truth. (Name chosen
to avoid "master" baggage and to not collide with federation's "coordinator".
"Tenant catalog" is the AWS-standard synonym.) The registry holds **routing and
authorization, never tenant business data and never tenant DB credentials**:

- `registry_tenant` — the tenant (account): id, name, slug, status
  (active/suspended), `settings`/`limits` JSON.
- `registry_user` — global identity keyed by **email** (one identity, many
  tenants). Owns authn (password/MFA) for non-SSO users.
- `registry_user_tenant_grant` — the **explicit email→tenant mapping** (1..*).
  Carries role, `is_default`, and supports **time-boxed / expiring** grants.
  *This is the least-privilege core (see §9).*
- `registry_tenant_placement` — per-tenant DB **coordinates only**: `host`,
  `port`, `dbname`, `region`/placement, `tier` (silo|pool), `openbao_role`
  reference. **No credentials.**
- `registry_tenant_idp` — per-tenant SSO/IdP config (§9).
- `registry_tenant_email_domain` — per-tenant allowed email-domain allowlist (§10).
- `registry_tenant_backup_status` — per-tenant last-good backup + RPO (§11).
- `registry_tenant_db_version` — each tenant DB's current Alembic revision (§12).

### Two APIs (a security boundary, not just tidiness)
- **Control-plane API (management).** Provision tenants, manage grants, store
  placement/IdP config, broker credentials, orchestrate migrations/backups.
  High-privilege, operator-facing, **never** exposed to tenant end-users.
- **Data-plane API (the existing SysManage API).** Serves tenant users; per
  request it routes to the correct tenant DB and uses a cached lease. A data-plane
  process only ever holds creds for tenants it is actively serving — it cannot
  enumerate or provision anyone.

### Data plane shape (decided: keep it simple)
A **single shared data-plane app tier that can connect to multiple tenant DBs** —
*not* per-tenant worker/process isolation. (Per-process tenant isolation is
stronger but over-engineered for now; revisit only if a memory-isolation
requirement appears.)

## 5. Logical partitions & the three deployment modes

Data is split into logical **partitions**: `registry`, `shared` (reference data),
and one `tenant` partition per customer. The same model definitions and the same
migration chains deploy across a spectrum of physical layouts, chosen by **config,
not code**:

| Mode | Audience | Physical layout | Setup cost |
|---|---|---|---|
| **Homelab / OSS (default)** | single user, single tenant | **1 database**, all partitions collapsed into one namespace, distinguished by table-name prefix | **zero extra** |
| **Single-server, schema-isolated** | small hosted | 1 Postgres, partitions in separate schemas (`tenant_<id>`) | 1 server |
| **Multi-DB SaaS** | enterprise / scale | registry DB + shared/reference DB + **N** tenant DBs across servers/regions | **2 + N** databases |

The arithmetic Bryan framed: **2 fixed** (registry + shared/reference) **+ N**
tenant databases at the top end, **collapsed to 1** at the bottom.

### How the collapse works without penalizing the homelab user
Two mechanisms, used together:

1. **Prefix namespacing (always on).** Registry tables are `registry_*`, shared
   tables `shared_*`, tenant tables run unprefixed. In collapsed mode all three
   chains land in one namespace and **name collisions are structurally
   impossible** — tenant tables already coexist today and never carry those
   prefixes. The prefix is **stable across all modes** (a table is named
   `registry_tenant` whether collapsed in one SQLite file or alone in a dedicated
   registry Postgres), so **no rename migration when a homelab user graduates** to
   multi-DB.
2. **Partition resolver + `schema_translate_map` (only when separating).** Tables
   carry a *symbolic* schema token (`registry`/`shared`/`tenant`), never a literal
   location. At session-bind time a resolver picks the **engine** and supplies a
   `schema_translate_map`; mapping a token to `None` removes qualification (the
   SQLite-safe collapse). Because qualification is runtime-injected, the migration
   code is dialect-clean everywhere.

```python
# Model: symbolic token, never a literal location
class Tenant(Base):
    __tablename__ = "registry_tenant"
    __table_args__ = {"schema": "registry"}

# Homelab: one engine, collapse all tokens (SQLite-safe)
Session(bind=engine_local.execution_options(
    schema_translate_map={"registry": None, "shared": None, "tenant": None}))

# SaaS: resolver routes to the right engine per partition
Session(bind=engine_for(tenant_id).execution_options(
    schema_translate_map={"tenant": None}))
```

**Decided (Bryan, June 2026): the homelab/default mode skips `schema_translate_map`
entirely** — the **prefix is the namespace**, one SQLite file, three chains side by
side, and the resolver always returns the single engine. `schema_translate_map` and
the engine-routing resolver are engaged **only** in the single-server-schema and
multi-DB modes. Because prefixes are stable across modes, turning that machinery on
during scale-out renames no tables. (SQLite's `ATTACH DATABASE` maps onto the same
`schema_translate_map` abstraction, so the multi-partition path is still testable on
SQLite, not Postgres-only.)

### Three hard rules that make the collapse safe
- **Distinct Alembic version tables per chain.** Three chains in one DB need
  `alembic_version_registry`, `alembic_version_shared`, and `alembic_version`
  (tenant) or they stomp each other — set via `context.configure(version_table=…)`.
- **No foreign key may cross a partition boundary.** A FK from a tenant table to
  `registry_tenant` works in collapsed mode but **cannot exist** once registry is
  a separate DB (neither Postgres nor SQLite supports cross-database FKs — not even
  across ATTACHed SQLite files). Therefore **every cross-partition reference is a
  *soft* reference**: store the UUID, **no `ForeignKey` constraint**, enforce
  integrity in the app layer. FKs are allowed **within** a partition. This is the
  rule most likely to be violated by accident and the one that silently breaks
  split-ability — call it out in review.
- **A CI guard enforces the prefix convention.** ~20 lines asserting the registry
  chain only creates `registry_*`, the shared chain only `shared_*`, and the
  tenant chain neither — so "we agreed on a convention" can't rot, especially in
  the unprefixed tenant chain where a stray name would most plausibly sneak in.

> Mnemonic: **prefixes give namespace safety in collapsed mode; soft
> cross-partition references give split-ability; the CI guard keeps both honest.**

## 6. Shared reference data

The CVE catalog, package metadata, and mirror tables are identical for every
tenant and must **not** be replicated into every tenant DB (multi-GB waste). They
live in their own `shared` partition (`shared_*` tables) — collapsed into the one
DB for homelab, a dedicated reference DB in SaaS. Tenant rows that reference shared
data (e.g. a host vulnerability finding → a CVE) use **soft references** (§5) so
the split holds.

## 7. Configuration (`sysmanage.yaml`)

Principle: the config file answers **one** question — *"how do I reach the
registry?"* — and the registry is the source of truth for everything else.
Per-tenant placement is **runtime data, not config** (tenants are provisioned and
rebalanced live; hand-editing YAML per onboarding is wrong).

**Homelab — unchanged from today (reinterpreted):**
```yaml
database:            # now means "the registry / bootstrap DB"
  host: ...          # or a local sqlite path
  name: sysmanage
  user: ...
  password: ...
# no multitenancy block → collapsed mode; registry + shared_ + the single
# tenant all live here, distinguished by prefix. Zero new required keys.
```

**SaaS — grows only by what bootstrap genuinely needs:**
```yaml
registry:                       # former "database" block, renamed for clarity
  host: registry-db.internal
  port: 5432
  name: sysmanage_registry
  credentials: openbao://...    # or an inline bootstrap secret
multitenancy:
  enabled: true
secrets:
  openbao_addr: https://vault.internal:8200   # approle/token for bootstrap
```

- `database:` → `registry:` — **DECIDED (Bryan, June 2026): alias-and-deprecate.**
  v3.0 accepts both keys (`registry:` preferred; `database:` honored with a
  deprecation warning from the config loader), so existing/homelab configs keep
  working untouched; the alias is dropped in a later major. In collapsed mode
  they're the same connection anyway.
- Reference-DB placement and all N tenant placements are **rows in the registry**
  (`host, port, dbname, region, openbao_role`) — **never credentials**.
- Bootstrap chain: **YAML → open registry → read placement rows → resolve engines
  → lease creds from OpenBAO.** The registry's *own* credential (or an OpenBAO
  address+token to fetch it) is the single bootstrap secret in YAML/env; every
  other credential is a dynamic lease.
- `multitenancy.enabled` (default false) gates the whole thing: when false the
  control-plane API doesn't mount, the resolver is hardwired to one engine, and
  behavior is identical to today.

## 8. Credentials: OpenBAO dynamic secrets + an API-layer lease cache

- **One OpenBAO** (HA cluster) for the control plane, using its **database secrets
  engine** to issue *dynamic, short-lived, per-tenant DB credentials* on demand.
  No tenant DB password is ever stored; a leaked lease auto-expires; revocation is
  centralized. **Not** one OpenBAO per tenant. Builds on the existing
  `VaultService` / lease handling (Phase 8.7 / 12.5).
- **API-layer lease cache** (hitting OpenBAO per transaction is fatal for
  latency/cost): cache the dynamic lease **in process memory only** (never disk,
  never logs), keyed by tenant, with a TTL slightly under the lease TTL and
  **proactive renewal**. Hang a **per-tenant warm connection pool** off the cached
  cred with idle eviction. On a DB auth failure (cred rotated/revoked) **evict and
  re-lease** — that's the revocation path. Blast radius of a memory compromise is
  limited to the tenants that process is actively serving.

## 9. Auth & identity

- **Two identity realms.** SysManage staff authenticate against the control
  plane's own identity; tenant users authenticate against **their** tenant's IdP.
  The `registry_user_tenant_grant` table bridges staff→tenant for cross-tenant /
  MSP cases.
- **Per-tenant identity federation.** Each tenant configures its own IdP
  (Entra/Azure AD, Okta, generic OIDC/SAML); SysManage acts as SP/RP. Promote the
  existing `ExternalIdpProvider`/`IdpRoleMapping`/`ExternalIdpSettings` to the
  *tenant* level in the registry.
- **Customer owns the user lifecycle.** With SSO + **JIT provisioning** (or
  **SCIM**), the customer's IdP is the source of truth: their admins decide who
  exists, who gets in, and (via group→role mapping) what they can do.
  Deprovisioning in Azure AD removes access. SysManage is out of the signup
  business for these tenants.
- **Account switching.** A user with grants to multiple tenants switches the
  *active* tenant via `POST /auth/switch-account`, which re-mints the token to
  carry `user_id` + active `tenant_id`. `get_current_tenant()` (new dependency,
  alongside `get_current_user`) resolves and verifies membership.
- **Explicit, *enforced*, expiring vendor-support grants (de-theatered).** By
  default SysManage staff have **no** grant to a customer's tenant. The customer
  grants time-boxed access from their tenant-admin UI ("grant vendor support for
  48h"), fully audit-logged and auto-expiring. The control is made *real* by tying
  it to credential issuance: **no active grant → OpenBAO will not lease the support
  process creds for that tenant → the tooling literally cannot open the database.**
  A loud, heavily-audited **break-glass** path covers true emergencies. This turns
  a cosmetic "we promise" into a defensible least-privilege control — exactly what
  wins enterprise security reviews.

## 10. Per-tenant email-domain allowlist

A per-tenant allowlist (`registry_tenant_email_domain`) surfaced in the
tenant-admin settings UI and **enforced at provisioning time** (invite /
SSO-JIT / SCIM): a user whose email domain isn't allowlisted cannot be added.

## 11. Backup / restore

Silo's headline benefit. Per-tenant restore = `pg_restore`/PITR of one database
(optionally to a side DB for customer verification, then cut over); blast radius is
one customer. Enables per-tenant retention, differentiated backup SLAs,
customer-initiated exports, and provable offboarding deletion. The cost **shifts**
from "restore is agony" to "did all N backups run and are they restorable" — a
tractable, automatable problem owned by the control plane
(`registry_tenant_backup_status`: per-tenant last-good backup + RPO, automated
restore-testing).

## 12. Migration / Alembic plan

**Hard rules (Bryan's, enforced — see project memory `alembic-migration-rules`):**
each chain is a **single linear chain** (no second root / multiple heads), every
migration **idempotent**, every migration runs on **SQLite and PostgreSQL**. The
existing chain's current single head is **`m10fedseclease`** (verified — one head,
no open branches).

**Three independent Alembic environments**, each its own linear chain with its own
version table:

| Chain | Builds | Applied to | Version table |
|---|---|---|---|
| `alembic/registry/` | `registry_*` control-plane tables | the one registry DB | `alembic_version_registry` |
| `alembic/shared/` | `shared_*` reference tables | the one reference DB | `alembic_version_shared` |
| `alembic/tenant/` | the per-customer schema (≈ today's chain) | **each** tenant DB | `alembic_version` |

Driven by one `env.py` that branches on a `--name`; the registry tracks each
tenant DB's current revision (`registry_tenant_db_version`) so rollouts can be
**staged/canaried tenant-by-tenant** — and a bad migration's blast radius is one
tenant.

**Carving the existing chain (the real labor + the only real risk).** Today
everything is one 146-migration chain. Do **not** rewrite history:
- Freeze the existing chain as the **`tenant`** chain (it already builds the
  per-tenant schema).
- Grow **`registry`** as a brand-new chain off nothing (its own root — legitimately
  separate *environment*, not a second head in the same chain).
- Extract the `shared_*` reference tables into the **`shared`** chain via a
  deliberate relocation migration, converting any tenant→reference FKs to soft
  references (§5) as part of the move.

**Required idempotent / cross-dialect patterns:**
- Existence guards before every create/add (`sa.inspect(bind)` → check
  `table_names` / `get_columns`).
- `op.batch_alter_table` for **every** column add/alter (SQLite can't `ALTER`
  in place).
- Add columns nullable → backfill → enforce `NOT NULL` (SQLite can't add a
  `NOT NULL` column without a constant default).
- Use the project `GUID` type (CHAR(32) on SQLite / UUID on Postgres) — no
  dialect-specific DDL.
- Dialect-guard anything Postgres-only (e.g. pool-tier RLS): `if
  bind.dialect.name == "postgresql"`.
- Downgrades mirror the guards (drop only if present).

## 13. Implementation slices (roadmap-style)

- **13.1.A — Registry foundation.** `alembic/registry/` chain + `registry_*`
  models (tenant, user, grant, placement); the partition **resolver** + tenant-aware
  session factory; `multitenancy.enabled` toggle (default false → no behavior
  change); control-plane API skeleton. Homelab collapse working end-to-end with one
  DB. *Smallest safe first step.*
- **13.1.B — Tenant routing & identity.** `get_current_tenant`; token carries
  active `tenant_id`; `POST /auth/switch-account`; email→tenant grant CRUD;
  per-tenant email-domain allowlist.
- **13.1.C — Credentials & placement.** OpenBAO database-secrets-engine
  integration; API-layer lease cache + per-tenant warm pools; `registry_tenant_placement`
  routing to separate engines; per-tenant DB provisioning automation.
- **13.1.D — Shared-reference split.** `alembic/shared/` chain; relocate `shared_*`
  tables; convert cross-partition FKs to soft references; CI prefix guard.
- **13.1.E — SSO & enforced grants.** Per-tenant IdP (Entra/Okta/OIDC/SAML),
  JIT/SCIM provisioning; vendor-support grants tied to OpenBAO issuance; break-glass.
- **13.1.F — Backup orchestration & data-isolation verification.** Per-tenant
  backup/RPO tracking + automated restore tests; the two-tenant cross-leak test
  harness (the roadmap's "data isolation verification" deliverable). *(Pool+RLS SMB
  tier deferred past GA — see §3.)*
- **13.1.G — Config builder & deployment docs.** Update the installer's config
  builder and the deployment documentation so an operator can actually stand up
  each of the three modes:
  - **Config builder** — `scripts/_sysmanage_secure_installation.py` currently
    prompts for and writes a single `database:` block (`get_database_config()` →
    `update_database_config()`). Extend it to:
    - treat `database:` as the **registry/bootstrap** pointer (rename to
      `registry:` with `database:` accepted as a deprecated alias);
    - prompt for **deployment mode** (homelab single-DB / single-server
      schema-isolated / multi-DB SaaS) and only ask for the extra
      registry/reference/OpenBAO details when `multitenancy.enabled` is chosen —
      **the homelab/OSS path must keep its current single-prompt simplicity**;
    - write the `multitenancy` + `secrets` (OpenBAO addr/bootstrap) blocks only
      in SaaS mode; never write tenant/reference *placements* to YAML (those are
      registry data).
    - keep `sysmanage.yaml.example` / `sysmanage-dev.yaml.example` (and the
      per-installer `installer/*/sysmanage.yaml.example`) in sync with the new
      shape.
  - **Deployment docs (`sysmanage-docs`)** — update the deployment surface to
    document the registry/control-plane model, the three modes, the `2 + N`
    database topology, OpenBAO dynamic-cred setup, and per-tenant SSO/grant config.
    Affected pages at minimum: `docs/deployment/configuration.html`,
    `docs/deployment/deployment.html`, `docs/deployment/installation.html`,
    `docs/deployment/secure-installation.html`, `docs/server/deployment.html`,
    and `docs/getting-started/first-deployment.html`. Make explicit that
    multi-tenancy is opt-in and that homelab/on-prem/federated deployments are
    unaffected. i18n the new strings across all supported locales.

## 14. Open decisions for Bryan

1. ~~**Homelab simplest mode:** pure prefix-only single namespace vs. always-on
   `schema_translate_map`.~~ **DECIDED (Bryan, June 2026): prefix-only.** The
   default single-DB homelab/OSS deployment uses table-name prefixes as the *only*
   separation mechanism — **no `schema_translate_map`, no resolver indirection** in
   this mode (the resolver simply always returns the one engine). Schemas/separate
   engines are introduced only on scale-out, and because prefixes are stable across
   modes, that flip renames no tables. See §5.
2. ~~**`database:` → `registry:` rename:** alias-and-deprecate vs. rename outright.~~
   **DECIDED (Bryan, June 2026): alias-and-deprecate.** v3.0 reads both keys
   (`registry:` preferred, `database:` honored with a deprecation warning); the
   alias is removed in a later major. The config builder (13.1.G) writes
   `registry:`. See §7.
3. ~~**Pool+RLS SMB tier:** build in Phase 13 vs. defer.~~ **DECIDED (Bryan, June
   2026): defer — v3.0 GA ships silo-only.** The registry is designed so a
   `tier: pool` can be added later without rework. See §3. *(This also defers
   decision 4 below.)*
4. ~~**NOT NULL enforcement** on tenant-scoped columns in the pool tier.~~
   **MOOT / DEFERRED (Bryan, June 2026).** Silo tenant tables carry no `tenant_id`
   column (the database *is* the boundary), so there is nothing to enforce at GA.
   This decision is deferred and revisited if/when the pool+RLS tier (§3, decision
   3) is built.
5. ~~**Shared reference data home:** dedicated `shared` DB vs. fold into registry.~~
   **DECIDED (Bryan, June 2026): dedicated `shared` database.** Confirms the
   **2 + N** SaaS topology (registry + shared + N tenants); keeps the small,
   security-critical control-plane tables isolated from bulky, frequently-refreshed
   reference data. See §6.
