# sysmanage.yaml Configuration Classification

**Status:** Design / decided-in-principle (June 2026)
**Scope:** Decide, for every `sysmanage.yaml` option, whether it (A) **stays in
YAML** (bootstrap-only), (B) **moves to OpenBAO** (secrets), or (C) **moves to a
Settings → DB table** (server- or tenant-scoped runtime config). Drives the
`scripts/sysmanage_secure_installation*` rewrite, the production bootstrap, and the
`sysmanage-docs` config builder.

Companion to [`openbao-deployment-and-airgap.md`](openbao-deployment-and-airgap.md)
and [`phase13-multi-tenancy-design.md`](phase13-multi-tenancy-design.md).

---

## 1. Principle

`sysmanage.yaml` should answer exactly **one** question: *"how do I reach the things
I need before the database and OpenBAO are available?"* Everything else is either a
**secret** (→ OpenBAO) or **runtime configuration** (→ a DB-backed Settings table,
editable in the UI, tenant-scoped where it makes sense). Three rules:

1. **Bootstrap-only stays in YAML.** If it's needed to bind the listener or to reach
   the registry DB / OpenBAO *before* those exist, it stays. Nothing else.
2. **Secrets go to OpenBAO by default.** Userids/passwords/tokens/keys/salts are
   stored in OpenBAO, not on disk in YAML. The *one* permitted exception is the
   single bootstrap credential needed to reach OpenBAO/the registry itself
   (chicken-and-egg) — and even that should be a locked-down file, not YAML, where
   possible.
3. **Operational config goes to a Settings table.** Anything an operator would tune
   at runtime moves to the DB and the Settings UI. Things that vary per customer
   (email, password policy, branding) are **tenant-scoped**; things that are
   server-wide are **server-scoped** (the existing `server_configuration` singleton).

Email is the motivating example: **email must be *enabled* for password-set flows to
work, but the SMTP server + credentials are a per-tenant concern** — so the email
block leaves YAML entirely and becomes tenant-scoped DB settings (+ OpenBAO for the
SMTP password).

## 2. Classification table

Legend: **A**=stay in YAML (bootstrap), **B**=OpenBAO (secret), **C**=DB Settings
(scope: *srv*=server singleton, *tenant*=per-tenant).

| Option | Bucket | Notes |
|---|---|---|
| `api.host` / `api.port` | **A** | listener bind — needed before anything |
| `api.certFile` / `keyFile` / `chainFile` | **A** | TLS paths needed at bind time |
| `webui.host` / `webui.port` | **A** | CORS / serving — bootstrap |
| `database.host` / `port` / `name` / `user` (→ `registry:`) | **A** | how to reach the registry/bootstrap DB |
| `database.password` | **A→B** | the bootstrap secret; prefer OpenBAO AppRole or a root-owned file, but it is the chicken-and-egg credential — see §3 |
| `logging.level` / `format` | **A** | configured very early (pre-DB) |
| `multitenancy.enabled` | **A** | gates topology; bootstrap |
| `vault.enabled` / `url` / `mount_path` / `timeout` / `verify_ssl` | **A** | how to reach OpenBAO — bootstrap |
| `vault.token` | **B** | read from the root-owned init file (init/unseal), **not** YAML |
| `vault.server.unseal_keys` | **B** | **currently in YAML — must move** to the root-owned `init.json` (already written by `scripts/openbao_init_unseal.py`) |
| `vault.server.*` (config_file/data_path/initialized) | **A/installer** | installer-managed OpenBAO files, not app config |
| `security.password_salt` | **B** | secret |
| `security.jwt_secret` | **B** | secret |
| `security.jwt_algorithm` | **A** | non-secret, needed at token-verify; keep simple |
| `security.admin_userid` | **C (srv)** + seed | seed the admin **user** into the DB at install; drop from YAML |
| `security.admin_password` | **B** | secret; set in OpenBAO at install, used to seed the admin user |
| `security.jwt_auth_timeout` / `jwt_refresh_timeout` | **C (srv)** | runtime-tunable |
| `security.cookie_domain` | **C (srv)** | runtime-tunable |
| `security.password_policy.*` | **C (tenant)** | per-customer policy; Settings → Security |
| `message_queue.*` | **C (srv)** | runtime-tunable |
| `monitoring.heartbeat_timeout` | **C (srv)** | runtime-tunable |
| `email.enabled` | **C (tenant)** | **required to be on** for password flows; per tenant |
| `email.smtp.host` / `port` / `use_tls` / `use_ssl` / `username` / `timeout` | **C (tenant)** | per-customer mail server |
| `email.smtp.password` | **B** | secret, per tenant |
| `email.from_address` / `from_name` / `templates.*` | **C (tenant)** | per-customer branding |
| `license.key` | **B** | treat as secret |
| `license.phone_home_url` / `phone_home_interval_hours` / `modules_path` | **C (srv)** | operational |
| `geo_lookup.maxmind_license_key` | **B** | secret |
| `geo_lookup.*` (enabled, paths, intervals) | **C (srv)** | operational |
| `airgap.*` (signing key paths) | **A** | filesystem paths used early |
| `federation.*` (identity/tls key paths) | **A** | filesystem paths used early |

### Resulting minimal YAML (the target)
```yaml
api:        { host: ..., port: ..., certFile: ..., keyFile: ... }
webui:      { host: ..., port: ... }
registry:   { host: ..., port: ..., name: ..., user: ... }   # + bootstrap secret (§3)
vault:      { enabled: true, url: http://127.0.0.1:8200, mount_path: secret }
logging:    { level: ..., format: ... }
multitenancy: { enabled: false }
# secrets live in OpenBAO; operational/email/policy live in the Settings DB.
```

## 3. The bootstrap chicken-and-egg

The app needs *something* in YAML to reach OpenBAO and the registry DB before it can
read anything from OpenBAO. Decision:

- **OpenBAO**: the app authenticates to the local OpenBAO using material from the
  **root-owned `init.json`** that `openbao_init_unseal.py` writes (`0600`), or an
  **AppRole** whose `role_id` may live in YAML and whose `secret_id` is delivered
  out of band. The raw `vault.token` leaves YAML.
- **Registry/DB password**: once OpenBAO is reachable, the DB password is a secret in
  OpenBAO; YAML keeps only the *pointer* (host/port/name/user). For the very first
  connection, the installer may write a locked-down bootstrap credential or use an
  OpenBAO AppRole — the single permitted on-disk secret, minimized and root-owned.

So the steady state is: **YAML has no passwords**; the only on-disk secret is the
locked-down OpenBAO bootstrap material, and everything else is brokered.

## 4. Where the DB settings live

- **Server-scoped (srv)** → the existing `server_configuration` singleton (extend it).
- **Tenant-scoped (tenant)** → `registry_tenant.settings` JSON already exists
  (Phase 13.1.A), or a dedicated `tenant_setting` table; secrets referenced from
  there resolve through OpenBAO per tenant. In **single-tenant/collapsed** mode there
  is one tenant row, so "tenant-scoped" settings simply live on that single tenant —
  no special case.
- A **Settings → Configuration** UI surfaces these (server tab + per-tenant tab),
  replacing hand-editing YAML.

## 5. Impact on `sysmanage_secure_installation*` (prime the pump)

The installer/secure-installation script must:
1. Ensure OpenBAO is installed, initialized, unsealed (done — §openbao doc).
2. **Generate + store secrets in OpenBAO**: `password_salt`, `jwt_secret`,
   `admin_password`, the DB password — instead of writing them into YAML.
3. **Seed the admin user** into the DB (userid from prompt/default) with its password
   referenced from OpenBAO.
4. Write the **minimal YAML** (§2) — pointers only, no secrets.
5. Seed **sane default DB settings** (password policy, timeouts, message-queue,
   monitoring) so a fresh instance is functional without UI work.
6. **Dev vs production**: dev (`make install-dev`) primes OpenBAO with generated dev
   secrets + a dev admin; production bootstraps from the binary package with the same
   flow and secure/sane defaults (no interactive secret entry required — generated +
   stored in OpenBAO, surfaced once for the operator to record).

## 6. Impact on the config builder (`sysmanage-docs`)

The web config builder (`config-builder.html`) must be reduced to the **minimal YAML**
surface (§2): it should stop emitting secrets and operational/email blocks, and
instead explain that secrets are generated into OpenBAO at install and that email /
policy / timeouts are configured in **Settings** after first login. i18n the new
copy. (Ties into ROADMAP 13.1.G.)

## 7. Work phasing (proposed)

1. **Settings tables + UI** — extend `server_configuration` (srv) and add tenant
   settings surfacing; migrate the C-bucket options with YAML-fallback during
   transition.
2. **Secrets → OpenBAO** — a secrets accessor that reads B-bucket values from OpenBAO
   (with a one-release YAML fallback + deprecation warning), plus the init seeding.
3. **secure_installation rewrite** — §5.
4. **Config builder + docs** — §6.
5. **Remove YAML fallbacks** in a later major once migrated.

Each step is independently shippable and backwards-compatible (YAML continues to work
with deprecation warnings until the final cleanup).
