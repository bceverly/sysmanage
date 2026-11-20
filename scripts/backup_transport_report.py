#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""NFS against restate-proxy, from the server's own backup history.

ROADMAP 27.8 (step 0 of Phase 27's sequence): whether SysManage can drop its
NFS transport is decided on numbers, including "a month of nightly runs on
production with no failed night the proxy caused".  Every capture already
records where its repository was -- an ``https://`` restate-proxy URL or an
NFS path -- with its seconds and bytes, so the comparison is in
``backup_run`` already.  This reads it (read-only, every database the server
serves) and prints, per transport: captures, failures, median seconds and
read throughput; per host: the first night through the proxy; and the
nights since the first proxy capture, with any failed proxy capture listed
so its cause can be judged.

    sudo -u sysmanage env SYSMANAGE_CONFIG=/etc/sysmanage.yaml \\
        /opt/sysmanage/.venv/bin/python scripts/backup_transport_report.py \\
        [--since 2026-10-25] [--json] [--database-url URL]
"""

import argparse
import json
import statistics
import sys
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

PROXY, NFS = "proxy", "nfs"


def transport_of(result: Dict[str, Any]) -> Optional[str]:
    """Where a capture's repository was: restate-proxy or NFS (None when the
    result does not say)."""
    repository = result.get("repository") or ""
    if not repository:
        return None
    return PROXY if repository.startswith(("https://", "http://")) else NFS


def _row(fqdn: str, status: str, queued_at: datetime, raw: Optional[str],
         message: Optional[str] = None):  # fmt: skip
    try:
        result = json.loads(raw) if raw else {}
    except ValueError:
        result = {}
    seconds = result.get("seconds")
    read = result.get("read_bytes") or 0
    return {
        "host": fqdn,
        "night": queued_at.date(),
        "status": status,
        "transport": transport_of(result),
        "seconds": seconds if isinstance(seconds, (int, float)) else None,
        "read_bytes": read if isinstance(read, int) else 0,
        "new_bytes": result.get("new_bytes") or 0,
        "message": (message or result.get("error") or result.get("message") or "")[
            :200
        ],
    }


def summarize(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """The comparison from capture rows (see :func:`_row`)."""
    rows = [r for r in rows if r["transport"]]
    by_transport: Dict[str, Any] = {}
    for transport in (NFS, PROXY):
        mine = [r for r in rows if r["transport"] == transport]
        good = [r for r in mine if r["status"] == "ok" and r["seconds"]]
        rates = [r["read_bytes"] / r["seconds"] / 1e6 for r in good if r["seconds"]]
        by_transport[transport] = {
            "captures": len(mine),
            # A failed capture may be the transport's doing; an incomplete one
            # finished but could not read a file or pause a service -- the
            # host's business, whatever the transport.
            "failed": sum(1 for r in mine if r["status"] == "failed"),
            "incomplete": sum(1 for r in mine if r["status"] == "incomplete"),
            "median_seconds": statistics.median([r["seconds"] for r in good]) if good else None,
            "median_read_mb_s": round(statistics.median(rates), 1) if rates else None,
        }  # fmt: skip
    first_proxy: Dict[str, date] = {}
    for r in sorted(rows, key=lambda r: r["night"]):
        if r["transport"] == PROXY:
            first_proxy.setdefault(r["host"], r["night"])
    proxy_nights = sorted({r["night"] for r in rows if r["transport"] == PROXY})
    failed_proxy = [
        {"host": r["host"], "night": r["night"].isoformat(), "message": r["message"]}
        for r in rows
        if r["transport"] == PROXY and r["status"] == "failed"
    ]
    return {
        "by_transport": by_transport,
        "first_proxy_night": {h: d.isoformat() for h, d in sorted(first_proxy.items())},
        "proxy_nights": len(proxy_nights),
        "proxy_since": proxy_nights[0].isoformat() if proxy_nights else None,
        "failed_proxy_captures": failed_proxy,
    }


_CAPTURES_SQL = """
    SELECT h.fqdn, r.status, r.queued_at, r.result, r.message
    FROM backup_run r
    JOIN backup_policy p ON p.id = r.policy_id
    JOIN host h ON h.id = p.host_id
    WHERE r.action = 'capture' AND r.status IN ('ok', 'failed', 'incomplete')
      AND r.queued_at >= :since
"""


def _sessions(url: Optional[str]):
    """A session on every database the server serves, or on just ``url``
    (one tenant's database read directly: a multi-tenant server reaches its
    tenants only through the licensed engine, and this needs no server
    configuration at all)."""
    # pylint: disable=import-outside-toplevel
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    if url:
        yield Session(create_engine(url))
        return
    from backend.persistence.partitions import iter_host_databases

    for _label, _tenant, db in iter_host_databases():
        yield db


def _captures(since: Optional[date], url: Optional[str] = None) -> List[Dict[str, Any]]:
    from sqlalchemy import text  # pylint: disable=import-outside-toplevel

    rows: List[Dict[str, Any]] = []
    for db in _sessions(url):
        try:
            for fqdn, status, queued_at, result, message in db.execute(
                text(_CAPTURES_SQL), {"since": since or date(2000, 1, 1)}
            ):
                rows.append(_row(fqdn, status, queued_at, result, message))
        finally:
            db.close()
    return rows


def _print(report: Dict[str, Any]) -> None:
    for transport, numbers in report["by_transport"].items():
        print(
            f"{transport:5}  captures {numbers['captures']:4}  failed {numbers['failed']:3}  "
            f"incomplete {numbers['incomplete']:3}  "
            f"median {numbers['median_seconds']} s  read {numbers['median_read_mb_s']} MB/s"
        )
    print(f"proxy nights: {report['proxy_nights']} since {report['proxy_since']}")
    for host, night in report["first_proxy_night"].items():
        print(f"  {host}: first through the proxy {night}")
    failed = report["failed_proxy_captures"]
    print(f"failed captures through the proxy (judge each): {len(failed)}")
    for row in failed:
        print(f"  {row['night']} {row['host']}: {row['message']}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--since", type=date.fromisoformat, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--database-url", help="read this one database (e.g. a tenant's) directly"
    )
    args = parser.parse_args(argv)
    report = summarize(_captures(args.since, args.database_url))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
