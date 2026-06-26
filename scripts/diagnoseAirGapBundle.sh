#!/usr/bin/env bash
#
# diagnoseAirGapBundle.sh — one-shot diagnostics for air-gap bundle build
# failures (hollow ISOs, exit 127, per-platform failures).
#
# Run on the build host (e.g. sysmanage-online) as root:
#     sudo bash diagnoseAirGapBundle.sh
#
# READ-ONLY.  It inspects the deployed build script, the tools on PATH
# (root AND the sysmanage service user, since the backend runs builds as
# 'sysmanage'), and — the important part — the PER-PLATFORM output of the
# most recent server/agent builds.  Nothing is modified.

set -uo pipefail

SCRIPT=/opt/sysmanage/scripts/buildAirGapBundle.sh
LOGDIR=/var/lib/sysmanage/airgap-bundles
BUILD_USER=sysmanage

hr() { printf '\n========== %s ==========\n' "$1"; }

# ---------------------------------------------------------------------------
hr "DEPLOYED BUILD SCRIPT"
if [[ -f "$SCRIPT" ]]; then
  ls -l "$SCRIPT"
  echo "sha256: $(sha256sum "$SCRIPT" 2>/dev/null | cut -d' ' -f1)"
  printf 'markers: rpmqpR=%s py312=%s reqfallback=%s strict=%s preflight=%s\n' \
    "$(grep -c 'rpm -qpR' "$SCRIPT")" \
    "$(grep -c 'python3.12 -m pip' "$SCRIPT")" \
    "$(grep -c 'requirements.txt\" -o \"\$REQ\"' "$SCRIPT")" \
    "$(grep -c 'FAILED Linux' "$SCRIPT")" \
    "$(grep -c 'preflight_resources' "$SCRIPT")"
else
  echo "MISSING: $SCRIPT"
fi

# ---------------------------------------------------------------------------
hr "TOOLS"
printf 'root : '
for t in docker xorrisofs jq curl awk df rpm2cpio; do
  command -v "$t" >/dev/null 2>&1 && printf '%s ' "$t" || printf '%s=MISSING ' "$t"
done; echo
if id "$BUILD_USER" >/dev/null 2>&1; then
  printf '%s : ' "$BUILD_USER"
  for t in docker xorrisofs jq curl awk df; do
    sudo -u "$BUILD_USER" bash -lc "command -v $t" >/dev/null 2>&1 \
      && printf '%s ' "$t" || printf '%s=MISSING ' "$t"
  done; echo
  echo "$BUILD_USER docker daemon reachable: $(sudo -u "$BUILD_USER" docker info >/dev/null 2>&1 && echo YES || echo NO)"
fi

# ---------------------------------------------------------------------------
# For a given product, dump the NEWEST build log with the per-platform
# results.  The "[<platform>] done — N deps + M wheels" lines are the
# smoking gun: a platform reporting "0 deps + 0 wheels" succeeded but is
# EMPTY, which is what makes a bundle hollow even though the build "passes".
_dump_build() {  # $1 = product (server|agent)
  local prod="$1" log
  log=$(grep -l "Product   : $prod" "$LOGDIR"/*.log 2>/dev/null | xargs -r ls -t 2>/dev/null | head -1)
  hr "NEWEST ${prod^^} BUILD"
  if [[ -z "$log" ]]; then
    echo "no $prod build log found in $LOGDIR"
    return
  fi
  echo "log: $log"
  echo "when: $(stat -c '%y' "$log" 2>/dev/null)"
  echo
  echo "--- per-platform output (look for '0 deps + 0 wheels' = empty/hollow) ---"
  grep -E "docker run .* to fetch|\] done —|no installer|\] .*failed — skipping" "$log"
  echo
  echo "--- summary / result ---"
  grep -E "succeeded |FAILED Linux|no installer|Linux platform.*failed|Staging tree|ISO :|exited|no platforms produced" "$log"
  echo
  echo "--- errors / abort cause ---"
  grep -nE "command not found|: 127|Unknown argument|No package|could not obtain|No matching distribution|No space|ERROR|Traceback|\[ERROR\]" "$log" | tail -25
}

_dump_build server
_dump_build agent

# ---------------------------------------------------------------------------
hr "PRESERVED PER-PLATFORM FAILURE LOGS (if any)"
for prod in server agent; do
  d="$LOGDIR/sysmanage-${prod}-bundle-logs"
  [[ -d "$d" ]] || continue
  shopt -s nullglob
  for f in "$d"/*.log; do
    echo "### ${prod}/$(basename "$f")  (mtime $(stat -c '%y' "$f" 2>/dev/null | cut -d. -f1))"
    tail -15 "$f"; echo
  done
  shopt -u nullglob
done

hr "DONE — paste this entire output back"
