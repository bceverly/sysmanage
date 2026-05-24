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
  server|agent) ;;
  *)
    echo "usage: $0 server|agent" >&2
    exit 2
    ;;
esac

# Map abstract product → concrete package details.
case "$PRODUCT" in
  server)
    PKG_NAME="sysmanage"
    PPA_NAME="bceverly/sysmanage"
    REQ_PATH_IN_DEB="./opt/sysmanage/requirements.txt"
    REQ_PATH_IN_RPM="/opt/sysmanage/requirements.txt"
    ;;
  agent)
    PKG_NAME="sysmanage-agent"
    PPA_NAME="bceverly/sysmanage-agent"
    REQ_PATH_IN_DEB="./opt/sysmanage-agent/requirements-prod.txt"
    REQ_PATH_IN_RPM="/opt/sysmanage-agent/requirements-prod.txt"
    ;;
esac

DEST_DIR="${DEST_DIR:-/tmp}"
STAGING_DIR="${STAGING_DIR:-$(mktemp -d -t sysmanage-bundle-XXXXXX)}"
PARALLEL="${PARALLEL:-1}"
PLATFORMS_ALL="ubuntu-jammy ubuntu-noble ubuntu-questing ubuntu-resolute debian-bookworm fedora-40 fedora-41 rhel-9 opensuse-leap alpine-3.20 freebsd netbsd openbsd macos windows"
PLATFORMS="${PLATFORMS:-$PLATFORMS_ALL}"
ISO_LABEL="SYSMANAGE-$(echo "$PRODUCT" | tr a-z A-Z)"
ISO_PATH="${DEST_DIR}/sysmanage-${PRODUCT}-bundle.iso"

# Where on the host THIS script lives — needed to find installer assets
# (the dispatcher install.sh) regardless of the cwd we're invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISPATCHER_SH="${SCRIPT_DIR}/../installer/airgap-bundle/install.sh"

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

for cmd in docker curl awk xorrisofs; do
  command -v "$cmd" >/dev/null 2>&1 \
    || die "missing required tool: $cmd
Install with:  sudo apt install xorriso docker.io curl"
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

echo "Installing \$MAIN_DEB + \$(ls -1 apt-deps/*.deb | wc -l) deps..."
exec sudo env PIP_NO_INDEX=1 PIP_FIND_LINKS="\$(pwd)/wheels" \\
     dpkg -i apt-deps/*.deb "\$MAIN_DEB"
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

echo "Installing \$MAIN_RPM + \$(ls -1 rpm-deps/*.rpm 2>/dev/null | wc -l) deps..."
exec sudo env PIP_NO_INDEX=1 PIP_FIND_LINKS="\$(pwd)/wheels" \\
     ${tool} install -y --allowerasing rpm-deps/*.rpm "\$MAIN_RPM"
EOF
  chmod +x "$outdir/install.sh"
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
      cd apt-deps
      apt-cache depends --recurse --no-recommends --no-suggests \
                        --no-conflicts --no-breaks --no-replaces --no-enhances \
                        $DIRECT \
        | awk "/^\\w/ {print \$1}" | sort -u \
        | xargs -n50 apt-get download 2>/dev/null || true
      find . -maxdepth 1 -name "*.deb" ! -name "*_amd64.deb" ! -name "*_all.deb" -delete
      cd ..

      # requirements.txt → wheels (pip wheel compiles sdists too)
      REQ=/tmp/req.txt
      dpkg-deb --fsys-tarfile "$PKG"_*.deb | tar -xO "$REQ_PATH" > "$REQ"
      python3 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { tail -30 "$outdir/build.log"; die "[$platform] docker build failed (log: $outdir/build.log)"; }

  _write_deb_installer "$outdir"
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
      # by default in the base image).
      DIRECT="$(dpkg-deb -f ${PKG}.deb Depends | tr "," "\n" \
                | awk "{print \$1}" | grep -v "^\\\${" | grep -vE "^$" | sort -u)"
      cd apt-deps
      apt-cache depends --recurse --no-recommends --no-suggests \
                        --no-conflicts --no-breaks --no-replaces --no-enhances \
                        $DIRECT \
        | awk "/^\\w/ {print \$1}" | sort -u \
        | xargs -n50 apt-get download 2>/dev/null || true
      find . -maxdepth 1 -name "*.deb" ! -name "*_amd64.deb" ! -name "*_all.deb" -delete
      cd ..

      REQ=/tmp/req.txt
      dpkg-deb --fsys-tarfile ${PKG}.deb | tar -xO "$REQ_PATH" > "$REQ"
      python3 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { tail -30 "$outdir/build.log"; warn "[$platform] docker build failed (log: $outdir/build.log) — skipping"; rm -rf "$outdir"; return; }

  _write_deb_installer "$outdir"
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
    "fedora:$ver" bash -euxc '
      dnf install -y -q \
        curl jq python3 python3-pip python3-devel \
        gcc libffi-devel openssl-devel libpq-devel \
        cpio rpm-build
      cd /out
      mkdir -p rpm-deps wheels

      # Asset name pattern: build-centos (build-and-release.yml:353)
      # produces ONE generic ``sysmanage-agent-<ver>-*.rpm`` with no
      # platform discriminator in the filename — it covers Fedora/RHEL
      # both.  We pick "any .rpm that does NOT have opensuse or sles in
      # the name" (those come from build-opensuse and are NOT cross-
      # compatible).
      ASSET_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
                  | jq -r ".assets[] | select(.name | test(\"\\\\.rpm$\")) | select(.name | test(\"opensuse|sles\") | not) | .browser_download_url" \
                  | head -1)
      [ -n "$ASSET_URL" ] || { echo "no generic .rpm in releases for $REPO" >&2; exit 1; }
      curl -fsSL -o "${PKG}.rpm" "$ASSET_URL"

      # dnf download with --resolve walks recursive deps for us.
      dnf download --resolve --destdir=rpm-deps "./${PKG}.rpm" \
        || dnf download --resolve --destdir=rpm-deps "${PKG}"
      # Drop the main package out of rpm-deps if dnf staged it there.
      find rpm-deps -maxdepth 1 -name "${PKG}-*.rpm" -delete 2>/dev/null || true

      REQ=/tmp/req.txt
      rpm2cpio "${PKG}.rpm" | cpio -id "./${REQ_PATH_RPM}" 2>/dev/null
      cp "./${REQ_PATH_RPM}" "$REQ"
      python3 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { tail -30 "$outdir/build.log"; warn "[$platform] docker build failed (log: $outdir/build.log) — skipping"; rm -rf "$outdir"; return; }

  _write_rpm_installer "$outdir" "dnf"
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
    "rockylinux:$ver" bash -euxc '
      dnf install -y -q --allowerasing \
        curl jq python3 python3-pip python3-devel \
        gcc libffi-devel openssl-devel libpq-devel \
        cpio
      cd /out
      mkdir -p rpm-deps wheels

      # RHEL/Rocky/Alma share the same generic ``sysmanage-agent-<ver>-*.rpm``
      # build-centos produces — the .rpm has no "el<N>" discriminator
      # (build-and-release.yml:353).  Pick any .rpm that is NOT one of
      # the openSUSE/SLES variants.
      ASSET_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
                  | jq -r ".assets[] | select(.name | test(\"\\\\.rpm$\")) | select(.name | test(\"opensuse|sles\") | not) | .browser_download_url" \
                  | head -1)
      [ -n "$ASSET_URL" ] || { echo "no generic .rpm in releases for $REPO" >&2; exit 1; }
      curl -fsSL -o "${PKG}.rpm" "$ASSET_URL"

      dnf download --resolve --destdir=rpm-deps "./${PKG}.rpm" \
        || dnf download --resolve --destdir=rpm-deps "${PKG}"
      find rpm-deps -maxdepth 1 -name "${PKG}-*.rpm" -delete 2>/dev/null || true

      REQ=/tmp/req.txt
      rpm2cpio "${PKG}.rpm" | cpio -id "./${REQ_PATH_RPM}" 2>/dev/null
      cp "./${REQ_PATH_RPM}" "$REQ"
      python3 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { tail -30 "$outdir/build.log"; warn "[$platform] docker build failed (log: $outdir/build.log) — skipping"; rm -rf "$outdir"; return; }

  _write_rpm_installer "$outdir" "dnf"
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
      zypper -nq --pkg-cache-dir=rpm-deps download $DIRECT_DEPS 2>/dev/null || true
      find rpm-deps -name "*.rpm" -exec cp {} rpm-deps/ \;
      find rpm-deps -mindepth 2 -type f -name "*.rpm" -delete 2>/dev/null || true
      find rpm-deps -mindepth 1 -type d -empty -delete 2>/dev/null || true

      REQ=/tmp/req.txt
      rpm2cpio "${PKG}.rpm" | cpio -id "./${REQ_PATH_RPM}" 2>/dev/null
      cp "./${REQ_PATH_RPM}" "$REQ"
      python3.11 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { tail -30 "$outdir/build.log"; warn "[$platform] docker build failed (log: $outdir/build.log) — skipping"; rm -rf "$outdir"; return; }

  _write_rpm_installer "$outdir" "zypper"
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
      )

      REQ=/tmp/req.txt
      tar -xzf "${PKG}.apk" -O "${REQ_PATH_RPM}" > "$REQ" 2>/dev/null \
        || { echo "no requirements file at ${REQ_PATH_RPM} inside ${PKG}.apk" >&2; exit 1; }
      python3 -m pip wheel --wheel-dir wheels -r "$REQ" pip setuptools wheel
    ' >"$outdir/build.log" 2>&1 \
    || { tail -30 "$outdir/build.log"; warn "[$platform] docker build failed (log: $outdir/build.log) — skipping"; rm -rf "$outdir"; return; }

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
exec sudo env PIP_NO_INDEX=1 PIP_FIND_LINKS="\$(pwd)/wheels" \\
     apk add --no-cache --allow-untrusted apk-deps/*.apk "\$MAIN_APK"
EOF
  chmod +x "$outdir/install.sh"
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
  # $1 = include regex, $2 = exclude regex (optional, "" for none), $3 = output path
  #
  # Asset name patterns are derived from build-and-release.yml's release
  # job (uploads ``release-files/*``).  The deploy-docs-repo step in
  # that workflow shows the literal filename globs for each platform —
  # this helper's regex needs to match those.  See the per-builder
  # comments for the exact pattern each platform uses.
  local include="$1" exclude="$2" outpath="$3"
  local repo; repo=$(_gh_owner_repo)
  local url
  url=$(curl -fsSL "https://api.github.com/repos/${repo}/releases/latest" \
        | awk -v inc="$include" -v exc="$exclude" '
            /"browser_download_url"/ && $0 ~ inc {
              if (exc != "" && $0 ~ exc) next
              print $2; exit
            }' \
        | tr -d '",')
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
  else
    warn "[freebsd] no non-macOS .pkg found in latest release — skipping"
    rm -rf "$outdir"
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
  else
    warn "[netbsd] no non-openbsd .tgz found in latest release — skipping"
    rm -rf "$outdir"
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
    rm -rf "$outdir"
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

# Sanity check: at least one platform produced output.
PLATFORMS_BUILT=$(find "$STAGING_DIR" -maxdepth 1 -mindepth 1 -type d | wc -l)
[[ "$PLATFORMS_BUILT" -gt 0 ]] \
  || die "no platforms produced output — every builder failed or stubbed"

log "Platforms staged: $PLATFORMS_BUILT"
log "Staging tree size: $(du -sh "$STAGING_DIR" | cut -f1)"

# README at root, links to dispatcher.
cat > "$STAGING_DIR/README.txt" <<EOF
SysManage ${PRODUCT} — air-gap install bundle (multi-OS)
=========================================================

Built : $(date -u +'%Y-%m-%dT%H:%M:%SZ')
Size  : $(du -sh "$STAGING_DIR" | cut -f1)

Install on the air-gapped host:

  sudo mount /dev/sr1 /mnt          # or wherever this ISO mounts
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
