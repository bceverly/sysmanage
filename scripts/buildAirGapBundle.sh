#!/usr/bin/env bash
# buildAirGapBundle.sh — Build a multi-OS air-gap install ISO for the
# sysmanage server or sysmanage-agent.  The resulting ISO contains a
# per-platform install bundle for every supported OS, plus a top-level
# install.sh dispatcher that auto-detects the host OS and runs the
# matching platform installer.
#
# Usage:
#   scripts/buildAirGapBundle.sh server   # for sysmanage server
#   scripts/buildAirGapBundle.sh agent    # for sysmanage-agent
#
# Tunables (env vars):
#   DEST_DIR       Output directory (default: /tmp)
#   STAGING_DIR    Staging dir for the ISO tree (default: mktemp)
#   PLATFORMS      Space-separated list to build (default: all).
#                  Useful for "PLATFORMS='ubuntu-resolute' …" smoke tests.
#   PARALLEL       Run platform builds in parallel (default: 1 = serial).
#                  Set to 4 for 4-way parallel; uses bash background jobs.
#
# Requirements on the build host:
#   * docker (or podman aliased to docker)
#   * xorriso or genisoimage
#   * curl, awk, jq
#
# Output:
#   $DEST_DIR/sysmanage-(server|agent)-bundle.iso
#
# Architecture:
#
# The script orchestrates a set of per-platform "builder" functions.
# Each builder:
#   1. Spins up the relevant Docker container (or uses a non-Docker path
#      for Win/macOS/BSD which pull from GitHub Releases).
#   2. Inside the container: downloads the package, its native-package
#      dependency closure, and its Python wheel closure.
#   3. Copies output to $STAGING/<platform-subdir>/.
#   4. Writes a platform-specific install.sh inside that subdir.
#
# When all builders have completed, the dispatcher install.sh is dropped
# at the staging root and the whole tree is wrapped into an ISO.
#
# Each builder function is INTENTIONALLY SELF-CONTAINED so new platforms
# can be added without touching unrelated code.  Stubs are provided for
# platforms that still need their fetch logic written; the dispatcher
# treats a missing subdirectory as "platform not in this bundle" and
# logs a useful error rather than installing the wrong thing.

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

PRODUCT="${1:-}"
case "$PRODUCT" in
  server|agent|proplus) ;;
  *)
    echo "usage: $0 server|agent|proplus" >&2
    exit 2
    ;;
esac

# Map abstract product → concrete package details.
#
# EXTRAS_* are extra top-level package roots fed into the recursive
# dep walk on top of the package's own Depends: field.  The sysmanage
# server bundle needs PostgreSQL server too, but that's declared as a
# Recommends: on the .deb (so it's intentionally omitted from the
# Depends: chain, and the dep walk uses --no-recommends).  Injecting
# it as an explicit root pulls postgresql + its transitive deps into
# the bundle so an air-gapped target can stand up the DB locally.
case "$PRODUCT" in
  server)
    PKG_NAME="sysmanage"
    PPA_NAME="bceverly/sysmanage"
    # Use the runtime-only requirements (no playwright/semgrep/pytest/…),
    # mirroring the agent.  The full requirements.txt drags dev tooling
    # into every bundle and — critically — playwright has no musl wheel,
    # which breaks the Alpine build.  Builders fall back to fetching this
    # file from the repo tag if the package doesn't ship it yet.
    REQ_PATH_IN_DEB="./opt/sysmanage/requirements-prod.txt"
    REQ_PATH_IN_RPM="/opt/sysmanage/requirements-prod.txt"
    EXTRAS_DEB="postgresql postgresql-contrib"
    EXTRAS_RPM="postgresql-server postgresql-contrib"
    EXTRAS_APK="postgresql postgresql-contrib"
    ;;
  agent)
    PKG_NAME="sysmanage-agent"
    PPA_NAME="bceverly/sysmanage-agent"
    REQ_PATH_IN_DEB="./opt/sysmanage-agent/requirements-prod.txt"
    REQ_PATH_IN_RPM="/opt/sysmanage-agent/requirements-prod.txt"
    EXTRAS_DEB=""
    EXTRAS_RPM=""
    EXTRAS_APK=""
    ;;
  proplus)
    # The Pro+ overlay doesn't bundle OS packages — it carries the
    # build host's Cython engine .so files, JS plugin shims, license
    # JWT, and cached public_key.pem.  None of the PKG_NAME / PPA /
    # EXTRAS variables apply; the proplus path short-circuits past
    # the per-platform builders entirely.
    PKG_NAME=""
    PPA_NAME=""
    REQ_PATH_IN_DEB=""
    REQ_PATH_IN_RPM=""
    EXTRAS_DEB=""
    EXTRAS_RPM=""
    EXTRAS_APK=""
    ;;
esac

DEST_DIR="${DEST_DIR:-/tmp}"
# Stage under /var/tmp, NOT /tmp.  On systemd 256+ (Ubuntu resolute,
# Fedora 40+) /tmp defaults to tmpfs — i.e. RAM-backed — so staging the
# multi-GB bundle tree (per-distro package + wheel closures, then the
# assembled ISO image) there fills physical memory and the OOM killer
# takes down whatever has the largest RSS, frequently the sysmanage
# backend that launched the build.  /var/tmp is disk-backed by FHS
# convention and survives across the build, so the staging tree never
# competes with RAM.  Honour an explicit STAGING_DIR / TMPDIR override.
STAGING_DIR="${STAGING_DIR:-$(mktemp -d "${TMPDIR:-/var/tmp}/sysmanage-bundle-XXXXXX")}"
PARALLEL="${PARALLEL:-1}"
PLATFORMS_ALL="ubuntu-jammy ubuntu-noble ubuntu-questing ubuntu-resolute debian-bookworm fedora-40 fedora-41 rhel-9 opensuse-leap alpine-3.20 freebsd netbsd openbsd macos windows"
PLATFORMS="${PLATFORMS:-$PLATFORMS_ALL}"
ISO_LABEL="SYSMANAGE-$(echo "$PRODUCT" | tr a-z A-Z)"
ISO_PATH="${DEST_DIR}/sysmanage-${PRODUCT}-bundle.iso"

# Per-platform build logs are preserved here — OUTSIDE the staging tree
# so they never bloat the ISO — even when a platform fails and its
# staging subdir is removed.  Without this the only evidence of WHY a
# platform dropped out vanishes with _safe_rmdir, and the bundle
# silently ships missing that platform's dependency closure.
BUNDLE_LOG_DIR="${BUNDLE_LOG_DIR:-${DEST_DIR}/sysmanage-${PRODUCT}-bundle-logs}"
# By default the build FAILS LOUDLY (non-zero exit, no ISO) if any
# requested platform failed, because a partial bundle is missing
# dependency closures and will fail to install offline on the dropped
# platforms.  Set ALLOW_PARTIAL_BUNDLE=1 to intentionally ship a
# subset (e.g. when you only care about a few platforms).
ALLOW_PARTIAL_BUNDLE="${ALLOW_PARTIAL_BUNDLE:-0}"

# Where on the host THIS script lives — needed to find installer assets
# (the dispatcher install.sh) regardless of the cwd we're invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISPATCHER_SH="${SCRIPT_DIR}/../installer/airgap-bundle/install.sh"

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

# Remove a staging subdir that may contain root-owned files left
# behind by Docker (which runs containers as root by default and
# bind-mounted /out is therefore populated as root, not the host
# user).  Plain ``rm -rf`` returns non-zero on those files which —
# under ``set -e`` — would kill the entire build prematurely.
# Spin up a throwaway container to chown the tree back to us, then
# rm.  Errors are always swallowed: cleanup is best-effort.
_safe_rmdir() {
  local target="$1"
  [[ -e "$target" ]] || return 0
  if ! rm -rf "$target" 2>/dev/null; then
    docker run --rm -v "$target":/work alpine:3.20 \
      sh -c "chown -R $(id -u):$(id -g) /work" >/dev/null 2>&1 || true
    rm -rf "$target" 2>/dev/null || true
  fi
  return 0
}

# Map a platform key to its staging subdir name.  Linux builders stage
# under linux-<platform>; the release-asset builders (bsd/macos/windows)
# stage under <platform> directly.
_outdir_for_platform() {
  case "$1" in
    ubuntu-*|debian-*|fedora-*|rhel-*|opensuse-*|alpine-*) echo "linux-$1" ;;
    *) echo "$1" ;;
  esac
}

# True for the Docker-driven Linux platforms that carry a full
# .deb/.rpm + wheel dependency closure (a failure there = broken
# bundle).  False for the release-asset platforms (bsd/macos/windows).
_is_linux_platform() {
  case "$1" in
    ubuntu-*|debian-*|fedora-*|rhel-*|opensuse-*|alpine-*) return 0 ;;
    *) return 1 ;;
  esac
}

# Failure handler for the Docker-based Linux builders.  Surface the tail
# of the build log, PRESERVE the full log outside the staging tree (so
# it survives the staging-dir cleanup), then drop the incomplete staging
# subdir so it isn't wrapped into the ISO.
_linux_build_failed() {
  local platform="$1" outdir="$2"
  tail -30 "$outdir/build.log" 2>/dev/null || true
  mkdir -p "$BUNDLE_LOG_DIR"
  cp -f "$outdir/build.log" "$BUNDLE_LOG_DIR/${platform}.log" 2>/dev/null || true
  warn "[$platform] docker build failed — skipping (full log: $BUNDLE_LOG_DIR/${platform}.log)"
  _safe_rmdir "$outdir"
}

# Resource thresholds for the build.  The per-distro Docker builds
# compile wheels (~1 GB each) and stage a multi-GB tree; a starved host
# OOM-kills them and silently ships a hollow ISO.  Mirror the values the
# backend's resource-status preflight uses.  All overridable via env.
MIN_BUILD_AVAIL_MB="${MIN_BUILD_AVAIL_MB:-2048}"   # RAM + free swap floor
SOFT_BUILD_RAM_MB="${SOFT_BUILD_RAM_MB:-1024}"     # real-RAM warn threshold
MIN_BUILD_DISK_GB="${MIN_BUILD_DISK_GB:-5}"        # free-disk floor
SOFT_BUILD_DISK_GB="${SOFT_BUILD_DISK_GB:-10}"     # free-disk warn threshold

# Read a /proc/meminfo field (e.g. MemAvailable, SwapFree) in MB, or -1.
_meminfo_mb() {
  awk -v k="$1:" '$1==k {printf "%d", $2/1024; f=1} END{ if(!f) print -1 }' \
    /proc/meminfo 2>/dev/null
}

# Free whole-GB on the filesystem holding $1, walking up to an existing
# ancestor so a not-yet-created dir doesn't break df.
_disk_free_gb() {
  local p="$1"
  while [[ -n "$p" && ! -e "$p" ]]; do
    [[ "$p" == "/" ]] && break
    p="$(dirname "$p")"
  done
  df -PBG "$p" 2>/dev/null | awk 'NR==2 {gsub("G","",$4); print $4+0}'
}

# Refuse to start a starved build (override: SKIP_RESOURCE_CHECK=1).
preflight_resources() {
  if [[ "${SKIP_RESOURCE_CHECK:-0}" == "1" ]]; then
    warn "resource pre-flight skipped (SKIP_RESOURCE_CHECK=1)"
    return 0
  fi
  [[ -r /proc/meminfo ]] || { warn "no /proc/meminfo — skipping resource pre-flight"; return 0; }
  local mem_avail swap_free avail disk_dest disk_stage disk_min
  mem_avail="$(_meminfo_mb MemAvailable)"; [[ "$mem_avail" =~ ^[0-9]+$ ]] || mem_avail=0
  swap_free="$(_meminfo_mb SwapFree)";     [[ "$swap_free" =~ ^[0-9]+$ ]] || swap_free=0
  avail=$(( mem_avail + swap_free ))
  disk_dest="$(_disk_free_gb "$DEST_DIR")";              [[ "$disk_dest"  =~ ^[0-9]+$ ]] || disk_dest=0
  disk_stage="$(_disk_free_gb "${STAGING_DIR:-/var/tmp}")"; [[ "$disk_stage" =~ ^[0-9]+$ ]] || disk_stage=0
  disk_min=$(( disk_dest < disk_stage ? disk_dest : disk_stage ))
  log "Resources : RAM avail ${mem_avail}MB + swap free ${swap_free}MB = ${avail}MB ; disk free ${disk_min}GB"

  local fatal=0
  if (( avail < MIN_BUILD_AVAIL_MB )); then
    warn "only ${avail}MB RAM+swap free; need >= ${MIN_BUILD_AVAIL_MB}MB (add swap or grow the VM)"
    fatal=1
  fi
  if (( disk_min < MIN_BUILD_DISK_GB )); then
    warn "only ${disk_min}GB free disk; need >= ${MIN_BUILD_DISK_GB}GB"
    fatal=1
  fi
  if (( fatal )); then
    die "insufficient resources for a bundle build — free up RAM/disk, or set SKIP_RESOURCE_CHECK=1 to try anyway."
  fi
  (( mem_avail < SOFT_BUILD_RAM_MB )) \
    && warn "only ${mem_avail}MB real RAM free — the build will lean on swap and run slowly"
  (( disk_min < SOFT_BUILD_DISK_GB )) \
    && warn "only ${disk_min}GB free disk — a full build can use several GB"
  return 0
}

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

for cmd in docker curl jq awk xorrisofs; do
  command -v "$cmd" >/dev/null 2>&1 \
    || die "missing required tool: $cmd
Install with:  sudo apt install xorriso docker.io curl jq"
done

docker info >/dev/null 2>&1 \
  || die "docker daemon not reachable.  Start it (sudo systemctl start docker) and add yourself to the docker group (sudo usermod -aG docker \$USER ; re-login)."

[[ -f "$DISPATCHER_SH" ]] \
  || die "dispatcher template not found at $DISPATCHER_SH
Expected the file installer/airgap-bundle/install.sh next to this script."

log "Product   : $PRODUCT  ($PKG_NAME)"
log "PPA       : $PPA_NAME"
log "Staging   : $STAGING_DIR"
log "Output    : $ISO_PATH"
log "Platforms : $PLATFORMS"

# The Pro+ overlay bundle is a lightweight file copy (no Docker, no
# wheel compile), so it doesn't need the resource floor.
[[ "$PRODUCT" == "proplus" ]] || preflight_resources

# Resolve the upstream release version (e.g. "2.4.0.2") from the
# GitHub release tag.  We strip a leading "v" because tags are
# typically vX.Y.Z but the user-facing version is X.Y.Z.  If the
# fetch fails (rate-limited, offline, etc.) we leave the marker
# empty and the API row stays version=null — non-fatal.
if [[ -n "${BUNDLE_VERSION_FILE:-}" ]]; then
  case "$PRODUCT" in
    server)  _gh_repo="bceverly/sysmanage" ;;
    agent)   _gh_repo="bceverly/sysmanage-agent" ;;
    proplus) _gh_repo="bceverly/sysmanage" ;;  # Pro+ rides server's tag.
  esac
  BUNDLE_VERSION="$(curl -fsSL "https://api.github.com/repos/${_gh_repo}/releases/latest" 2>/dev/null \
                    | awk -F\" '/"tag_name":/ {print $4; exit}' \
                    | sed -E 's/^v//')" || true
  if [[ -n "${BUNDLE_VERSION:-}" ]]; then
    printf '%s' "$BUNDLE_VERSION" > "$BUNDLE_VERSION_FILE"
    log "Version   : $BUNDLE_VERSION"
  else
    warn "could not resolve upstream release tag for ${_gh_repo}"
  fi
fi

# ---------------------------------------------------------------------------
# Pro+ overlay bundle — assembled from the build host's own license
# artifacts (Cython engine .so files, JS plugin shims, license JWT,
# cached public_key.pem).  No Docker, no per-distro builders; the
# overlay is OS-agnostic because the engines are loaded by the
# already-installed sysmanage server's Python interpreter on the
# target.  Bails early if the build host isn't itself Pro+-licensed.
# ---------------------------------------------------------------------------

build_proplus() {
  local sysmanage_yaml="/etc/sysmanage.yaml"
  local modules_src="/var/lib/sysmanage/modules"
  local public_key_src="/var/lib/sysmanage/license/public_key.pem"

  [[ -r "$sysmanage_yaml" ]] \
    || die "cannot read $sysmanage_yaml — build host must be a sysmanage server"
  [[ -d "$modules_src" ]] \
    || die "modules dir not found at $modules_src — build host must have Pro+ active"
  [[ -r "$public_key_src" ]] \
    || die "license public key not found at $public_key_src — build host must have phoned home at least once"

  # Pull the license.key string from the yaml (one-line value or a
  # quoted string).  Use grep+sed rather than a yaml parser so this
  # works in the bare shell environment.
  local license_key
  license_key="$(awk '
    BEGIN { in_license = 0 }
    /^license:/ { in_license = 1; next }
    /^[^[:space:]]/ { in_license = 0 }
    in_license && /^[[:space:]]+key:/ {
      sub(/^[[:space:]]+key:[[:space:]]*/, "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' "$sysmanage_yaml")"
  [[ -n "$license_key" ]] \
    || die "license.key not set in $sysmanage_yaml — build host is not Pro+ licensed"

  log "Staging Pro+ overlay (modules + license + public key)"
  mkdir -p "$STAGING_DIR/modules"
  cp -R "$modules_src/." "$STAGING_DIR/modules/"
  cp "$public_key_src" "$STAGING_DIR/public_key.pem"
  printf '%s\n' "$license_key" > "$STAGING_DIR/license.key"
  chmod 600 "$STAGING_DIR/license.key"

  # Embed the collector's manifest-signing PUBLIC key, if this build
  # host is a collector.  The repository server drops it into its
  # trusted-collectors keyring (see install.sh below) so it can verify
  # air-gap media signed by THIS collector — establishing cross-air-gap
  # trust through the same media the operator already hand-carries,
  # rather than a separate out-of-band key exchange.  Only the PUBLIC
  # key travels; the private signing key never leaves the collector.
  # Optional: a build host that isn't a collector ships no key and the
  # repository operator must add it manually before the first ingest.
  local collector_pub="/var/lib/sysmanage/airgap/collector-ed25519.pub"
  if [[ -r "$collector_pub" ]]; then
    log "Embedding collector signing public key into the bundle keyring"
    mkdir -p "$STAGING_DIR/trusted-collectors"
    # Name by sha256 of the key file so multiple collectors' keys can
    # coexist in one repository keyring without clobbering.  This is a
    # cosmetic filename only — the repository recomputes the canonical
    # fingerprint internally when matching a signature to a key.
    local fp
    fp="$(sha256sum "$collector_pub" | awk '{print $1}')"
    [[ -n "$fp" ]] || fp="collector"
    cp "$collector_pub" "$STAGING_DIR/trusted-collectors/${fp}.pub"
  else
    warn "no collector signing key at $collector_pub — bundle ships without a trusted-collector key; the repository operator must add it manually before ingesting media"
  fi

  # Idempotent installer that the air-gap target runs as root.  Uses
  # the already-installed sysmanage venv's PyYAML so we don't need a
  # standalone yaml editor on the target.
  cat > "$STAGING_DIR/install.sh" <<'EOF'
#!/bin/sh
# Pro+ overlay installer for sysmanage.  Idempotent — safe to re-run.
#
# Prerequisite: the sysmanage server package must already be installed
# (i.e. the OS-level air-gap server bundle ran first).  This script
# copies the bundled Pro+ engine modules, license key, and license
# public key into place, edits /etc/sysmanage.yaml to operate offline,
# and restarts the sysmanage service.

set -eu
cd "$(dirname "$0")"

if [ "$(id -u)" != "0" ]; then
  echo "ERROR: must run as root (try: sudo ./install.sh)" >&2
  exit 1
fi

if [ ! -f /etc/sysmanage.yaml ]; then
  echo "ERROR: /etc/sysmanage.yaml not found.  Install the sysmanage" >&2
  echo "       server bundle first, then re-run this overlay." >&2
  exit 2
fi
if [ ! -x /opt/sysmanage/.venv/bin/python ]; then
  echo "ERROR: /opt/sysmanage/.venv/bin/python not found.  This overlay" >&2
  echo "       requires the sysmanage server to be installed first." >&2
  exit 2
fi

echo "[proplus] Installing Pro+ engine modules..."
install -d -o sysmanage -g sysmanage -m 0750 /var/lib/sysmanage/modules
# Copy then chown — using install(1) per-file would lose
# subdirectories if the vendor ever adds them.
cp -R modules/. /var/lib/sysmanage/modules/
chown -R sysmanage:sysmanage /var/lib/sysmanage/modules
find /var/lib/sysmanage/modules -type f -exec chmod 0644 {} +

echo "[proplus] Installing license public key..."
install -d -o sysmanage -g sysmanage -m 0750 /var/lib/sysmanage/license
install -o sysmanage -g sysmanage -m 0644 public_key.pem \
  /var/lib/sysmanage/license/public_key.pem

# Trusted-collector keyring: if the build host embedded a collector's
# manifest-signing public key, drop it into the repository's keyring so
# the ingestion orchestrator can verify air-gap media signed by that
# collector.  Additive — never clears existing trusted keys, so an
# overlay re-run or a second collector's bundle just adds another key.
if [ -d trusted-collectors ]; then
  echo "[proplus] Installing trusted-collector keyring..."
  install -d -o sysmanage -g sysmanage -m 0750 \
    /var/lib/sysmanage/airgap/trusted-collectors
  for k in trusted-collectors/*.pub; do
    [ -e "$k" ] || continue
    install -o sysmanage -g sysmanage -m 0644 "$k" \
      /var/lib/sysmanage/airgap/trusted-collectors/
    echo "[proplus]   + $(basename "$k")"
  done
fi

echo "[proplus] Updating /etc/sysmanage.yaml for offline operation..."
LICENSE_KEY="$(cat license.key)"
/opt/sysmanage/.venv/bin/python - "$LICENSE_KEY" <<'PYEOF'
import sys
import yaml
from pathlib import Path

key = sys.argv[1].strip()
path = Path("/etc/sysmanage.yaml")
data = yaml.safe_load(path.read_text()) or {}

lic = data.setdefault("license", {})
lic["key"] = key
# Deliberately do NOT blank phone_home_url here.  The JWT's
# offline_days grace window is the vendor's enforcement lever
# against ISO sharing: an air-gapped target will fail phone-home,
# fall back to the local validator + cached public_key.pem, and
# stay Pro+-active for offline_days (~30) from the last successful
# phone-home.  Operators must refresh this overlay before the grace
# expires.  If we silenced phone_home_url, every shared copy of
# this ISO would run Pro+ until the JWT's exp date — months or
# years — with no revocation path.

geo = data.setdefault("geo_lookup", {})
geo["enabled"] = False
geo["ipapi_fallback_enabled"] = False

path.write_text(yaml.safe_dump(data, sort_keys=False))
print("[proplus] /etc/sysmanage.yaml updated")
PYEOF

echo "[proplus] Registering modules in proplus_module_cache..."
# The module loader queries the proplus_module_cache table to decide
# whether each engine module is already on disk; if no row exists it
# tries to download from license.sysmanage.org (which fails on an
# air-gap host).  Walk /var/lib/sysmanage/modules/*.so and upsert a
# row per module so the loader finds them locally on next startup.
cd /opt/sysmanage && PYTHONPATH=/opt/sysmanage /opt/sysmanage/.venv/bin/python - <<'PYEOF'
import hashlib
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from backend.persistence import db
from backend.persistence.models import ProPlusModuleCache

MODULES_DIR = Path("/var/lib/sysmanage/modules")
# Filenames are <module_code>_<py_major>.<py_minor>.so e.g.
# health_engine_3.14.so or airgap_repository_engine_3.14.so.
FILE_RE = re.compile(r"^(?P<code>[a-z0-9_]+)_(?P<py>\d+\.\d+)\.so$")
SYSTEM = platform.system().lower()  # "linux"
MACHINE = {"x86_64": "x86_64", "amd64": "x86_64",
           "aarch64": "aarch64", "arm64": "aarch64"}.get(
    platform.machine().lower(), platform.machine().lower())

def sha512(path):
    h = hashlib.sha512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

Session = sessionmaker(bind=db.get_engine())
now = datetime.now(timezone.utc).replace(tzinfo=None)
inserted = updated = 0
with Session() as s:
    for so in sorted(MODULES_DIR.glob("*.so")):
        m = FILE_RE.match(so.name)
        if not m:
            continue
        code, pyv = m.group("code"), m.group("py")
        digest = sha512(so)
        row = (s.query(ProPlusModuleCache)
                .filter_by(module_code=code, platform=SYSTEM,
                           architecture=MACHINE, python_version=pyv)
                .first())
        if row is None:
            s.add(ProPlusModuleCache(
                module_code=code, version="airgap",
                platform=SYSTEM, architecture=MACHINE,
                python_version=pyv, file_path=str(so),
                file_hash=digest, downloaded_at=now,
            ))
            inserted += 1
        else:
            row.file_path = str(so)
            row.file_hash = digest
            row.downloaded_at = now
            updated += 1
    s.commit()
print(f"[proplus] module cache: {inserted} inserted, {updated} updated")
PYEOF

echo "[proplus] Restarting sysmanage service..."
systemctl restart sysmanage

echo
echo "Pro+ overlay installed.  Verify with:"
echo "  systemctl status sysmanage"
echo "  curl -ks https://localhost:8443/api/v1/server-info | python3 -m json.tool"
echo "The 'license_tier' field should now be 'professional' or 'enterprise'."
EOF
  chmod +x "$STAGING_DIR/install.sh"

  cat > "$STAGING_DIR/README.txt" <<EOF
SysManage Pro+ overlay bundle
==============================

Built  : $(date -u +'%Y-%m-%dT%H:%M:%SZ')
Source : $(hostname -f 2>/dev/null || hostname)

This ISO carries the Pro+ engine modules, license JWT, and license
public key from a sysmanage server with an active Pro+ license, ready
to drop onto an air-gapped sysmanage server that has the standard
sysmanage server bundle already installed.

Install on the air-gapped server:

  sudo mount -o loop sysmanage-proplus-bundle.iso /mnt
  sudo /mnt/install.sh
  sudo umount /mnt

The installer is idempotent: re-running it overwrites the modules,
the license key, and the relevant /etc/sysmanage.yaml fields.

Layout:

  install.sh         offline installer (run as root)
  README.txt         this file
  modules/           Cython engine .so files + JS plugin shims
  public_key.pem     ECDSA P-521 public key for license verification
  license.key        license JWT (single line, 0600 perms)
EOF

  log "Building ISO with xorrisofs"
  rm -f "$ISO_PATH" 2>/dev/null || true
  xorrisofs -quiet -o "$ISO_PATH" -V "$ISO_LABEL" -r -J "$STAGING_DIR"
  log "Done."
  log "ISO : $ISO_PATH ($(du -h "$ISO_PATH" | cut -f1))"
}

# Branch off here when building the Pro+ overlay — no per-platform
# orchestration, no dispatcher install.sh.  build_proplus mints the
# ISO itself and we exit clean.
if [[ "$PRODUCT" == "proplus" ]]; then
  build_proplus
  exit 0
fi

# ---------------------------------------------------------------------------
# Per-platform builders
# ---------------------------------------------------------------------------
#
# Each builder writes its output under $STAGING_DIR/<subdir>/ and creates
# a `install.sh` in that subdir.  The dispatcher will hand off to that
# install.sh after detecting the host OS.
#
# All builders take a single argument: the platform key (e.g.
# "ubuntu-resolute").  This redundancy lets the orchestrator dispatch
# generically.

# Shared: write a Ubuntu/Debian-style per-platform installer that does
# the same env-var-driven offline install we proved out with buildServerIso.sh.
_write_deb_installer() {
  local outdir="$1"
  cat > "$outdir/install.sh" <<EOF
#!/bin/sh
# Per-platform Ubuntu/Debian installer for ${PKG_NAME}.
set -eu
cd "\$(dirname "\$0")"

if ! command -v dpkg >/dev/null 2>&1; then
  echo "ERROR: dpkg not found — this subdirectory is for Ubuntu/Debian only." >&2
  exit 2
fi

# The main package is the only .deb at this directory's top level;
# dependency .debs live under apt-deps/.
MAIN_DEB="\$(ls -1 *.deb 2>/dev/null | head -1)"
if [ -z "\$MAIN_DEB" ]; then
  echo "ERROR: no .deb found in \$(pwd)" >&2
  exit 3
fi

# apt-deps/ may be empty (e.g. a build host where the dep walk
# produced nothing) — don't let the literal "apt-deps/*.deb" reach
# dpkg or it'll error before installing anything.
DEP_COUNT=\$(ls -1 apt-deps/*.deb 2>/dev/null | wc -l)
echo "Installing \$MAIN_DEB + \$DEP_COUNT deps..."
if [ "\$DEP_COUNT" -gt 0 ]; then
  exec sudo env PIP_NO_INDEX=1 PIP_FIND_LINKS="\$(pwd)/wheels" \\
       dpkg -i apt-deps/*.deb "\$MAIN_DEB"
else
  exec sudo env PIP_NO_INDEX=1 PIP_FIND_LINKS="\$(pwd)/wheels" \\
       dpkg -i "\$MAIN_DEB"
fi
EOF
  chmod +x "$outdir/install.sh"
}

# Shared: Fedora/RHEL/openSUSE installer.
_write_rpm_installer() {
  local outdir="$1"
  local tool="$2"   # dnf | yum | zypper
  cat > "$outdir/install.sh" <<EOF
#!/bin/sh
# Per-platform ${tool} installer for ${PKG_NAME}.
set -eu
cd "\$(dirname "\$0")"

if ! command -v ${tool} >/dev/null 2>&1; then
  echo "ERROR: ${tool} not found — this subdirectory is for ${tool}-based systems." >&2
  exit 2
fi

MAIN_RPM="\$(ls -1 *.rpm 2>/dev/null | head -1)"
if [ -z "\$MAIN_RPM" ]; then
  echo "ERROR: no .rpm found in \$(pwd)" >&2
  exit 3
fi

# rpm-deps/ may be empty — don't let the literal "rpm-deps/*.rpm"
# reach ${tool} or it'll error before installing anything.
DEP_COUNT=\$(ls -1 rpm-deps/*.rpm 2>/dev/null | wc -l)
echo "Installing \$MAIN_RPM + \$DEP_COUNT deps..."
if [ "\$DEP_COUNT" -gt 0 ]; then
  exec sudo env PIP_NO_INDEX=1 PIP_FIND_LINKS="\$(pwd)/wheels" \\
       ${tool} install -y --allowerasing rpm-deps/*.rpm "\$MAIN_RPM"
else
  exec sudo env PIP_NO_INDEX=1 PIP_FIND_LINKS="\$(pwd)/wheels" \\
       ${tool} install -y --allowerasing "\$MAIN_RPM"
fi
EOF
  chmod +x "$outdir/install.sh"
}

# ----- OpenBAO artifact staging (air-gap secrets broker) -------------------
#
# OpenBAO is central to SysManage and must be present for an offline install.
# `bao` is a single static binary with no dependency tree, so staging it is
# trivial: for deb/rpm platforms we drop the native package into the same
# dep dir the per-platform install.sh already batch-installs (so OpenBAO is
# installed offline "for free"); for the others we stage the extracted
# binary under <subdir>/openbao/bao, which the platform install.sh drops at
# /usr/local/bin/bao before installing the OS package.  Runs on the HOST
# after the container build (curl + jq are host requirements).
_OPENBAO_REPO="openbao/openbao"

_openbao_asset_url() {
  # $1 = jq regex matched against asset .name
  curl -fsSL "https://api.github.com/repos/${_OPENBAO_REPO}/releases/latest" 2>/dev/null \
    | jq -r ".assets[] | select(.name | test(\"$1\")) | .browser_download_url" \
    | head -1
}

_stage_openbao() {
  local outdir="$1" kind="$2"
  case "$kind" in
    deb)
      local url; url=$(_openbao_asset_url "amd64\\\\.deb\$")
      if [ -n "$url" ]; then
        mkdir -p "$outdir/apt-deps"
        curl -fsSL -o "$outdir/apt-deps/openbao_amd64.deb" "$url" \
          && log "[openbao] staged .deb into $(basename "$outdir")/apt-deps" \
          || warn "[openbao] .deb download failed for $(basename "$outdir")"
      else
        warn "[openbao] no .deb asset found"
      fi
      ;;
    rpm)
      local url; url=$(_openbao_asset_url "x86_64\\\\.rpm\$")
      if [ -n "$url" ]; then
        mkdir -p "$outdir/rpm-deps"
        curl -fsSL -o "$outdir/rpm-deps/openbao_x86_64.rpm" "$url" \
          && log "[openbao] staged .rpm into $(basename "$outdir")/rpm-deps" \
          || warn "[openbao] .rpm download failed for $(basename "$outdir")"
      else
        warn "[openbao] no .rpm asset found"
      fi
      ;;
    binary-*)
      local osname="${kind#binary-}" tok ext bin
      case "$osname" in
        linux)   tok="Linux_x86_64";   ext="tar\\\\.gz"; bin="bao" ;;
        freebsd) tok="Freebsd_x86_64"; ext="tar\\\\.gz"; bin="bao" ;;
        netbsd)  tok="Netbsd_x86_64";  ext="tar\\\\.gz"; bin="bao" ;;
        darwin)  tok="Darwin_arm64";   ext="tar\\\\.gz"; bin="bao" ;;
        windows) tok="Windows_x86_64"; ext="zip";        bin="bao.exe" ;;
        *) warn "[openbao] unknown binary os: $osname"; return ;;
      esac
      local url; url=$(_openbao_asset_url "${tok}\\\\.${ext}\$")
      if [ -z "$url" ]; then warn "[openbao] no $osname asset found"; return; fi
      mkdir -p "$outdir/openbao"
      local tmp; tmp="$(mktemp)"
      if curl -fsSL -o "$tmp" "$url"; then
        if [ "$ext" = "zip" ]; then
          (cd "$outdir/openbao" && unzip -o "$tmp" "$bin" >/dev/null 2>&1) || true
        else
          tar -xzf "$tmp" -C "$outdir/openbao" "$bin" 2>/dev/null || true
        fi
        [ -f "$outdir/openbao/$bin" ] \
          && log "[openbao] staged $osname binary into $(basename "$outdir")/openbao" \
          || warn "[openbao] could not extract $bin for $osname"
      fi
      rm -f "$tmp"
      ;;
    *) warn "[openbao] unknown stage kind: $kind" ;;
  esac
}

# ----- Ubuntu / Debian builders (apt-based) --------------------------------

# Ubuntu release codename → Python version + Docker image.
_ubuntu_python_version() {
  case "$1" in
    jammy)    echo "3.10" ;;
    noble)    echo "3.12" ;;
    questing) echo "3.13" ;;
    resolute) echo "3.14" ;;
    *)        echo "" ;;
  esac
}

_ubuntu_image() {
  case "$1" in
    jammy)    echo "ubuntu:22.04" ;;
    noble)    echo "ubuntu:24.04" ;;
    questing) echo "ubuntu:25.10" ;;
    resolute) echo "ubuntu:26.04" ;;
    *)        echo "" ;;
  esac
}

build_ubuntu_like() {
  local platform="$1"           # e.g. ubuntu-resolute
  local codename="${platform#ubuntu-}"
  local image; image=$(_ubuntu_image "$codename")
  local py;    py=$(_ubuntu_python_version "$codename")
  [[ -n "$image" && -n "$py" ]] || die "unknown ubuntu codename: $codename"

  local outdir="$STAGING_DIR/linux-${platform}"
  mkdir -p "$outdir"

  log "[$platform] docker run $image to fetch packages + wheels"
  docker run --rm \
    -v "$outdir:/out" \
    -e PKG="$PKG_NAME" \
    -e PPA="$PPA_NAME" \
    -e REPO="$(_gh_owner_repo)" \
    -e REQ_PATH="$REQ_PATH_IN_DEB" \
    -e PY="$py" \
    -e EXTRAS="$EXTRAS_DEB" \
    "$image" bash -euxc '
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y --no-install-recommends \
        ca-certificates curl jq gnupg software-properties-common \
        python3 python3-pip python3-venv \
        gcc libffi-dev libssl-dev libpq-dev python3-dev
      add-apt-repository -y "ppa:${PPA}"
      apt-get update -qq

      cd /out
      mkdir -p apt-deps wheels

      # Main package — try PPA first, fall back to GitHub Releases.
      # The PPA path fails when Launchpad has not yet built (or has
      # failed to build) the binary for this codename, even though
      # the source upload succeeded.  GitHub Releases ships a generic
      # .deb that is binary-compatible with both Debian and Ubuntu
      # (same glibc family, Architecture: all package), so it serves
      # as a resilient fallback.
      if ! apt-get download "$PKG" 2>/dev/null; then
        echo "[$PKG] PPA download failed for ${PPA} — falling back to GitHub Releases ($REPO)"
        ASSET_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
                    | jq -r ".assets[] | select(.name | test(\"\\\\.deb$\")) | .browser_download_url" \
                    | head -1)
        [ -n "$ASSET_URL" ] || { echo "no .deb in releases for $REPO" >&2; exit 1; }
        # Save under the same _<version>_<arch>.deb glob pattern that
        # apt-get download produces, so downstream globs (`"$PKG"_*.deb`)
        # still match.  The exact version string in the filename does
        # not matter to dpkg-deb invocations below.
        curl -fsSL -o "${PKG}_releases_all.deb" "$ASSET_URL"
      fi

      # Recursive apt deps (filtered to amd64/all).  Note the
      # triple-backslash on \\\${  — we want the inner bash to see
      # \${ as four literal chars (one backslash + dollar + brace)
      # so grep gets the regex ^\${ to filter Debian-style unresolved
      # template deps like ${PYTHON3}.  A single \\ would make the
      # inner bash try to expand ${...} and choke on the missing }.
      DIRECT="$(dpkg-deb -f "$PKG"_*.deb Depends | tr "," "\n" \
                | awk "{print \$1}" | grep -v "^\\\${" | grep -vE "^$" | sort -u)"
      # Inject product-specific extras (e.g. postgresql for the
      # server) as additional dep-walk roots.  Set by the PRODUCT
      # case at the top of the outer script; agent passes empty.
      ROOTS="$DIRECT $EXTRAS"
      cd apt-deps
      # Expand the dep tree, then filter out two kinds of entries
      # that would poison a batched apt-get download: virtual
      # provides (printed as <name> in angle brackets) and
      # arch-suffixed names like python3:i386 that have no archive
      # entry on amd64.  Then download per-package so one missing
      # entry does not abort the whole batch under xargs.
      DEP_PKGS="$(apt-cache depends --recurse --no-recommends --no-suggests \
                                    --no-conflicts --no-breaks --no-replaces --no-enhances \
                                    $ROOTS \
                  | awk "/^[A-Za-z0-9]/ {print \$1}" \
                  | grep -v "<.*>" \
                  | grep -v ":" \
                  | sort -u)"
      echo "Resolved $(echo "$DEP_PKGS" | wc -l) candidate dep packages"
      _ok=0; _fail=0
      while IFS= read -r _pkg; do
        [ -z "$_pkg" ] && continue
        if apt-get download "$_pkg" >/dev/null 2>&1; then
          _ok=$((_ok+1))
        else
          _fail=$((_fail+1))
        fi
      done <<<"$DEP_PKGS"
      echo "downloaded $_ok apt deps; $_fail were unavailable/virtual"
      find . -maxdepth 1 -name "*.deb" ! -name "*_amd64.deb" ! -name "*_all.deb" -delete
      # Drop legacy "X" packages when a "X-stable" replacement is
      # also bundled.  Ubuntu 26.04 (resolute) introduced runc-stable
      # as the Conflicts: replacement for runc; apt-cache depends
      # --recurse follows both branches and downloads both.  Without
      # this filter, dpkg -i fails on the second of the pair.
      for _stable in $(ls *-stable_*.deb 2>/dev/null); do
        _legacy="${_stable%%-stable_*}"
        rm -f "${_legacy}"_*.deb 2>/dev/null || true
      done
      cd ..

      # requirements -> wheels (pip wheel compiles sdists too).  Prefer
      # the file shipped inside the package; if it is absent (e.g. the
      # server package predates requirements-prod.txt) fetch it from the
      # repo at the released tag so the version still matches.
      REQ=/tmp/req.txt
      dpkg-deb --fsys-tarfile "$PKG"_*.deb | tar -xO "$REQ_PATH" > "$REQ" 2>/dev/null || true
      if [ ! -s "$REQ" ]; then
        TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | jq -r .tag_name)
        curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/$(basename "$REQ_PATH")" -o "$REQ" \
          || curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/requirements.txt" -o "$REQ" \
          || { echo "could not obtain requirements for ${PKG}" >&2; exit 1; }
      fi
      python3 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { _linux_build_failed "$platform" "$outdir"; return; }

  _write_deb_installer "$outdir"
  _stage_openbao "$outdir" deb
  log "[$platform] done — $(find "$outdir/apt-deps" -name '*.deb' | wc -l) deps + $(find "$outdir/wheels" -name '*.whl' | wc -l) wheels"
}

# Distro→image mapping for Debian.  We pull the .deb directly from
# GitHub Releases (no Debian apt source exists in the project) and
# resolve the apt dep closure using Debian's own package metadata.
_debian_image() {
  case "$1" in
    bookworm) echo "debian:12" ;;
    trixie)   echo "debian:13" ;;
    *)        echo "" ;;
  esac
}

build_debian_like() {
  local platform="$1"           # e.g. debian-bookworm
  local codename="${platform#debian-}"
  local image; image=$(_debian_image "$codename")
  [[ -n "$image" ]] || { warn "[$platform] unknown debian codename — skipping"; return; }

  local outdir="$STAGING_DIR/linux-${platform}"
  mkdir -p "$outdir"

  log "[$platform] docker run $image to fetch .deb + apt deps + wheels"
  docker run --rm \
    -v "$outdir:/out" \
    -e PKG="$PKG_NAME" \
    -e REPO="$(_gh_owner_repo)" \
    -e REQ_PATH="$REQ_PATH_IN_DEB" \
    -e EXTRAS="$EXTRAS_DEB" \
    "$image" bash -euxc '
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y --no-install-recommends \
        ca-certificates curl jq gnupg \
        python3 python3-pip python3-venv python3-dev \
        gcc libffi-dev libssl-dev libpq-dev

      cd /out
      mkdir -p apt-deps wheels

      # Pull the .deb from GitHub Releases.  Asset name pattern is the
      # standard one produced by the build-ubuntu job (which the .deb
      # is binary-compatible with on Debian for the architectures we
      # ship — both Debian and Ubuntu use the same glibc family).
      ASSET_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
                  | jq -r ".assets[] | select(.name | test(\"\\\\.deb$\")) | .browser_download_url" \
                  | head -1)
      [ -n "$ASSET_URL" ] || { echo "no .deb in releases for $REPO" >&2; exit 1; }
      curl -fsSL -o "${PKG}.deb" "$ASSET_URL"

      # Recursive apt deps via apt-cache (Debian repos are configured
      # by default in the base image).  Same filter+loop pattern as
      # the Ubuntu builder — see comment there for the rationale.
      DIRECT="$(dpkg-deb -f ${PKG}.deb Depends | tr "," "\n" \
                | awk "{print \$1}" | grep -v "^\\\${" | grep -vE "^$" | sort -u)"
      ROOTS="$DIRECT $EXTRAS"
      cd apt-deps
      DEP_PKGS="$(apt-cache depends --recurse --no-recommends --no-suggests \
                                    --no-conflicts --no-breaks --no-replaces --no-enhances \
                                    $ROOTS \
                  | awk "/^[A-Za-z0-9]/ {print \$1}" \
                  | grep -v "<.*>" \
                  | grep -v ":" \
                  | sort -u)"
      echo "Resolved $(echo "$DEP_PKGS" | wc -l) candidate dep packages"
      _ok=0; _fail=0
      while IFS= read -r _pkg; do
        [ -z "$_pkg" ] && continue
        if apt-get download "$_pkg" >/dev/null 2>&1; then
          _ok=$((_ok+1))
        else
          _fail=$((_fail+1))
        fi
      done <<<"$DEP_PKGS"
      echo "downloaded $_ok apt deps; $_fail were unavailable/virtual"
      find . -maxdepth 1 -name "*.deb" ! -name "*_amd64.deb" ! -name "*_all.deb" -delete
      # Same legacy-vs-stable filter as the Ubuntu builder — see the
      # comment there for the rationale.
      for _stable in $(ls *-stable_*.deb 2>/dev/null); do
        _legacy="${_stable%%-stable_*}"
        rm -f "${_legacy}"_*.deb 2>/dev/null || true
      done
      cd ..

      REQ=/tmp/req.txt
      dpkg-deb --fsys-tarfile ${PKG}.deb | tar -xO "$REQ_PATH" > "$REQ" 2>/dev/null || true
      if [ ! -s "$REQ" ]; then
        TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | jq -r .tag_name)
        curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/$(basename "$REQ_PATH")" -o "$REQ" \
          || curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/requirements.txt" -o "$REQ" \
          || { echo "could not obtain requirements for ${PKG}" >&2; exit 1; }
      fi
      python3 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { _linux_build_failed "$platform" "$outdir"; return; }

  _write_deb_installer "$outdir"
  _stage_openbao "$outdir" deb
  log "[$platform] done — $(find "$outdir/apt-deps" -name '*.deb' | wc -l) deps + $(find "$outdir/wheels" -name '*.whl' | wc -l) wheels"
}

# ----- Fedora / RHEL / openSUSE / Alpine -----------------------------------
#
# All four use the same pattern as Debian: spin up a distro container,
# fetch the platform-specific installer from GitHub Releases, resolve
# the native-package dep closure with the distro's tooling, pip-wheel
# the Python deps.  The asset-name regex differs per platform because
# the build matrix uses different filename conventions; comments call
# out the assumption so it's clear what to adjust if releases use
# different names.

build_fedora() {
  local platform="$1"           # e.g. fedora-40
  local ver="${platform#fedora-}"
  local outdir="$STAGING_DIR/linux-${platform}"
  mkdir -p "$outdir"

  log "[$platform] docker run fedora:$ver to fetch .rpm + dnf deps + wheels"
  docker run --rm \
    -v "$outdir:/out" \
    -e PKG="$PKG_NAME" \
    -e REPO="$(_gh_owner_repo)" \
    -e REQ_PATH_RPM="${REQ_PATH_IN_RPM#/}" \
    -e EXTRAS="$EXTRAS_RPM" \
    "fedora:$ver" bash -euxc '
      # dnf-plugins-core provides the `dnf download` subcommand —
      # absent in stock fedora images, so without it the download
      # step below silently no-ops and we ship a Fedora bundle with
      # only the main .rpm and no transitive deps.
      dnf install -y -q \
        curl jq python3 python3-pip python3-devel \
        gcc libffi-devel openssl-devel libpq-devel \
        cpio rpm-build dnf-plugins-core
      cd /out
      mkdir -p rpm-deps wheels

      # Asset name pattern: build-centos (build-and-release.yml:353)
      # produces ONE generic ``sysmanage-agent-<ver>-*.rpm`` with no
      # platform discriminator in the filename — it covers Fedora/RHEL
      # both.  We pick "any .rpm that does NOT have opensuse or sles in
      # the name" (those come from build-opensuse and are NOT cross-
      # compatible).
      ASSET_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
                  | jq -r ".assets[] | select(.name | test(\"\\\\.rpm$\")) | select(.name | test(\"opensuse|sles|el9\") | not) | .browser_download_url" \
                  | head -1)
      [ -n "$ASSET_URL" ] || { echo "no generic .rpm in releases for $REPO" >&2; exit 1; }
      curl -fsSL -o "${PKG}.rpm" "$ASSET_URL"

      # Download the full dependency closure of the rpm into rpm-deps.
      # This must work on BOTH dnf4 (Fedora 40, Rocky 9) and dnf5
      # (Fedora 41+): dnf5 rejects ``dnf download --resolve ./local.rpm``
      # ("No package ./x.rpm available") and ``dnf install --downloadonly``
      # does not take --destdir.  Portable path: read the rpm Requires and
      # let dnf download those by name (plus their transitive deps) from
      # the repos; the main rpm itself is already fetched above.
      REQS=$(rpm -qpR "${PKG}.rpm" | awk "{print \$1}" \
             | grep -vE "^(rpmlib|/|python\\(abi\\))" | sort -u)
      dnf download --resolve --destdir=rpm-deps $REQS || true
      # Pull the extra product-specific roots (e.g. postgresql-server)
      # and their transitive deps too.
      for _extra in $EXTRAS; do
        dnf download --resolve --destdir=rpm-deps "$_extra" || true
      done
      # Drop the main package out of rpm-deps if dnf staged it there.
      find rpm-deps -maxdepth 1 -name "${PKG}-*.rpm" -delete 2>/dev/null || true

      REQ=/tmp/req.txt
      rpm2cpio "${PKG}.rpm" | cpio -id "./${REQ_PATH_RPM}" 2>/dev/null || true
      cp "./${REQ_PATH_RPM}" "$REQ" 2>/dev/null || true
      if [ ! -s "$REQ" ]; then
        TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | jq -r .tag_name)
        curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/$(basename "$REQ_PATH_RPM")" -o "$REQ" \
          || curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/requirements.txt" -o "$REQ" \
          || { echo "could not obtain requirements for ${PKG}" >&2; exit 1; }
      fi
      python3 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { _linux_build_failed "$platform" "$outdir"; return; }

  _write_rpm_installer "$outdir" "dnf"
  _stage_openbao "$outdir" rpm
  log "[$platform] done — $(find "$outdir/rpm-deps" -name '*.rpm' | wc -l) deps + $(find "$outdir/wheels" -name '*.whl' | wc -l) wheels"
}

# RHEL/Rocky/Alma — Rocky Linux 9 is the freely-available stand-in.
build_rhel() {
  local platform="$1"           # e.g. rhel-9
  local ver="${platform#rhel-}"
  local outdir="$STAGING_DIR/linux-${platform}"
  mkdir -p "$outdir"

  log "[$platform] docker run rockylinux:$ver to fetch .rpm + dnf deps + wheels"
  docker run --rm \
    -v "$outdir:/out" \
    -e PKG="$PKG_NAME" \
    -e REPO="$(_gh_owner_repo)" \
    -e REQ_PATH_RPM="${REQ_PATH_IN_RPM#/}" \
    -e EXTRAS="$EXTRAS_RPM" \
    "rockylinux:$ver" bash -euxc '
      # dnf-plugins-core provides `dnf download`; Rocky 9 stock image
      # ships without it.  Use python3.12 (AppStream) — Rocky/RHEL 9 ships
      # python3 = 3.9 by default, but the server requires >= 3.12 (e.g.
      # fastapi 0.129.0 dropped 3.9), so wheels must be built for 3.12.
      dnf install -y -q --allowerasing \
        curl jq python3.12 python3.12-pip python3.12-devel \
        gcc libffi-devel openssl-devel libpq-devel \
        cpio dnf-plugins-core
      cd /out
      mkdir -p rpm-deps wheels

      # Prefer the EL9-specific RPM (sysmanage-<ver>-1.el9.x86_64.rpm) —
      # its python3.12 deps resolve on Rocky/RHEL 9, where the generic
      # CentOS RPM (Requires: python3 >= 3.12) is unsatisfiable.  Fall
      # back to the generic non-openSUSE RPM for older releases that
      # predate the el9 build.
      ASSET_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
                  | jq -r ".assets[] | select(.name | test(\"\\\\.el9\\\\..*\\\\.rpm$\")) | .browser_download_url" \
                  | head -1)
      if [ -z "$ASSET_URL" ]; then
        ASSET_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
                    | jq -r ".assets[] | select(.name | test(\"\\\\.rpm$\")) | select(.name | test(\"opensuse|sles|el9\") | not) | .browser_download_url" \
                    | head -1)
      fi
      [ -n "$ASSET_URL" ] || { echo "no el9/generic .rpm in releases for $REPO" >&2; exit 1; }
      curl -fsSL -o "${PKG}.rpm" "$ASSET_URL"

      # Download the full dependency closure of the rpm into rpm-deps.
      # Portable across dnf4 (Rocky 9) and dnf5: read the rpm Requires and
      # let dnf download those by name (plus their transitive deps); the
      # main rpm itself is already fetched above.
      REQS=$(rpm -qpR "${PKG}.rpm" | awk "{print \$1}" \
             | grep -vE "^(rpmlib|/|python\\(abi\\))" | sort -u)
      dnf download --resolve --destdir=rpm-deps $REQS || true
      for _extra in $EXTRAS; do
        dnf download --resolve --destdir=rpm-deps "$_extra" || true
      done
      find rpm-deps -maxdepth 1 -name "${PKG}-*.rpm" -delete 2>/dev/null || true

      REQ=/tmp/req.txt
      rpm2cpio "${PKG}.rpm" | cpio -id "./${REQ_PATH_RPM}" 2>/dev/null || true
      cp "./${REQ_PATH_RPM}" "$REQ" 2>/dev/null || true
      if [ ! -s "$REQ" ]; then
        TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | jq -r .tag_name)
        curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/$(basename "$REQ_PATH_RPM")" -o "$REQ" \
          || curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/requirements.txt" -o "$REQ" \
          || { echo "could not obtain requirements for ${PKG}" >&2; exit 1; }
      fi
      python3.12 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { _linux_build_failed "$platform" "$outdir"; return; }

  _write_rpm_installer "$outdir" "dnf"
  _stage_openbao "$outdir" rpm
  log "[$platform] done — $(find "$outdir/rpm-deps" -name '*.rpm' | wc -l) deps + $(find "$outdir/wheels" -name '*.whl' | wc -l) wheels"
}

# openSUSE Leap — uses zypper, not dnf.  The build-opensuse matrix in
# the agent workflow targets Leap 15.5; bump as needed.
build_opensuse() {
  local platform="$1"           # opensuse-leap
  local outdir="$STAGING_DIR/linux-${platform}"
  mkdir -p "$outdir"

  log "[$platform] docker run opensuse/leap:15.5 to fetch .rpm + zypper deps + wheels"
  docker run --rm \
    -v "$outdir:/out" \
    -e PKG="$PKG_NAME" \
    -e REPO="$(_gh_owner_repo)" \
    -e REQ_PATH_RPM="${REQ_PATH_IN_RPM#/}" \
    -e EXTRAS="$EXTRAS_RPM" \
    "opensuse/leap:15.5" bash -euxc '
      zypper -nq install -y \
        curl jq python311 python311-pip python311-devel \
        gcc libffi-devel libopenssl-devel postgresql-devel \
        cpio
      cd /out
      mkdir -p rpm-deps wheels

      # build-opensuse (matrix=opensuse-leap) produces a .rpm whose
      # filename contains "opensuse-leap" (build-and-release.yml:1905).
      # tumbleweed/sles have their own variants which we skip here.
      ASSET_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
                  | jq -r ".assets[] | select(.name | test(\"opensuse-leap.*\\\\.rpm$\")) | .browser_download_url" \
                  | head -1)
      [ -n "$ASSET_URL" ] || { echo "no opensuse-leap .rpm in releases for $REPO" >&2; exit 1; }
      curl -fsSL -o "${PKG}.rpm" "$ASSET_URL"

      # zypper does not have a clean "download recursive deps" verb the
      # way dnf does.  Best-effort: use rpm to query Requires, then
      # zypper download each.  This misses transitive closure; for a
      # fully reproducible bundle, rebuild the metadata via createrepo
      # in a follow-up.
      DIRECT_DEPS=$(rpm -qpR "${PKG}.rpm" | awk "{print \$1}" | grep -v "^rpmlib\\|^/" | sort -u)
      zypper -nq --pkg-cache-dir=rpm-deps download $DIRECT_DEPS $EXTRAS 2>/dev/null || true
      find rpm-deps -name "*.rpm" -exec cp {} rpm-deps/ \;
      find rpm-deps -mindepth 2 -type f -name "*.rpm" -delete 2>/dev/null || true
      find rpm-deps -mindepth 1 -type d -empty -delete 2>/dev/null || true

      REQ=/tmp/req.txt
      rpm2cpio "${PKG}.rpm" | cpio -id "./${REQ_PATH_RPM}" 2>/dev/null || true
      cp "./${REQ_PATH_RPM}" "$REQ" 2>/dev/null || true
      if [ ! -s "$REQ" ]; then
        TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | jq -r .tag_name)
        curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/$(basename "$REQ_PATH_RPM")" -o "$REQ" \
          || curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/requirements.txt" -o "$REQ" \
          || { echo "could not obtain requirements for ${PKG}" >&2; exit 1; }
      fi
      python3.11 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { _linux_build_failed "$platform" "$outdir"; return; }

  _write_rpm_installer "$outdir" "zypper"
  _stage_openbao "$outdir" rpm
  log "[$platform] done — $(find "$outdir/rpm-deps" -name '*.rpm' | wc -l) deps + $(find "$outdir/wheels" -name '*.whl' | wc -l) wheels"
}

# Alpine — apk-based, uses musl libc.  Different filename pattern:
# .apk archives instead of .rpm/.deb.
build_alpine() {
  local platform="$1"           # e.g. alpine-3.20
  local ver="${platform#alpine-}"
  local outdir="$STAGING_DIR/linux-${platform}"
  mkdir -p "$outdir"

  log "[$platform] docker run alpine:$ver to fetch .apk + deps + wheels"
  docker run --rm \
    -v "$outdir:/out" \
    -e PKG="$PKG_NAME" \
    -e REPO="$(_gh_owner_repo)" \
    -e REQ_PATH_RPM="${REQ_PATH_IN_RPM#/}" \
    -e EXTRAS="$EXTRAS_APK" \
    "alpine:$ver" sh -euxc '
      apk add --no-cache \
        curl jq python3 py3-pip python3-dev \
        gcc musl-dev libffi-dev openssl-dev postgresql-dev \
        bash
      cd /out
      mkdir -p apk-deps wheels

      # Alpine variants: build-and-release.yml:1806 produces
      # sysmanage-agent-<ver>-alpine<NNN>.apk for alpine 3.19/3.20/3.21.
      # Pick the highest version number (which sorts naturally as the
      # last entry when grouped by alpine<NNN>).
      ASSET_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
                  | jq -r ".assets[] | select(.name | test(\"alpine[0-9]+\\\\.apk$\")) | .browser_download_url" \
                  | sort -V | tail -1)
      [ -n "$ASSET_URL" ] || { echo "no alpine[NNN].apk in releases for $REPO" >&2; exit 1; }
      curl -fsSL -o "${PKG}.apk" "$ASSET_URL"

      # apk fetch --recursive walks the dep tree and writes .apk files
      # into the current dir.  --output-dir is supported by newer apk.
      ( cd apk-deps
        # Need the package metadata in apk DB; build a temp index from
        # the downloaded .apk so apk can resolve its deps.
        for dep in $(tar -xzf "../${PKG}.apk" -O .PKGINFO 2>/dev/null \
                     | awk -F " = " "/^depend = /{print \$2}" \
                     | awk "{print \$1}" | sort -u); do
          apk fetch --recursive --no-cache "$dep" 2>/dev/null || true
        done
        # Product-specific extras (e.g. postgresql for the server).
        for _extra in $EXTRAS; do
          apk fetch --recursive --no-cache "$_extra" 2>/dev/null || true
        done
      )

      # The Alpine package lays the app out under /usr/libexec/sysmanage
      # and (unlike the deb/rpm) does not ship requirements.txt at the
      # deb/rpm path, so extraction from the .apk misses.  Fall back to
      # the canonical requirements.txt from the repo at the released tag
      # — the exact dependency list the venv is built from, independent
      # of how each platform package happens to be laid out.
      REQ=/tmp/req.txt
      tar -xzf "${PKG}.apk" -O "${REQ_PATH_RPM}" > "$REQ" 2>/dev/null || true
      if [ ! -s "$REQ" ]; then
        TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | jq -r .tag_name)
        curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/$(basename "${REQ_PATH_RPM}")" -o "$REQ" \
          || curl -fsSL "https://raw.githubusercontent.com/$REPO/${TAG}/requirements.txt" -o "$REQ" \
          || { echo "could not obtain requirements for ${PKG} (apk + repo fallback both failed)" >&2; exit 1; }
      fi
      python3 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { _linux_build_failed "$platform" "$outdir"; return; }

  # Alpine installer uses apk add --allow-untrusted on local files.
  cat > "$outdir/install.sh" <<EOF
#!/bin/sh
# Per-platform Alpine installer for ${PKG_NAME}.
set -eu
cd "\$(dirname "\$0")"
if ! command -v apk >/dev/null 2>&1; then
  echo "ERROR: apk not found — this subdirectory is for Alpine only." >&2
  exit 2
fi
MAIN_APK="\$(ls -1 *.apk 2>/dev/null | head -1)"
[ -n "\$MAIN_APK" ] || { echo "ERROR: no .apk found" >&2; exit 3; }
# apk-deps/ may be empty — don't let the literal "apk-deps/*.apk"
# reach apk add or it'll error before installing anything.
DEP_COUNT=\$(ls -1 apk-deps/*.apk 2>/dev/null | wc -l)
# OpenBAO ships no .apk; place the bundled static binary so the package
# post-install finds it (offline) instead of trying to download it.
if [ -x openbao/bao ]; then
  sudo install -m 755 openbao/bao /usr/local/bin/bao
fi
echo "Installing \$MAIN_APK + \$DEP_COUNT deps..."
if [ "\$DEP_COUNT" -gt 0 ]; then
  exec sudo env PIP_NO_INDEX=1 PIP_FIND_LINKS="\$(pwd)/wheels" \\
       apk add --no-cache --allow-untrusted apk-deps/*.apk "\$MAIN_APK"
else
  exec sudo env PIP_NO_INDEX=1 PIP_FIND_LINKS="\$(pwd)/wheels" \\
       apk add --no-cache --allow-untrusted "\$MAIN_APK"
fi
EOF
  chmod +x "$outdir/install.sh"
  _stage_openbao "$outdir" binary-linux
  log "[$platform] done — $(find "$outdir/apk-deps" -name '*.apk' | wc -l) deps + $(find "$outdir/wheels" -name '*.whl' | wc -l) wheels"
}

# ----- Win / macOS / BSD: pull pre-built installers from GitHub Releases ---

# GitHub Releases asset names are predictable from the workflow's matrix
# build job — sysmanage-agent_<ver>-windows-x64.msi etc.  We fetch the
# latest tagged release via the GH API (no auth needed for public repos)
# and download the assets matching this platform.

_gh_owner_repo() {
  case "$PRODUCT" in
    server) echo "bceverly/sysmanage" ;;
    agent)  echo "bceverly/sysmanage-agent" ;;
  esac
}

_fetch_latest_release_asset() {
  # $1 = include regex (matched against asset .name), $2 = exclude regex
  # (optional, "" for none), $3 = output path.
  #
  # The previous implementation used awk against the raw JSON and
  # tried to anchor patterns with `$` for end-of-line — but GitHub's
  # pretty-printed JSON puts the URL inside quotes and often followed
  # by a comma, so end-of-line anchors never matched and every BSD/
  # macOS asset silently came back empty.  jq matches against the
  # asset .name field directly, which is the clean filename, so the
  # same regex anchors work as intended.
  local include="$1" exclude="$2" outpath="$3"
  local repo; repo=$(_gh_owner_repo)
  local url
  if [[ -n "$exclude" ]]; then
    url=$(curl -fsSL "https://api.github.com/repos/${repo}/releases/latest" \
          | jq -r --arg inc "$include" --arg exc "$exclude" \
              '.assets[] | select(.name | test($inc)) | select(.name | test($exc) | not) | .browser_download_url' \
          | head -1)
  else
    url=$(curl -fsSL "https://api.github.com/repos/${repo}/releases/latest" \
          | jq -r --arg inc "$include" \
              '.assets[] | select(.name | test($inc)) | .browser_download_url' \
          | head -1)
  fi
  if [[ -z "$url" ]]; then
    return 1
  fi
  curl -fsSL -o "$outpath" "$url"
}

build_windows() {
  local outdir="$STAGING_DIR/windows"
  mkdir -p "$outdir"
  log "[windows] fetching .msi from GitHub Releases"
  # build-windows uploads sysmanage-agent-<ver>-windows-x64.msi and
  # sysmanage-agent-<ver>-windows-arm64.msi (build-and-release.yml:795).
  if _fetch_latest_release_asset 'windows-x64.*\.msi' '' "$outdir/${PKG_NAME}-x64.msi"; then
    log "[windows] got x64 .msi"
  else
    warn "[windows] no windows-x64 .msi found in latest release — skipping"
  fi
  _fetch_latest_release_asset 'windows-arm64.*\.msi' '' "$outdir/${PKG_NAME}-arm64.msi" || true
  _stage_openbao "$outdir" binary-windows
  # README — Windows install can't be scripted from POSIX sh; instruct user.
  cat > "$outdir/install.sh" <<EOF
#!/bin/sh
echo "Windows installer (.msi) is GUI-only.  Open ${PKG_NAME}-x64.msi or"
echo "${PKG_NAME}-arm64.msi from File Explorer to run the install."
EOF
  chmod +x "$outdir/install.sh"
}

build_macos() {
  local outdir="$STAGING_DIR/macos"
  mkdir -p "$outdir"
  log "[macos] fetching .pkg from GitHub Releases"
  # build-macos uploads sysmanage-agent-<ver>-macos.pkg
  # (build-and-release.yml:616).  Must specifically match "macos" since
  # FreeBSD also produces a .pkg but without any platform name.
  if _fetch_latest_release_asset 'macos.*\.pkg' '' "$outdir/${PKG_NAME}.pkg"; then
    log "[macos] got .pkg"
    _stage_openbao "$outdir" binary-darwin
  else
    warn "[macos] no macos .pkg found in latest release — skipping"
  fi
  cat > "$outdir/install.sh" <<EOF
#!/bin/sh
echo "macOS installer (.pkg) — run interactively:"
echo "  sudo installer -pkg ${PKG_NAME}.pkg -target /"
echo "Or double-click the .pkg from Finder."
EOF
  chmod +x "$outdir/install.sh"
}

# BSD builders fetch the platform's pre-built installer from GitHub
# Releases.  Unlike Linux we don't bundle native-package dependencies
# (BSD pkg(8) on the target will resolve its own deps from its own
# repos, which IS available even on air-gapped hosts as long as the
# operator pre-populated /var/db/pkg).  We also don't bundle Python
# wheels: the BSD .pkg is built with its venv vendored.

_write_bsd_installer() {
  local outdir="$1"
  local installer_cmd="$2"   # "pkg add" or "pkg_add"
  cat > "$outdir/install.sh" <<EOF
#!/bin/sh
# Per-platform BSD installer for ${PKG_NAME}.
set -eu
cd "\$(dirname "\$0")"
ARTIFACT="\$(ls -1 *.pkg *.tgz 2>/dev/null | head -1)"
[ -n "\$ARTIFACT" ] || { echo "ERROR: no .pkg/.tgz artifact found" >&2; exit 3; }
# OpenBAO ships no BSD package; place the bundled static binary so the
# package post-install finds it (offline) instead of trying to fetch it.
if [ -x openbao/bao ]; then
  sudo install -m 755 openbao/bao /usr/local/bin/bao 2>/dev/null || \
    { sudo mkdir -p /usr/local/bin && sudo cp openbao/bao /usr/local/bin/bao && sudo chmod 755 /usr/local/bin/bao; }
fi
exec sudo ${installer_cmd} -f "./\$ARTIFACT"
EOF
  chmod +x "$outdir/install.sh"
}

build_freebsd() {
  local outdir="$STAGING_DIR/freebsd"
  mkdir -p "$outdir"
  log "[freebsd] fetching .pkg from GitHub Releases"
  # build-freebsd uploads sysmanage-agent-<ver>.pkg with NO platform
  # discriminator in the name (build-and-release.yml:950).  macOS also
  # publishes a .pkg, so the include pattern matches any .pkg and the
  # exclude pattern rejects the macOS one.
  if _fetch_latest_release_asset '\.pkg$' 'macos' "$outdir/${PKG_NAME}.pkg"; then
    log "[freebsd] got .pkg"
    _write_bsd_installer "$outdir" "pkg add"
    _stage_openbao "$outdir" binary-freebsd
  else
    warn "[freebsd] no non-macOS .pkg found in latest release — skipping"
    _safe_rmdir "$outdir"
  fi
}

build_netbsd() {
  local outdir="$STAGING_DIR/netbsd"
  mkdir -p "$outdir"
  log "[netbsd] fetching .tgz from GitHub Releases"
  # build-netbsd uploads sysmanage-agent-<ver>.tgz with NO platform
  # discriminator (build-and-release.yml:1148).  OpenBSD also produces
  # .tgz files (with "openbsd" in the name), so exclude those.
  if _fetch_latest_release_asset '\.tgz$' 'openbsd' "$outdir/${PKG_NAME}.tgz"; then
    log "[netbsd] got .tgz"
    _write_bsd_installer "$outdir" "pkg_add"
    _stage_openbao "$outdir" binary-netbsd
  else
    warn "[netbsd] no non-openbsd .tgz found in latest release — skipping"
    _safe_rmdir "$outdir"
  fi
}

build_openbsd() {
  local outdir="$STAGING_DIR/openbsd"
  mkdir -p "$outdir"
  log "[openbsd] fetching .tgz from GitHub Releases"
  # OpenBSD ships per-release builds: sysmanage-agent-<ver>-openbsd75.tgz,
  # ...-openbsd76.tgz, ...-openbsd77.tgz (build-and-release.yml:1667).
  # We currently grab the first match — typically the newest by upload
  # order — which lands the .tgz matching the latest supported OpenBSD
  # release.  The bundle dispatcher uses ``uname -r`` to confirm match.
  if _fetch_latest_release_asset 'openbsd[0-9]+\.tgz$' '' "$outdir/${PKG_NAME}.tgz"; then
    log "[openbsd] got .tgz"
    _write_bsd_installer "$outdir" "pkg_add"
  else
    warn "[openbsd] no openbsd[NN].tgz found in latest release — skipping"
    _safe_rmdir "$outdir"
  fi
}

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

# Dispatcher: route each platform key to its builder function.
build_one() {
  local p="$1"
  case "$p" in
    ubuntu-*)   build_ubuntu_like "$p" ;;
    debian-*)   build_debian_like "$p" ;;
    fedora-*)   build_fedora "$p" ;;
    rhel-*)     build_rhel "$p" ;;
    opensuse-*) build_opensuse "$p" ;;
    alpine-*)   build_alpine "$p" ;;
    windows)    build_windows ;;
    macos)      build_macos ;;
    freebsd)    build_freebsd ;;
    netbsd)     build_netbsd ;;
    openbsd)    build_openbsd ;;
    *) warn "unknown platform key: $p — skipping" ;;
  esac
}

# Run all platforms (serial or parallel based on $PARALLEL).
if [[ "$PARALLEL" -le 1 ]]; then
  for p in $PLATFORMS; do
    build_one "$p"
  done
else
  log "Running $PARALLEL platforms in parallel"
  pids=()
  for p in $PLATFORMS; do
    build_one "$p" &
    pids+=($!)
    if (( ${#pids[@]} >= PARALLEL )); then
      wait -n
      # Drop completed pids — best-effort, bash doesn't tell us which.
      pids=($(jobs -rp))
    fi
  done
  wait
fi

# ---------------------------------------------------------------------------
# Drop dispatcher install.sh at staging root + build the ISO
# ---------------------------------------------------------------------------

cp "$DISPATCHER_SH" "$STAGING_DIR/install.sh"
chmod +x "$STAGING_DIR/install.sh"

# Per-platform result summary.  A bundle that silently drops platforms
# is worse than a failed build: it installs fine on the platforms that
# DID make it and mysteriously fails offline on the ones that didn't.
# But the two failure classes are NOT equal:
#   * Linux platforms (ubuntu/debian/fedora/rhel/opensuse/alpine) carry
#     the .deb/.rpm + wheel dependency closures — a Linux failure means
#     a genuinely broken bundle, so it's FATAL (this is the OOM/silent-
#     hollow-bundle case we're guarding against).
#   * Release-asset platforms (windows/macos/*bsd) just fetch a prebuilt
#     installer from GitHub Releases; one being absent is expected (e.g.
#     the server product ships no Windows installer) and is a WARNING,
#     not a build failure.
_built=(); _failed_linux=(); _failed_asset=()
for p in $PLATFORMS; do
  if [[ -f "$STAGING_DIR/$(_outdir_for_platform "$p")/install.sh" ]]; then
    _built+=("$p")
  elif _is_linux_platform "$p"; then
    _failed_linux+=("$p")
  else
    _failed_asset+=("$p")
  fi
done

log "============================================================"
log "Bundle platform summary for '$PRODUCT':"
log "  succeeded     (${#_built[@]}): ${_built[*]:-none}"
(( ${#_failed_linux[@]} )) \
  && warn "  FAILED Linux  (${#_failed_linux[@]}): ${_failed_linux[*]}  <-- missing dependency closures"
(( ${#_failed_asset[@]} )) \
  && warn "  no installer  (${#_failed_asset[@]}): ${_failed_asset[*]}  (not published for this product — skipped)"
{ (( ${#_failed_linux[@]} )) || (( ${#_failed_asset[@]} )); } && [[ -d "$BUNDLE_LOG_DIR" ]] \
  && warn "  failure logs: $BUNDLE_LOG_DIR/<platform>.log"
log "============================================================"

if (( ${#_built[@]} == 0 )); then
  die "no platforms produced output — every builder failed or stubbed (logs: $BUNDLE_LOG_DIR)"
fi
if (( ${#_failed_linux[@]} )) && [[ "$ALLOW_PARTIAL_BUNDLE" != "1" ]]; then
  die "${#_failed_linux[@]} Linux platform(s) failed — the ISO would be missing their dependency closures and fail to install offline.
Fix the failures above (see $BUNDLE_LOG_DIR), or set ALLOW_PARTIAL_BUNDLE=1 to ship a partial bundle on purpose."
fi

PLATFORMS_BUILT=${#_built[@]}
log "Platforms staged: $PLATFORMS_BUILT"
log "Staging tree size: $(du -sh "$STAGING_DIR" | cut -f1)"

# README at root, links to dispatcher.
cat > "$STAGING_DIR/README.txt" <<EOF
SysManage ${PRODUCT} — air-gap install bundle (multi-OS)
=========================================================

Built : $(date -u +'%Y-%m-%dT%H:%M:%SZ')
Size  : $(du -sh "$STAGING_DIR" | cut -f1)

Install on the air-gapped host:

  sudo mount -o loop sysmanage-${PRODUCT}-bundle.iso /mnt
  # or if the ISO is on physical media:
  sudo mount /dev/sr0 /mnt
  sudo /mnt/install.sh

That dispatcher detects the host OS and runs the right platform's
installer from the appropriate subdirectory.

Platforms included in this bundle (one subdirectory each):

$(cd "$STAGING_DIR" && ls -d */ 2>/dev/null | sed 's|/||' | sed 's/^/  /')
EOF

# Build the ISO.
if [[ -e "$ISO_PATH" ]]; then
  rm -f "$ISO_PATH" 2>/dev/null || true
fi
log "Building ISO with xorrisofs"
xorrisofs -quiet -o "$ISO_PATH" -V "$ISO_LABEL" -r -J "$STAGING_DIR"

log "Done."
log "ISO : $ISO_PATH ($(du -h "$ISO_PATH" | cut -f1))"
