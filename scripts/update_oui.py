#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Regenerate the bundled MAC vendor table from the IEEE registries (21.6 S5).

Unenrolled asset discovery names the maker behind each MAC address. The
lookup must work on an AIR-GAPPED server, so the table ships with the server
(``backend/data/oui.tsv.gz``) instead of being fetched at runtime. Run this
when you want a fresher table; the output is deterministic (sorted, gzip
mtime 0), so an unchanged registry produces a byte-identical file.

Sources (public IEEE Registration Authority listings):
  MA-L  https://standards-oui.ieee.org/oui/oui.csv      24-bit prefixes
  MA-M  https://standards-oui.ieee.org/oui28/mam.csv    28-bit prefixes
  MA-S  https://standards-oui.ieee.org/oui36/oui36.csv  36-bit prefixes

Output: one ``PREFIX<TAB>Vendor`` line per assignment, PREFIX being 6, 7 or
9 upper-case hex digits; a ``#`` header line names the sources and the date.

Usage: python3 scripts/update_oui.py [--from-dir DIR]   (DIR holds the 3 CSVs)
"""

import argparse
import csv
import gzip
import io
import os
import sys
import urllib.request
from datetime import datetime, timezone

SOURCES = {
    "oui.csv": "https://standards-oui.ieee.org/oui/oui.csv",
    "mam.csv": "https://standards-oui.ieee.org/oui28/mam.csv",
    "oui36.csv": "https://standards-oui.ieee.org/oui36/oui36.csv",
}
OUT = os.path.join(
    os.path.dirname(__file__), "..", "backend", "data", "oui.tsv.gz"
)
MAX_VENDOR = 64


def _fetch(name: str, from_dir) -> str:
    if from_dir:
        with open(os.path.join(from_dir, name), encoding="utf-8") as fh:
            return fh.read()
    request = urllib.request.Request(
        SOURCES[name], headers={"User-Agent": "Mozilla/5.0 sysmanage-oui-update"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
        return response.read().decode("utf-8", "replace")


def _vendor(name: str) -> str:
    return " ".join(name.split())[:MAX_VENDOR].strip()


def build(from_dir=None):
    table = {}
    for name in SOURCES:
        for row in csv.DictReader(io.StringIO(_fetch(name, from_dir))):
            prefix = (row.get("Assignment") or "").strip().upper()
            vendor = _vendor(row.get("Organization Name") or "")
            if prefix and vendor and all(c in "0123456789ABCDEF" for c in prefix):
                table[prefix] = vendor
    return table


def write(table, path=OUT) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# IEEE MA-L/MA-M/MA-S registries, {stamp}, {len(table)} assignments"]
    lines += [f"{prefix}\t{table[prefix]}" for prefix in sorted(table)]
    data = ("\n".join(lines) + "\n").encode("utf-8")
    with open(path, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
            gz.write(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-dir", help="read the three CSVs from here instead")
    args = parser.parse_args()
    table = build(args.from_dir)
    if len(table) < 30000:
        print(f"refusing to write: only {len(table)} assignments parsed", file=sys.stderr)
        return 1
    write(table)
    print(f"wrote {len(table)} assignments to {os.path.normpath(OUT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
