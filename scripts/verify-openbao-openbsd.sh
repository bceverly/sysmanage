#!/bin/sh
#
# verify-openbao-openbsd.sh — Phase 13.1.I
#
# Smoke-test the OFFICIAL prebuilt OpenBAO release binary on OpenBSD, end to end:
#   download -> ./bao --version -> server -> init -> unseal -> KV round-trip.
#
# OpenBSD enforces pinsyscalls(2) + W^X, which frequently kills cross-compiled
# Go binaries (abort trap) before they do anything.  If this script PASSes, the
# prebuilt is usable and we make it the OpenBSD installer default; if it FAILs,
# OpenBSD keeps the source build (scripts/build-openbao.sh).
#
# Runs as a normal user (file storage, no mlock, localhost listener).  Needs
# network for the one-time download.  Exits 0 on PASS, 1 on FAIL.
#
# Usage:   sh verify-openbao-openbsd.sh [version]      # default 2.5.4
#   e.g.   sh verify-openbao-openbsd.sh
#          OPENBAO_VERSION=2.5.4 sh verify-openbao-openbsd.sh

set -u

VER="${OPENBAO_VERSION:-${1:-2.5.4}}"
WORK="${WORK:-/tmp/baotest}"
PORT="${PORT:-8222}"            # 8222 (not 8200) to dodge a running OpenBAO
ADDR="http://127.0.0.1:${PORT}"
ASSET="bao_${VER}_Openbsd_x86_64.tar.gz"
URL="https://github.com/openbao/openbao/releases/download/v${VER}/${ASSET}"

SRV_PID=""
cleanup() {
	[ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null
	pkill -f "bao server -config=${WORK}/openbao.hcl" 2>/dev/null
}
trap cleanup EXIT INT TERM

say()  { echo "==> $*"; }
fail() { echo; echo "[FAIL] $*"; echo; exit 1; }

echo "================================================================"
echo " OpenBAO prebuilt verification (Phase 13.1.I)"
echo " host:    $(uname -a)"
echo " version: v${VER}   port: ${PORT}   workdir: ${WORK}"
echo "================================================================"

mkdir -p "$WORK" || fail "cannot create $WORK"
cd "$WORK" || fail "cannot cd $WORK"

# 1. Download the official OpenBSD asset --------------------------------------
say "Downloading ${ASSET} ..."
rm -f "$ASSET"
if ! ftp -o "$ASSET" "$URL"; then
	fail "download failed — likely NO OpenBSD prebuilt for v${VER}. Keep source build."
fi
[ -s "$ASSET" ] || fail "downloaded file is empty"

# 2. Extract ------------------------------------------------------------------
say "Extracting ..."
tar xzf "$ASSET" || fail "tar extract failed"
[ -f ./bao ] || fail "no 'bao' binary after extract"
chmod +x ./bao 2>/dev/null
ls -l ./bao

# 3. THE make-or-break: does the binary even run? (pinsyscalls / W^X) ---------
say "Running ./bao --version (pinsyscalls/W^X smoke test) ..."
VOUT="$(./bao --version 2>&1)"
VRC=$?
echo "    ${VOUT}"
[ $VRC -eq 0 ] || fail "bao --version exited ${VRC} (abort trap / syscall pin?). Prebuilt unusable; keep source build."

# 4. Start a throwaway server (file storage, no mlock, plaintext localhost) ----
say "Starting bao server on ${ADDR} ..."
cat > openbao.hcl <<EOF
storage "file" { path = "${WORK}/data" }
listener "tcp" { address = "127.0.0.1:${PORT}"  tls_disable = 1 }
disable_mlock = true
ui = false
EOF
rm -rf "${WORK}/data"
BAO_ADDR="$ADDR" ./bao server -config=openbao.hcl >server.log 2>&1 &
SRV_PID=$!
export BAO_ADDR="$ADDR"

# 5. Wait for it to listen (or detect an immediate runtime abort) -------------
say "Waiting for server to come up ..."
i=0
up=0
while [ $i -lt 20 ]; do
	if ./bao status 2>&1 | grep -qi "Initialized"; then
		up=1
		break
	fi
	kill -0 "$SRV_PID" 2>/dev/null || break   # server died — stop waiting
	sleep 1
	i=$((i + 1))
done
if [ $up -ne 1 ]; then
	echo "----------------- server.log -----------------"
	cat server.log 2>/dev/null
	echo "----------------------------------------------"
	fail "server never became ready (likely abort-trapped at runtime). Keep source build."
fi
say "Server is up."

# 6. init / unseal ------------------------------------------------------------
say "operator init ..."
./bao operator init -key-shares=1 -key-threshold=1 > init.txt 2>&1 || {
	cat init.txt
	fail "operator init failed"
}
UNSEAL="$(awk '/Unseal Key 1:/ {print $NF}' init.txt)"
ROOT="$(awk '/Initial Root Token:/ {print $NF}' init.txt)"
[ -n "$UNSEAL" ] && [ -n "$ROOT" ] || {
	cat init.txt
	fail "could not parse unseal key / root token from init output"
}

say "operator unseal ..."
./bao operator unseal "$UNSEAL" >/dev/null 2>&1 || fail "unseal failed"

# 7. KV v2 round-trip ---------------------------------------------------------
export BAO_TOKEN="$ROOT"
say "enable kv-v2 + put/get ..."
./bao secrets enable -version=2 -path=secret kv >/dev/null 2>&1 || fail "secrets enable failed"
./bao kv put secret/smtest foo=bar >/dev/null 2>&1 || fail "kv put failed"
GOT="$(./bao kv get -field=foo secret/smtest 2>/dev/null)"
[ "$GOT" = "bar" ] || fail "kv get returned '${GOT}' (expected 'bar')"

# 8. Verdict ------------------------------------------------------------------
echo
echo "================================================================"
echo " [PASS] OpenBAO v${VER} prebuilt is fully functional on $(uname -sr)"
echo "        version OK | server up | init/unseal OK | KV round-trip OK"
echo
echo "        => the prebuilt tarball can be the OpenBSD installer default."
echo "================================================================"
exit 0
