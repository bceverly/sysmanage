#!/usr/bin/env bash
# buildServerIso.sh — Build an offline-install ISO for the sysmanage
# server containing:
#   * the latest sysmanage .deb from the Launchpad PPA
#   * every apt dependency the .deb declares (recursive closure)
#   * every Python wheel the postinst's venv needs (from requirements.txt)
# so the whole install can run on an air-gapped Ubuntu host.
#
# Output (both in /tmp by default):
#   /tmp/sysmanage_<version>_<arch>.deb        (the raw .deb on its own)
#   /tmp/sysmanage_<version>_<arch>-bundle.iso (the full air-gap bundle)
#
# IMPORTANT: this script must be run on a host that matches the target
# in BOTH dimensions:
#   * Ubuntu release  — apt-get download grabs the host's archive versions
#   * Python version  — pip download grabs wheels for the host's Python
# If you run it on a different release/Python, the resulting bundle
# won't install on the target.  The simplest setup: SSH into the
# ``sysmanage-online`` VM from buildAirGapTestNetwork.sh (which is the
# same Ubuntu release as the air-gap target) and run the script there.
#
# To mount on the air-gap VM after the script finishes:
#   virsh -c qemu:///system change-media sysmanage-airgap <target> \
#       /tmp/sysmanage_<version>_<arch>-bundle.iso --update --live
#
# Then follow the README.txt embedded in the ISO root.
#
# Tunables (override via env):
#   UBUNTU_RELEASE  Ubuntu codename to pull from PPA (default: resolute)
#   ARCH            Debian arch for the index lookup (default: amd64)
#   DEST_DIR        Where to put outputs (default: /tmp)
#   ISO_LABEL       Volume label for the ISO (default: SYSMANAGE-SERVER)
#   PYTHON_BIN      Python interpreter for pip download (default: python3)
#
# Requires: curl, gunzip, awk, dpkg-deb, apt-cache, apt-get, lsb_release,
# pip, plus one of xorrisofs / genisoimage / mkisofs.

set -euo pipefail

UBUNTU_RELEASE="${UBUNTU_RELEASE:-resolute}"
ARCH="${ARCH:-amd64}"
DEST_DIR="${DEST_DIR:-/tmp}"
ISO_LABEL="${ISO_LABEL:-SYSMANAGE-SERVER}"
PPA_URL_BASE="https://ppa.launchpadcontent.net/bceverly/sysmanage/ubuntu"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Package-specific config (the only block that differs between this
# script and buildAgentIso.sh).
PKG_NAME="sysmanage"
REQ_PATH_IN_DEB="./opt/sysmanage/requirements.txt"

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

for cmd in curl gunzip awk dpkg-deb apt-cache apt-get lsb_release "$PYTHON_BIN"; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing required tool: $cmd"
done
"$PYTHON_BIN" -m pip --version >/dev/null 2>&1 \
  || die "$PYTHON_BIN -m pip is not available (install python3-pip)"

ISO_TOOL=""
for candidate in xorrisofs genisoimage mkisofs; do
  if command -v "$candidate" >/dev/null 2>&1; then
    ISO_TOOL="$candidate"; break
  fi
done
[[ -n "$ISO_TOOL" ]] || die "no ISO builder found.  sudo apt install xorriso"

HOST_RELEASE="$(lsb_release -cs 2>/dev/null || echo unknown)"
if [[ "$HOST_RELEASE" != "$UBUNTU_RELEASE" ]]; then
  warn "host release '$HOST_RELEASE' != target '$UBUNTU_RELEASE'"
  warn "apt .debs in the bundle may not match the air-gap target's archive."
  warn "Consider running this on a '$UBUNTU_RELEASE' host (e.g. sysmanage-online)."
fi

# ---------------------------------------------------------------------------
# 1. Discover the latest .deb from the PPA's Packages.gz index
# ---------------------------------------------------------------------------

INDEX_URL="${PPA_URL_BASE}/dists/${UBUNTU_RELEASE}/main/binary-${ARCH}/Packages.gz"
log "Querying ${INDEX_URL}"

DEB_REL_PATH="$(
  curl -fsSL "$INDEX_URL" \
    | gunzip \
    | awk -v pkg="$PKG_NAME" '
        $0 == "Package: " pkg {found=1}
        found && /^$/ {found=0}
        found && /^Filename:/ {print $2}' \
    | sort -V \
    | tail -1
)"

[[ -n "$DEB_REL_PATH" ]] \
  || die "no $PKG_NAME package found in ${UBUNTU_RELEASE}/${ARCH}.
Try a different UBUNTU_RELEASE or wait for Launchpad to finish publishing."

DEB_URL="${PPA_URL_BASE}/${DEB_REL_PATH}"
DEB_NAME="$(basename "$DEB_REL_PATH")"
DEB_PATH="${DEST_DIR}/${DEB_NAME}"
ISO_PATH="${DEST_DIR}/${DEB_NAME%.deb}-bundle.iso"

# ---------------------------------------------------------------------------
# 2. Download the main .deb
# ---------------------------------------------------------------------------

log "Downloading ${DEB_NAME}"
curl -fsSL --progress-bar -o "$DEB_PATH" "$DEB_URL"

# ---------------------------------------------------------------------------
# 3. Stage + extract requirements.txt
# ---------------------------------------------------------------------------

STAGE="$(mktemp -d -t sysmanage-iso-XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT
cp "$DEB_PATH" "$STAGE/"

REQ_FILE="$STAGE/requirements.txt"
log "Extracting $REQ_PATH_IN_DEB from the .deb"
dpkg-deb --fsys-tarfile "$DEB_PATH" | tar -xO "$REQ_PATH_IN_DEB" > "$REQ_FILE" 2>/dev/null \
  || die "couldn't extract $REQ_PATH_IN_DEB from $DEB_NAME"
[[ -s "$REQ_FILE" ]] || die "extracted requirements.txt is empty"
log "requirements.txt: $(grep -cE '^[a-zA-Z0-9]' "$REQ_FILE") top-level packages"

# ---------------------------------------------------------------------------
# 4. apt-get download — recursive deps of the .deb's Depends: line
# ---------------------------------------------------------------------------

APT_DEPS_DIR="$STAGE/apt-deps"
mkdir -p "$APT_DEPS_DIR"

log "Computing recursive apt dependency closure"
# Pull direct deps from the .deb's control file (no PPA needed in apt
# sources — we already have the .deb itself).
DIRECT_DEPS="$(
  dpkg-deb -f "$DEB_PATH" Depends \
    | tr ',' '\n' \
    | awk '{print $1}' \
    | grep -v '^\${' \
    | grep -vE '^$' \
    | sort -u
)"
log "Direct deps: $(echo "$DIRECT_DEPS" | tr '\n' ' ')"

# Walk the closure through apt-cache.
ALL_DEPS="$(
  # shellcheck disable=SC2086
  apt-cache depends --recurse --no-recommends --no-suggests \
    --no-conflicts --no-breaks --no-replaces --no-enhances \
    $DIRECT_DEPS \
  | awk '/^\w/ {print $1}' \
  | sort -u
)"
log "Recursive closure: $(echo "$ALL_DEPS" | wc -l) candidate packages"

log "Running apt-get download into $APT_DEPS_DIR"
(
  cd "$APT_DEPS_DIR"
  # apt-get download fails per-package on virtual packages; that's fine
  # — those don't have a real .deb to download anyway.  We collect what
  # we can and the missing virtual entries get resolved transitively.
  echo "$ALL_DEPS" | xargs -n50 apt-get download 2>&1 \
    | grep -vE "Can't select (versions|provides) only candidate|Unable to locate" \
    || true
)
APT_DEB_COUNT="$(find "$APT_DEPS_DIR" -maxdepth 1 -name '*.deb' | wc -l)"
[[ "$APT_DEB_COUNT" -gt 0 ]] || die "apt-get download produced no .debs"
log "Downloaded $APT_DEB_COUNT apt .deb packages (before arch prune)"

# Prune any .deb whose architecture doesn't match the target.  When the
# build host has foreign architectures enabled (``dpkg --print-foreign-
# architectures`` shows ``i386`` etc.), apt-cache depends walks
# Multi-Arch: same/foreign packages and apt-get download fetches both
# variants — those would be rejected by ``dpkg -i`` on the air-gap host
# with ``package architecture (i386) does not match system (amd64)``.
# Keep ``Architecture: all`` packages (e.g., python3-pip-whl); they're
# arch-independent and always valid.
PRUNED=$(find "$APT_DEPS_DIR" -maxdepth 1 -name '*.deb' \
           ! -name "*_${ARCH}.deb" ! -name "*_all.deb" -print -delete | wc -l)
if [[ "$PRUNED" -gt 0 ]]; then
  log "Pruned $PRUNED non-${ARCH} .deb files from the bundle"
fi
APT_DEB_COUNT="$(find "$APT_DEPS_DIR" -maxdepth 1 -name '*.deb' | wc -l)"
log "Final apt .deb count: $APT_DEB_COUNT"

# ---------------------------------------------------------------------------
# 5. pip download — wheels for requirements.txt + pip bootstrap deps
# ---------------------------------------------------------------------------

WHEELS_DIR="$STAGE/wheels"
mkdir -p "$WHEELS_DIR"

log "Running $PYTHON_BIN -m pip wheel into $WHEELS_DIR (this can take a few minutes)"
# Use ``pip wheel`` (not ``pip download``) so that any package without a
# pre-built wheel on PyPI gets COMPILED into a wheel here on the build
# host.  Transitive build dependencies (e.g., Cython for PyYAML on
# Python 3.14, where PyPI has no cp314 wheel) are fetched from PyPI as
# part of the build and burned into the resulting wheel — the air-gap
# target then installs the wheel directly, no build step, no Cython.
# Result: ``wheels/`` contains ONLY .whl files; the target's pip never
# has to compile anything.
"$PYTHON_BIN" -m pip wheel \
  --wheel-dir "$WHEELS_DIR" \
  --requirement "$REQ_FILE" \
  pip setuptools wheel \
  >/tmp/pip-wheel.log 2>&1 \
  || { tail -30 /tmp/pip-wheel.log; die "pip wheel failed (see /tmp/pip-wheel.log)"; }

WHEEL_COUNT="$(find "$WHEELS_DIR" -maxdepth 1 -name '*.whl' | wc -l)"
log "Built $WHEEL_COUNT wheels (sdists compiled on the build host)"

# ---------------------------------------------------------------------------
# 6. README — explains the offline install path
# ---------------------------------------------------------------------------

cat > "$STAGE/README.txt" <<EOF
SysManage server — air-gap install bundle
==========================================

Built       : $(date -u +'%Y-%m-%dT%H:%M:%SZ')
Built-on    : Ubuntu ${HOST_RELEASE} / Python $("$PYTHON_BIN" --version 2>&1 | awk '{print $2}')
Target      : Ubuntu ${UBUNTU_RELEASE} / ${ARCH}
Main pkg    : ${DEB_NAME}
apt-deps/   : ${APT_DEB_COUNT} recursive apt dependencies
wheels/     : ${WHEEL_COUNT} Python packages (requirements.txt closure + pip/setuptools/wheel)

Install on the air-gapped host
------------------------------

  sudo mount /dev/sr1 /mnt          # or /dev/sr0 — check 'lsblk -f' for the
                                    # SYSMANAGE-SERVER label
  cd /mnt

  # Single command: dpkg resolves install order from the Depends: graph,
  # so giving it ALL the .debs at once works.  The PIP_NO_INDEX +
  # PIP_FIND_LINKS env vars are read by the sysmanage postinst's
  # pip install step (which builds the /opt/sysmanage/.venv) — without
  # them, pip would try to reach PyPI and fail.
  sudo PIP_NO_INDEX=1 PIP_FIND_LINKS=/mnt/wheels \\
       dpkg -i apt-deps/*.deb ${DEB_NAME}

  # If dpkg complains about a leftover dep problem (rare, usually only
  # if the bundle was built against a different Ubuntu point release),
  # this fixes it offline:
  sudo PIP_NO_INDEX=1 PIP_FIND_LINKS=/mnt/wheels dpkg --configure -a

Post-install — PostgreSQL setup and first start
-----------------------------------------------

  sudo cp /etc/sysmanage/sysmanage.yaml.example /etc/sysmanage.yaml
  sudo \$EDITOR /etc/sysmanage.yaml
      # Edit at minimum: database.password, security.password_salt,
      # security.jwt_secret, security.admin_userid, security.admin_password

  sudo -u postgres createuser sysmanage
  sudo -u postgres createdb sysmanage -O sysmanage
  sudo -u postgres psql -c "ALTER USER sysmanage WITH PASSWORD '<password>';"

  cd /opt/sysmanage
  sudo -u sysmanage .venv/bin/python -m alembic upgrade head
  sudo systemctl restart sysmanage

When you're done:
  cd /
  sudo umount /mnt

If you re-build the bundle later, eject the old ISO from this VM first:
  virsh -c qemu:///system change-media sysmanage-airgap <target> --eject
EOF

# ---------------------------------------------------------------------------
# 7. Build the ISO
# ---------------------------------------------------------------------------

log "Building ISO with ${ISO_TOOL}"
# Clear any pre-existing output file.  xorriso refuses to overwrite when
# the target exists with restrictive perms (e.g., owned by root from a
# previous sudo'd run), surfacing as "Failed to open device : Permission
# denied".  rm with --force ignores the "doesn't exist" case.
if [[ -e "$ISO_PATH" ]]; then
  # Best-effort remove.  If the file is owned by another user (e.g.,
  # from a prior sudo'd run) we'll fail silently here and the actual
  # error will surface from xorriso below as "Permission denied" —
  # which is clear enough to act on (chown / rm with sudo by hand).
  rm -f "$ISO_PATH" 2>/dev/null || true
fi
case "$ISO_TOOL" in
  xorrisofs)
    "$ISO_TOOL" -quiet -o "$ISO_PATH" -V "$ISO_LABEL" -r -J "$STAGE"
    ;;
  genisoimage|mkisofs)
    "$ISO_TOOL" -o "$ISO_PATH" -V "$ISO_LABEL" -r -J "$STAGE" >/dev/null
    ;;
esac

log "ISO     : $ISO_PATH ($(du -h "$ISO_PATH" | cut -f1))"
log ""
log "Mount on the air-gap VM:"
log "  virsh -c qemu:///system domblklist sysmanage-airgap"
log "  virsh -c qemu:///system change-media sysmanage-airgap <target> \\"
log "    $ISO_PATH --update --live"
