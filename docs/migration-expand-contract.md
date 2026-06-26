# Database migrations must be expand-contract (Phase 13.1)

SysManage migrates a **fleet of databases incrementally**, not one database
atomically:

1. the registry chain (control plane),
2. the shared chain (reference data),
3. the tenant chain against the bootstrap database, then
4. the tenant chain against **every tenant database, one at a time** (the
   `sysmanage-migrate` fan-out).

There are two windows where the **running server code executes against an
old schema**:

- between "new package installed" and "operator ran `sysmanage-migrate`", and
- **during the per-tenant fan-out itself** — tenant A is migrated, tenant B is
  not yet, and the same server process serves both.

Therefore every migration must be **backward-compatible (expand-contract)**:

- **Expand (this release):** add tables/columns/indexes; make new columns
  nullable or defaulted; backfill; start writing to the new shape while still
  reading the old. New code must work against the *old* schema, and old-enough
  code must tolerate the *new* schema.
- **Contract (a LATER release):** once every database in every fleet is past
  the expand, drop the old column/table or finish the rename.

### Don't, in a single release
- `DROP TABLE` / `DROP COLUMN` / `DROP CONSTRAINT` of something current code uses.
- Rename a table or column (`ALTER ... RENAME`, `op.alter_column(new_column_name=...)`)
  — that's a drop+add in disguise. Add the new name, dual-write, switch reads,
  drop the old name a release later.
- Add a `NOT NULL` column without a default (old rows / old code break).
- Narrow a type or tighten a constraint that existing data/code may violate.

### Do
- Additive DDL only in the expand release.
- Reversible, idempotent migrations (we already require SQLite + PostgreSQL parity).
- Split a rename across two releases (expand: add + dual-write; contract: drop).

## Enforcement

`scripts/check_migrations.py` scans every migration's `upgrade()` for
destructive DDL and fails CI if it finds any (`make check-migrations`, part of
`make lint`). `downgrade()` is exempt.

If a drop is the **intentional contract step** (a release after the add, when
the whole fleet is past it), annotate the line:

```python
# expand-contract-ok: dropping legacy_col, added + dual-written in v3.1, fleet is past it
op.drop_column("widget", "legacy_col")
```
