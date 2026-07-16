#!/usr/bin/env bash
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# diagnose-host-tenant.sh — Reconcile a host's tenant binding (Phase 13.1).
#
# In multi-tenancy a host has TWO independent facts that must agree:
#
#   1. The host→tenant INDEX  (registry_host_tenant in the registry/bootstrap
#      DB) — what BACKGROUND dispatch (schedulers, the queue processors) trusts
#      to decide which tenant database to route a host's messages to.
#   2. The host DATA location  (the ``host`` row + all host-scoped data) — which
#      tenant database the row actually lives in.  The UI reads this via the
#      request's active tenant.
#
# Manual test setup (moving rows, re-issuing tokens) can leave these
# DISAGREEING — the index says tenant A while the data is in tenant B.  The UI
# still works (it follows the active tenant), but background dispatch routes to
# the wrong DB.  This script reports both facts and, when they disagree, prints
# the exact SQL to reconcile them (it makes NO changes itself — you review + run).
#
# Usage:
#   scripts/diagnose-host-tenant.sh <host_id>
#
# Requires: sudo access to run psql as the ``postgres`` superuser (the tenant
# tables are owned by per-tenant roles, so a normal login can't read them).

set -euo pipefail

HOST_ID="${1:-}"
REGISTRY_DB="${REGISTRY_DB:-sysmanage}"

if [[ -z "$HOST_ID" ]]; then
  echo "usage: $0 <host_id>" >&2
  exit 2
fi

# psql as the postgres superuser (peer auth).  -tA = tuples-only, unaligned.
pg() { sudo -u postgres psql -tAqc "$2" -d "$1"; }

# ---------------------------------------------------------------------------
# 1. The index binding (registry/bootstrap DB)
# ---------------------------------------------------------------------------
echo "=== host→tenant INDEX (registry_host_tenant in $REGISTRY_DB) ==="
index_row="$(pg "$REGISTRY_DB" "
  SELECT t.slug || '|' || t.id
  FROM registry_host_tenant rht
  JOIN registry_tenant t ON t.id = rht.tenant_id
  WHERE rht.host_id = '$HOST_ID';" || true)"

if [[ -z "$index_row" ]]; then
  echo "  (no binding — the host is NOT in the index; background dispatch will"
  echo "   treat it as server-scoped / unrouted)"
  index_slug=""
  index_tid=""
else
  index_slug="${index_row%%|*}"
  index_tid="${index_row##*|}"
  echo "  index says: tenant '$index_slug'  ($index_tid)"
fi
echo

# ---------------------------------------------------------------------------
# 2. Where the host DATA actually lives — scan every provisioned tenant DB
# ---------------------------------------------------------------------------
echo "=== host DATA location (scanning every provisioned tenant database) ==="
# tenant slug | tenant id | database name, one per line
placements="$(pg "$REGISTRY_DB" "
  SELECT t.slug || '|' || t.id || '|' || p.database_name
  FROM registry_tenant_placement p
  JOIN registry_tenant t ON t.id = p.tenant_id
  ORDER BY t.slug;")"

found_in=()    # "slug|tid|db" for each tenant DB that has the host
while IFS='|' read -r slug tid dbname; do
  [[ -z "$dbname" ]] && continue
  hit="$(pg "$dbname" "SELECT fqdn FROM host WHERE id = '$HOST_ID';" 2>/dev/null || true)"
  if [[ -n "$hit" ]]; then
    echo "  FOUND in tenant '$slug'  (db=$dbname)  fqdn=$hit"
    found_in+=("$slug|$tid|$dbname")
  else
    echo "  not in tenant '$slug'  (db=$dbname)"
  fi
done <<< "$placements"

# Also check the bootstrap/registry DB itself (collapsed/unbound data).
boot_hit="$(pg "$REGISTRY_DB" "SELECT fqdn FROM host WHERE id = '$HOST_ID';" 2>/dev/null || true)"
[[ -n "$boot_hit" ]] && echo "  ALSO in the bootstrap DB '$REGISTRY_DB'  fqdn=$boot_hit  (stray/legacy row)"
echo

# ---------------------------------------------------------------------------
# 3. Verdict + reconciliation SQL
# ---------------------------------------------------------------------------
echo "=== verdict ==="
if (( ${#found_in[@]} == 0 )); then
  echo "  The host's data was found in NO tenant database."
  echo "  Either it lives in the bootstrap DB (single-tenant / not yet bound), or"
  echo "  it was deleted.  Nothing to reconcile against — re-register the host via"
  echo "  its tenant enrollment token to establish a clean binding + data."
  exit 0
fi

if (( ${#found_in[@]} > 1 )); then
  echo "  ⚠ The host's data exists in MORE THAN ONE tenant database (duplicate)."
  echo "  Decide which tenant owns it, then DELETE the row (and its host-scoped"
  echo "  data) from the other tenant DB(s).  Keep the one matching your intent."
  echo
fi

# Use the first (or only) data location as the authority.
IFS='|' read -r data_slug data_tid data_db <<< "${found_in[0]}"

if [[ "$index_tid" == "$data_tid" && ${#found_in[@]} -eq 1 ]]; then
  echo "  ✅ CONSISTENT — the index and the host data both point at tenant"
  echo "     '$data_slug'.  No reconciliation needed."
  exit 0
fi

echo "  ✗ INCONSISTENT:"
echo "      index  → '${index_slug:-<none>}' (${index_tid:-none})"
echo "      data   → '$data_slug' ($data_tid, db=$data_db)"
echo
echo "  Recommended fix: point the index at where the data actually lives."
echo "  Review, then run as the postgres superuser:"
echo
if [[ -z "$index_tid" ]]; then
  echo "    sudo -u postgres psql -d $REGISTRY_DB -c \\"
  echo "      \"INSERT INTO registry_host_tenant (id, host_id, tenant_id, created_at)"
  echo "       VALUES (gen_random_uuid(), '$HOST_ID', '$data_tid', now());\""
else
  echo "    sudo -u postgres psql -d $REGISTRY_DB -c \\"
  echo "      \"UPDATE registry_host_tenant SET tenant_id='$data_tid'"
  echo "       WHERE host_id='$HOST_ID';\""
fi
echo
echo "  (Alternatively, if the host SHOULD belong to '${index_slug:-the indexed tenant}',"
echo "   move the data instead — cleanest is to delete + re-register via that"
echo "   tenant's enrollment token so the flow writes data + index together.)"
