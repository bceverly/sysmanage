# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""NFS against restate-proxy from the server's backup history (27.8)."""

import json
from datetime import datetime

from scripts import backup_transport_report as report


def _row(host, night, transport, status="ok", seconds=100, read=200_000_000):
    repository = ("https://backup.example:8443/v1/x" if transport == "proxy"
                  else "/mnt/backups/x")  # fmt: skip
    result = {"repository": repository, "seconds": seconds, "read_bytes": read}
    if status != "ok":
        result["error"] = "connection reset"
    return report._row(  # pylint: disable=protected-access
        host, status, datetime.fromisoformat(f"{night}T03:00:00"), json.dumps(result)
    )


def test_transport_comes_from_the_repository():
    assert report.transport_of({"repository": "https://b:8443/v1/r"}) == "proxy"
    assert report.transport_of({"repository": "/mnt/backups/web-1"}) == "nfs"
    assert report.transport_of({}) is None


def test_the_comparison():
    rows = [
        _row("web", "2026-11-01", "nfs", seconds=100),
        _row("web", "2026-11-02", "nfs", seconds=120),
        _row("web", "2026-11-03", "proxy", seconds=110),
        _row("db", "2026-11-04", "proxy", seconds=50, read=500_000_000),
        _row("db", "2026-11-05", "proxy", status="failed", seconds=None),
        _row("db", "2026-11-06", "proxy", status="incomplete", seconds=60),
    ]
    out = report.summarize(rows)
    assert out["by_transport"]["nfs"] == {"captures": 2, "failed": 0, "incomplete": 0,
                                          "median_seconds": 110.0, "median_read_mb_s": 1.8}  # fmt: skip
    assert out["by_transport"]["proxy"]["captures"] == 4
    assert out["by_transport"]["proxy"]["failed"] == 1
    assert out["by_transport"]["proxy"]["incomplete"] == 1
    assert out["first_proxy_night"] == {"db": "2026-11-04", "web": "2026-11-03"}
    assert out["proxy_nights"] == 4 and out["proxy_since"] == "2026-11-03"
    assert out["failed_proxy_captures"] == [
        {"host": "db", "night": "2026-11-05", "message": "connection reset"}
    ]


def test_a_result_that_says_nothing_is_left_out():
    row = report._row(
        "x", "ok", datetime(2026, 11, 1), "not json"
    )  # pylint: disable=protected-access
    assert report.summarize([row])["by_transport"]["nfs"]["captures"] == 0
