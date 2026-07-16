#!/usr/bin/env bash
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# dump-codeql-alerts.sh — paginate the GitHub Code Scanning API
# and dump every open CodeQL alert on bceverly/sysmanage into a
# single JSON array file.
#
# Usage:
#   GITHUB_TOKEN=<pat> ./scripts/dump-codeql-alerts.sh
#
# Optional env:
#   REPO=bceverly/sysmanage   (default; override to dump a different repo)
#   STATE=open                (default; ``open`` | ``closed`` | ``dismissed`` | ``fixed``)
#   OUT=/tmp/codeql-alerts.json   (default output path)
#
# PAT scope required:
#   * Classic PAT:        ``security_events``  (or ``repo`` for private repos)
#   * Fine-grained PAT:   Repository → "Code scanning alerts: Read"

set -euo pipefail

REPO="${REPO:-bceverly/sysmanage}"
STATE="${STATE:-open}"
OUT="${OUT:-/tmp/codeql-alerts.json}"

if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "ERROR: GITHUB_TOKEN is not set." >&2
    echo "       export GITHUB_TOKEN=<pat-with-security_events-scope>" >&2
    exit 1
fi

echo "Repo:  ${REPO}"
echo "State: ${STATE}"
echo "Out:   ${OUT}"
echo

TMPDIR_LOCAL="$(mktemp -d -t codeql-dump.XXXXXX)"
trap 'rm -rf "${TMPDIR_LOCAL}"' EXIT

page=1
total=0
while :; do
    page_file="${TMPDIR_LOCAL}/page-${page}.json"
    echo -n "  page ${page}... "
    http_code="$(curl -sS \
        -o "${page_file}" \
        -w '%{http_code}' \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "https://api.github.com/repos/${REPO}/code-scanning/alerts?state=${STATE}&per_page=100&page=${page}")"

    case "${http_code}" in
        200) ;;
        401)
            echo "FAIL (401 Unauthorized)"
            echo "       Check that GITHUB_TOKEN is valid." >&2
            cat "${page_file}" >&2
            exit 1
            ;;
        403)
            echo "FAIL (403 Forbidden)"
            echo "       PAT likely lacks 'security_events' scope." >&2
            cat "${page_file}" >&2
            exit 1
            ;;
        404)
            echo "FAIL (404 Not Found)"
            echo "       Repo ${REPO} not found, or PAT can't see it." >&2
            cat "${page_file}" >&2
            exit 1
            ;;
        *)
            echo "FAIL (HTTP ${http_code})"
            cat "${page_file}" >&2
            exit 1
            ;;
    esac

    count="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "${page_file}")"
    echo "${count} alerts"
    total=$((total + count))

    if [ "${count}" -lt 100 ]; then
        # Last page (or empty page).  Stop paginating.
        break
    fi
    page=$((page + 1))
done

# Concatenate all per-page arrays into one big array via Python — way
# easier than wrangling brackets/commas in shell.  No stdout redirect
# here: the python script writes to OUT itself.  An earlier version of
# this used both ``python3 ... > OUT`` and ``json.dump(..., open(OUT))``,
# which sent ``print()`` into the same file as the JSON and corrupted
# the start of the array.  Lesson: pick one writer.
python3 - <<EOF
import json, glob, os, re
tmpdir = "${TMPDIR_LOCAL}"
out = "${OUT}"
alerts = []
files = sorted(
    glob.glob(os.path.join(tmpdir, "page-*.json")),
    key=lambda p: int(re.search(r"page-(\d+)\.json", p).group(1)),
)
for f in files:
    with open(f) as fh:
        alerts.extend(json.load(fh))
with open(out, "w") as fh:
    json.dump(alerts, fh, indent=2)
print(f"Wrote {len(alerts)} alerts to {out}")
EOF

echo
echo "Done."
echo

# Print a quick breakdown by rule and severity so the operator
# sees the shape of the alert population without having to write
# their own jq.
python3 - <<EOF
import json
from collections import Counter

alerts = json.load(open("${OUT}"))
by_rule = Counter()
by_severity = Counter()
by_file = Counter()
for a in alerts:
    rule = a.get("rule", {}).get("id") or a.get("rule", {}).get("name") or "<no-rule>"
    sev = a.get("rule", {}).get("severity") or a.get("rule", {}).get("security_severity_level") or "?"
    loc = a.get("most_recent_instance", {}).get("location", {})
    path = loc.get("path", "<no-path>")
    by_rule[rule] += 1
    by_severity[sev] += 1
    by_file[path] += 1

print(f"Total: {len(alerts)} alerts")
print()
print("=== By severity ===")
for sev, n in by_severity.most_common():
    print(f"  {sev:12s}  {n:5d}")
print()
print("=== By rule (top 15) ===")
for rule, n in by_rule.most_common(15):
    print(f"  {n:5d}  {rule}")
print()
print("=== By file (top 15) ===")
for path, n in by_file.most_common(15):
    print(f"  {n:5d}  {path}")
EOF
