#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
migrate-tenant-data — relocate per-tenant rows from the bootstrap database into
each tenant's database (Phase 13.1 data plane).

Idempotent: run it repeatedly as each object is routed to the tenant partition.
Rows whose host isn't assigned to a tenant are left in place.  No-op when
multi-tenancy is disabled.

Usage:
  migrate-tenant-data                 # dry run: show what WOULD move
  migrate-tenant-data --apply         # copy rows into tenant DBs (safe; leaves source)
  migrate-tenant-data --apply --delete-source   # ...and remove moved rows from the bootstrap DB
  migrate-tenant-data --verify        # show rows REMAINING in the bootstrap DB (drop readiness)

OpenBAO must be running (per-tenant DBs are reached via leased credentials).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services import tenant_data_mover  # noqa: E402


def _print_move(report) -> int:
    if not report.get("_enabled", False):
        print("Multi-tenancy disabled — nothing to move (single database).")
        return 0
    failures = 0
    for name, r in report.items():
        if name == "_enabled":
            continue
        print(
            f"  {name}: moved={r['moved']} "
            f"already-present={r['skipped_present']} "
            f"unassigned(left in place)={r['skipped_unassigned']} "
            f"errors={r['errors']}"
        )
        failures += r["errors"]
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Actually copy rows (default: dry run)."
    )
    parser.add_argument(
        "--delete-source",
        action="store_true",
        help="With --apply, remove moved rows from the bootstrap DB.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Report rows remaining in the bootstrap DB (drop readiness).",
    )
    args = parser.parse_args(argv)

    if args.verify:
        status = tenant_data_mover.verify_source_drained()
        print("=== Bootstrap DB drain status (per domain) ===")
        ready = True
        for name, s in status.items():
            placeable = s["remaining"] - s["unassigned"]
            state = "DRAINED" if placeable == 0 else "PENDING"
            if placeable != 0:
                ready = False
            print(
                f"  {name}: remaining={s['remaining']} "
                f"(unassigned={s['unassigned']}, still-to-move={placeable}) [{state}]"
            )
        print(
            "\n[OK] All assigned rows have been moved — safe to drop legacy tables."
            if ready
            else "\n[WAIT] Some assigned rows still live in the bootstrap DB."
        )
        return 0

    mode = (
        "dry run (no changes)"
        if not args.apply
        else ("move (copy + delete source)" if args.delete_source else "copy")
    )
    print(f"=== Migrating tenant data — {mode} ===")
    report = tenant_data_mover.move_all(
        apply=args.apply, delete_source=args.delete_source
    )
    return _print_move(report)


if __name__ == "__main__":
    sys.exit(main())
