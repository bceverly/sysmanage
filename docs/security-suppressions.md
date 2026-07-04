# Security-scan suppressions & false-positive rationale

This records every **intentional** suppression of a CodeQL / Semgrep / Bandit
finding, with the reason it is safe. Scanner findings that were *fixed in code*
(rather than suppressed) are noted too, so a reviewer can audit the whole batch.

> Note on tooling: `# nosemgrep` suppresses **Semgrep only**; `# nosec`
> suppresses **Bandit only**. **CodeQL ignores both** — a CodeQL finding can
> only be cleared by a code change that breaks the taint/flow, by dismissing it
> in the GitHub Security UI, or via a `.github/codeql/codeql-config.yml` filter.

## Fixed in code (not suppressed)

| Finding | Files | Fix |
| --- | --- | --- |
| CodeQL **log injection** (CWE-117) | `api/control_plane.py`, `services/tenant_provisioning.py`, `persistence/tenant_engine.py`, `config/settings_service.py` | Request-derived values (tenant id, setting key) are passed through `backend/utils/log_sanitize.py::scrub()` before logging — strips CR/LF so a hostile value can't forge log lines. |
| CodeQL **clear-text logging of sensitive info** (High) | `config/secrets_service.py` (YAML-fallback path) | Restructured to log only the exception *type* (never `str(exc)`, which could embed a secret) and to make the deprecation warning **key-agnostic** (the secret name is treated as sensitive, so it's no longer interpolated). |
| CodeQL **empty except** | `persistence/tenant_context.py`, `tests/test_alembic_prefix_guard.py` | Added an explanatory comment documenting why the exception is intentionally ignored (benign stale-token reset / best-effort temp-file unlink). |

## Suppressed false positives

| Finding | Location | Why it's safe |
| --- | --- | --- |
| Semgrep `sqlalchemy-execute-raw-query` | `services/tenant_orchestration.py` (create/drop role+db), `scripts/provision_bootstrap.py` | **psycopg**, not SQLAlchemy (rule mis-targets). Every identifier goes through `psycopg.sql.Identifier()` (injection-safe quoting); values are `%s` bind params. DDL (CREATE/DROP ROLE/DATABASE, GRANT) cannot parameterize identifiers, so this is the correct construct. |
| Semgrep `dynamic-urllib-use-detected` | `scripts/provision_bootstrap.py` | URL is the operator-configured OpenBAO address (trusted config, not user input). Operator-run bootstrap CLI — no SSRF surface. |
| Semgrep `logger-credential-leak` | `persistence/tenant_engine.py`, `scripts/openbao_init_unseal.py` | The log lines emit a tenant id / TTL / filesystem error only — never the leased credential or token value. |
| Bandit `B608` (hardcoded SQL) | `scripts/provision_bootstrap.py` (peer-auth SQL-file emit) | Pre-existing. The role identifier is regex-validated (`^[a-z_][a-z0-9_]*$`), the password is URL-safe (no quotes), and the file is written 0600 and applied by the operator themselves — not a runtime query. |
