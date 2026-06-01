#!/usr/bin/env bash
#
# diagnoseAirGapBundle.sh — one-shot diagnostics for air-gap bundle build
# failures (hollow ISOs, exit 127, per-platform failures).
#
# Run on the build host (e.g. sysmanage-online) as root:
#     sudo bash diagnoseAirGapBundle.sh
#
# It is READ-ONLY: it inspects the deployed build script, the tools on
# PATH (both root's and the sysmanage service user's, since the backend
# runs the build as 'sysmanage'), and the most recent server/agent build
# logs.  Nothing is modified.

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
  echo
  echo "Fix markers (each should be >= 1 if the up-to-date script is deployed):"
  printf '  dnf5 download fix (rpm -qpR)     : %s\n' "$(grep -c 'rpm -qpR' "$SCRIPT")"
  printf '  rhel python3.12 wheels           : %s\n' "$(grep -c 'python3.12 -m pip' "$SCRIPT")"
  printf '  requirements.txt fallback        : %s\n' "$(grep -c 'requirements.txt\" -o \"\$REQ\"' "$SCRIPT")"
  printf '  strict per-platform summary      : %s\n' "$(grep -c 'FAILED Linux' "$SCRIPT")"
  printf '  resource preflight               : %s\n' "$(grep -c 'preflight_resources' "$SCRIPT")"
  echo
  echo ">> If any marker above is 0, the host has a STALE script -> re-deploy it."
else
  echo "MISSING: $SCRIPT does not exist."
fi

# ---------------------------------------------------------------------------
hr "TOOLS ON PATH"
echo "As root:"
for t in docker xorrisofs jq curl awk df rpm2cpio; do
  printf '  %-10s: %s\n' "$t" "$(command -v "$t" 2>/dev/null || echo MISSING)"
done
echo
echo "As the build user ($BUILD_USER) — this is who the backend actually runs the build as:"
if id "$BUILD_USER" >/dev/null 2>&1; then
  for t in docker xorrisofs jq curl awk df; do
    path=$(sudo -u "$BUILD_USER" bash -lc "command -v $t" 2>/dev/null || echo MISSING)
    printf '  %-10s: %s\n' "$t" "${path:-MISSING}"
  done
  echo
  echo "  $BUILD_USER can reach docker daemon? : $(sudo -u "$BUILD_USER" docker info >/dev/null 2>&1 && echo YES || echo NO)"
else
  echo "  user '$BUILD_USER' not found on this host"
fi
echo
echo ">> Any MISSING above (especially for $BUILD_USER) is the likely cause of exit 127."

# ---------------------------------------------------------------------------
_newest_log_for() {  # $1 = product (server|agent)
  grep -l "Product   : $1" "$LOGDIR"/*.log 2>/dev/null | xargs -r ls -t 2>/dev/null | head -1
}

hr "NEWEST SERVER BUILD LOG"
SL=$(_newest_log_for server)
if [[ -n "$SL" ]]; then
  echo "log: $SL"
  echo "--- platform summary ---"
  grep -E "succeeded|FAILED Linux|no installer|Linux platform.*failed|Staging tree|ISO :" "$SL" | tail -12
  echo "--- exit-127 / errors (the line before a 127 names the missing command) ---"
  grep -nE "command not found|: 127|not found|exited|ERROR|could not obtain|insufficient" "$SL" | tail -20
else
  echo "no server build log found in $LOGDIR"
fi

hr "NEWEST AGENT BUILD LOG"
AL=$(_newest_log_for agent)
if [[ -n "$AL" ]]; then
  echo "log: $AL"
  echo "--- platform summary (why the ISO is the size it is) ---"
  grep -E "succeeded|FAILED Linux|no installer|Linux platform.*failed|Staging tree|ISO :" "$AL" | tail -12
else
  echo "no agent build log found in $LOGDIR"
fi

# ---------------------------------------------------------------------------
hr "PRESERVED PER-PLATFORM FAILURE LOGS"
for prod in server agent; do
  d="$LOGDIR/sysmanage-${prod}-bundle-logs"
  [[ -d "$d" ]] || continue
  echo "### ${prod} (${d}):"
  shopt -s nullglob
  for f in "$d"/*.log; do
    echo "----- $(basename "$f") -----"
    tail -12 "$f"
    echo
  done
  shopt -u nullglob
done

hr "DONE"
echo "Paste this entire output back."
