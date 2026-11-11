#!/bin/sh
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# install-python-linux.sh -- find (or install) the Python the SysManage
# server's virtual environment is built from, and print its path.
#
# The server needs Python 3.11 or newer.  Its dependencies' security fixes
# ship only for 3.11+ (Pillow 13, dnspython 2.9), so on Python 3.10 they
# stay on releases with known, unfixed vulnerabilities -- and the server
# runs uploaded images through Pillow.  Ubuntu 22.04 (jammy) ships 3.10;
# its own python3.11 package is a release candidate (3.11.0~rc1) in
# universe that has never had a security update.  So where the system
# Python is too old, the server brings its own: a pinned
# python-build-standalone build, installed under /opt/sysmanage/python.
#
# Shipped at /usr/share/sysmanage/python/ (root-owned, like the OpenBAO
# helper: root runs it).
#
# Usage:
#   install-python-linux.sh [--prefix DIR] [--keep-archive DIR]
#
#   Prints the absolute path of the interpreter to use on stdout; everything
#   else goes to stderr.  Exits nonzero when no suitable Python can be had.
#
#   --prefix DIR        where a bundled Python is installed
#                       (default /opt/sysmanage/python)
#   --keep-archive DIR  also copy the verified archive into DIR (the
#                       air-gap bundle builder uses this to carry it)
#
# Order:
#   1. the system python3 (or python3.N) when it is 3.11 or newer -> use it
#   2. a Python this script installed earlier, still the pinned build
#   3. the pinned archive from $SYSMANAGE_PYTHON_BUNDLE (air-gap bundle)
#   4. the pinned archive downloaded from python-build-standalone's
#      GitHub release
#   An archive is installed only when its sha256 matches the value pinned
#   below, wherever it came from.  Never pipes a download into a shell.

PBS_TAG="20261110"
PBS_PYTHON="3.12.16"
PBS_URL="${SYSMANAGE_PYTHON_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}}"
MIN_MINOR=11

PREFIX="/opt/sysmanage/python"
KEEP_DIR=""
BUNDLE_DIR="${SYSMANAGE_PYTHON_BUNDLE:-/opt/sysmanage/installer/python}"

say() { printf '%s\n' "$*" >&2; }
warn() { printf '[!] %s\n' "$*" >&2; }

while [ $# -gt 0 ]; do
	case "$1" in
		--prefix) PREFIX="$2"; shift 2 ;;
		--keep-archive) KEEP_DIR="$2"; shift 2 ;;
		-h|--help) say "usage: $0 [--prefix DIR] [--keep-archive DIR]"; exit 0 ;;
		*) say "usage: $0 [--prefix DIR] [--keep-archive DIR]"; exit 2 ;;
	esac
done

# The pinned archive and its sha256 for this machine's architecture.
# From SHA256SUMS of release $PBS_TAG.
case "$(uname -m)" in
	x86_64|amd64)
		TRIPLE="x86_64-unknown-linux-gnu"
		SHA256="6a9e62dad033790aef722dbd370e0ce76ce17b73627ba3ae679f537049350b39" ;;
	aarch64|arm64)
		TRIPLE="aarch64-unknown-linux-gnu"
		SHA256="b6a41defec4975d94b4ff1950236e7383e5c02ba40ea48c9ec33c66087a35aab" ;;
	riscv64)
		TRIPLE="riscv64-unknown-linux-gnu"
		SHA256="bda9b504221e23b7670a20bcacfa989273cfdc20dfda7d9e4d441c44fd83fd6f" ;;
	ppc64le)
		TRIPLE="ppc64le-unknown-linux-gnu"
		SHA256="51cd1c86949dfeb5e8afc6019e6049779ec5b63f6706619f79bc46c179c6454d" ;;
	s390x)
		TRIPLE="s390x-unknown-linux-gnu"
		SHA256="7fa92933a7fc0a4db002188010eadffec9fe60fb337bb1dfe4b65a7d93ee1661" ;;
	*)
		TRIPLE=""
		SHA256="" ;;
esac
ARCHIVE="cpython-${PBS_PYTHON}+${PBS_TAG}-${TRIPLE}-install_only_stripped.tar.gz"
STAMP="$PREFIX/.sysmanage-python"

# 1. A new enough system Python.
for candidate in python3 python3.14 python3.13 python3.12 python3.11; do
	path="$(command -v "$candidate" 2>/dev/null)" || continue
	if "$path" -c "import sys; sys.exit(sys.version_info < (3, $MIN_MINOR))" 2>/dev/null; then
		printf '%s\n' "$path"
		exit 0
	fi
done

if [ -z "$TRIPLE" ]; then
	warn "this system's Python is older than 3.$MIN_MINOR, and there is no"
	warn "bundled Python for the $(uname -m) architecture."
	warn "Install Python 3.$MIN_MINOR or newer as python3, then reinstall SysManage."
	exit 1
fi

# 2. Installed earlier, and still the pinned build.
if [ -x "$PREFIX/bin/python3" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$ARCHIVE" ]; then
	printf '%s\n' "$PREFIX/bin/python3"
	exit 0
fi

sha256_of() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
	elif command -v openssl >/dev/null 2>&1; then
		openssl dgst -sha256 "$1" | awk '{print $NF}'
	else
		return 1
	fi
}

download() {
	if command -v curl >/dev/null 2>&1; then
		curl -fsSL --retry 3 --connect-timeout 20 -o "$2" "$1"
	elif command -v wget >/dev/null 2>&1; then
		wget -q -T 20 -t 3 -O "$2" "$1"
	else
		warn "neither curl nor wget is installed; cannot download Python"
		return 1
	fi
}

WORK="$(mktemp -d)" || exit 1
trap 'rm -rf "$WORK"' EXIT

# 3. The air-gap bundle's copy, else 4. the release download.
if [ -f "$BUNDLE_DIR/$ARCHIVE" ]; then
	say "Using the bundled Python $PBS_PYTHON ($BUNDLE_DIR)"
	cp "$BUNDLE_DIR/$ARCHIVE" "$WORK/$ARCHIVE" || exit 1
else
	say "This system's Python is older than 3.$MIN_MINOR; downloading Python $PBS_PYTHON"
	if ! download "$PBS_URL/$ARCHIVE" "$WORK/$ARCHIVE"; then
		warn "could not download $PBS_URL/$ARCHIVE"
		warn "On a machine without internet access, use the air-gap bundle, or"
		warn "copy that file into $BUNDLE_DIR and reinstall SysManage."
		exit 1
	fi
fi

actual="$(sha256_of "$WORK/$ARCHIVE")" || {
	warn "no sha256 tool (sha256sum or openssl) available; refusing to install Python unverified"
	exit 1
}
if [ "$actual" != "$SHA256" ]; then
	warn "$ARCHIVE has sha256 $actual, expected $SHA256; refusing to install it"
	exit 1
fi

# Unpack beside the prefix, then swap it in, so a failure halfway never
# leaves a broken interpreter where a working one was.
parent="$(dirname "$PREFIX")"
mkdir -p "$parent" || exit 1
NEW="$(mktemp -d "$parent/.python-new.XXXXXX")" || exit 1
if ! tar -xzf "$WORK/$ARCHIVE" -C "$NEW" || [ ! -x "$NEW/python/bin/python3" ]; then
	warn "could not unpack $ARCHIVE"
	rm -rf "$NEW"
	exit 1
fi
printf '%s\n' "$ARCHIVE" > "$NEW/python/.sysmanage-python"
rm -rf "$PREFIX.old"
[ -e "$PREFIX" ] && mv "$PREFIX" "$PREFIX.old"
if ! mv "$NEW/python" "$PREFIX"; then
	warn "could not install Python in $PREFIX"
	[ -e "$PREFIX.old" ] && mv "$PREFIX.old" "$PREFIX"
	rm -rf "$NEW"
	exit 1
fi
rm -rf "$NEW" "$PREFIX.old"

if [ -n "$KEEP_DIR" ]; then
	mkdir -p "$KEEP_DIR" && cp "$WORK/$ARCHIVE" "$KEEP_DIR/" || exit 1
fi

say "Installed Python $PBS_PYTHON in $PREFIX"
printf '%s\n' "$PREFIX/bin/python3"
