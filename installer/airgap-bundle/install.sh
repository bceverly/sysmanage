#!/bin/sh
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# install.sh — air-gap bundle dispatcher.  Detects the host OS, maps it
# to one of the bundle's per-platform subdirectories, and runs the
# platform-specific install script there.
#
# This file lives at the ROOT of the mega-ISO produced by
# scripts/buildAirGapBundle.sh.  Run from the mounted ISO directory:
#
#     sudo /mnt/install.sh
#
# Each platform-specific subdirectory is laid out as:
#
#     <subdir>/install.sh          # platform-specific installer
#     <subdir>/<package files>     # .deb/.rpm/.apk/.pkg/.msi/etc.
#     <subdir>/wheels/             # Python wheels (Linux only)
#     <subdir>/apt-deps/ or deps/  # native package dependencies
#
# Adding a new platform: drop a new <subdir> with its own install.sh and
# add a case-branch below.  No central registry to keep in sync.
#
# POSIX sh — not bash — because Alpine ships only sh + busybox by default.

set -eu

# ---------------------------------------------------------------------------
# Where am I?
# ---------------------------------------------------------------------------

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SELF_DIR"

err() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }
log() { printf '\033[1;36m[install]\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------------------
# OS detection
# ---------------------------------------------------------------------------

OS_ID=""
OS_VERSION=""
OS_LIKE=""

if [ -f /etc/os-release ]; then
  # Linux: rely on os-release ID + VERSION_ID.
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-}"
  OS_VERSION="${VERSION_ID:-}"
  OS_LIKE="${ID_LIKE:-}"
elif command -v uname >/dev/null 2>&1; then
  case "$(uname -s)" in
    Darwin)  OS_ID="macos";  OS_VERSION="$(sw_vers -productVersion 2>/dev/null || echo '')" ;;
    FreeBSD) OS_ID="freebsd"; OS_VERSION="$(uname -r)" ;;
    NetBSD)  OS_ID="netbsd";  OS_VERSION="$(uname -r)" ;;
    OpenBSD) OS_ID="openbsd"; OS_VERSION="$(uname -r)" ;;
    *)       OS_ID="$(uname -s | tr '[:upper:]' '[:lower:]')" ;;
  esac
fi

log "Detected: id=${OS_ID:-?} version=${OS_VERSION:-?}"

# ---------------------------------------------------------------------------
# Map OS to bundle subdirectory
# ---------------------------------------------------------------------------

SUBDIR=""
case "${OS_ID}:${OS_VERSION}" in
  ubuntu:22.04*) SUBDIR=linux-ubuntu-jammy    ;;
  ubuntu:24.04*) SUBDIR=linux-ubuntu-noble    ;;
  ubuntu:25.10*) SUBDIR=linux-ubuntu-questing ;;
  ubuntu:26.04*) SUBDIR=linux-ubuntu-resolute ;;
  debian:12*)    SUBDIR=linux-debian-bookworm ;;
  debian:13*)    SUBDIR=linux-debian-trixie   ;;
  fedora:40*)    SUBDIR=linux-fedora-40       ;;
  fedora:41*)    SUBDIR=linux-fedora-41       ;;
  rhel:9*|rocky:9*|almalinux:9*|centos:9*)
                 SUBDIR=linux-rhel-9          ;;
  opensuse-leap:15*|sles:15*)
                 SUBDIR=linux-opensuse-leap   ;;
  alpine:3.*)
    # Builder writes to linux-alpine-<ver> (e.g. linux-alpine-3.20).
    # Pick the first matching subdir actually present in the bundle.
    for d in "$SELF_DIR"/linux-alpine-*; do
      [ -d "$d" ] && SUBDIR="$(basename "$d")" && break
    done
    ;;
  freebsd:*)     SUBDIR=freebsd               ;;
  netbsd:*)      SUBDIR=netbsd                ;;
  openbsd:*)     SUBDIR=openbsd               ;;
  macos:*)       SUBDIR=macos                 ;;
  *)
    # Fall back to ID_LIKE for derivatives we haven't enumerated.
    case " $OS_LIKE " in
      *' debian '*) SUBDIR=linux-debian-bookworm ;;
      *' rhel '*|*' fedora '*) SUBDIR=linux-rhel-9 ;;
      *) ;;
    esac
    ;;
esac

if [ -z "$SUBDIR" ] || [ ! -d "$SELF_DIR/$SUBDIR" ]; then
  err "Unsupported or unrecognised OS: id=${OS_ID:-?} version=${OS_VERSION:-?}"
  err "Supported subdirectories present in this bundle:"
  for d in "$SELF_DIR"/linux-* "$SELF_DIR"/freebsd "$SELF_DIR"/netbsd \
           "$SELF_DIR"/openbsd "$SELF_DIR"/macos "$SELF_DIR"/windows; do
    [ -d "$d" ] && err "  $(basename "$d")"
  done
  exit 2
fi

# ---------------------------------------------------------------------------
# Hand off to platform installer
# ---------------------------------------------------------------------------

PLATFORM_INSTALLER="$SELF_DIR/$SUBDIR/install.sh"
if [ ! -x "$PLATFORM_INSTALLER" ]; then
  err "Bundle is missing $SUBDIR/install.sh (or it's not executable)."
  exit 3
fi

log "Running $SUBDIR/install.sh"
cd "$SELF_DIR/$SUBDIR"
exec "$PLATFORM_INSTALLER" "$@"
