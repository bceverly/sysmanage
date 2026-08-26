#!/bin/sh
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# Phase 20.1 spike probe: can THIS host be its own Ansible control node?
#
# 20.1 was decided as PULL-style -- the server ships a playbook down the
# existing WebSocket and the agent runs it locally -- so every managed host is
# its own control node.  That makes the control-node requirements a per-platform
# question, and two of them bite:
#
#   * ansible-core declares `Operating System :: POSIX` only.  Windows is a
#     MANAGED node, never a controller, which is why Windows gets a separate
#     DSC/PowerShell executor behind the same profile abstraction.
#   * the controller Python floor climbs fast: core 2.15 needs py>=3.9,
#     2.16/2.17 need >=3.10, 2.18 needs >=3.11, 2.21 needs >=3.12.  The agent
#     supports py3.9+, so an old host may only be able to run an old core.
#
# READ-ONLY.  This installs nothing; it reports what the platform already has
# and prints the command that WOULD install it.  Run it on each platform and
# collect the PROBE-RESULT lines.
#
# Usage:  sh scripts/probe-ansible-support.sh

set -u

OS=$(uname -s 2>/dev/null || echo unknown)
REL=$(uname -r 2>/dev/null || echo unknown)
ARCH=$(uname -m 2>/dev/null || echo unknown)

echo "=== SysManage Phase 20.1 ansible control-node probe ==="
echo "os=$OS release=$REL arch=$ARCH"

# --- Python -----------------------------------------------------------------
PY=""
for c in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -n "$PY" ]; then PYV=$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null); else PYV="none"; fi
echo "python=$PY version=$PYV"

# Highest ansible-core the controller Python can host (see table above).
CORE_MAX="none"
case "$PYV" in
3.9)  CORE_MAX="2.15" ;;
3.10) CORE_MAX="2.17" ;;
3.11) CORE_MAX="2.18" ;;
3.12|3.13|3.14) CORE_MAX="2.21+" ;;
esac
echo "max_core_for_this_python=$CORE_MAX"

# --- ansible already present? -----------------------------------------------
ACORE="absent"
APY="n/a"
APYPATH="n/a"
if command -v ansible >/dev/null 2>&1; then
ACORE=$(ansible --version 2>/dev/null | head -1 | sed -e 's/.*core //' -e 's/\].*//' -e 's/^ansible *//')
# CRITICAL: ansible-core often does NOT run on the system `python3`.  Observed
# on FreeBSD 14 (2026-08-26): `python3 -V` is 3.13.15 while ansible-core is the
# py312 port running /usr/local/bin/python3.12.  So the agent must SHELL OUT to
# ansible-playbook and must never `import ansible` into its own interpreter --
# and the core-version ceiling is governed by ANSIBLE's python, not the
# system's.
APY=$(ansible --version 2>/dev/null | sed -n 's/.*python version = \([0-9][0-9.]*\).*/\1/p' | head -1)
APYPATH=$(ansible --version 2>/dev/null | sed -n 's/.*python version = .*(\(\/[^)]*\)).*/\1/p' | head -1)
[ -z "$APY" ] && APY="unparsed"
[ -z "$APYPATH" ] && APYPATH="unparsed"
fi
echo "installed_ansible_core=$ACORE"
echo "ansible_python=$APY path=$APYPATH"
if [ "$APY" != "n/a" ] && [ "$APY" != "unparsed" ]; then
AMAJMIN=$(echo "$APY" | cut -d. -f1,2)
if [ "$AMAJMIN" != "$PYV" ]; then echo "WARNING: ansible runs on python $AMAJMIN but 'python3' is $PYV -- the agent MUST subprocess, not import"; fi
fi

# --- what the platform packages ---------------------------------------------
# Query only; nothing is installed.
PKGCMD="unknown"
PKGAVAIL="unknown"
# NOTE: the package name is DERIVED from the search, never hardcoded.  A
# hardcoded guess was wrong twice on first contact -- FreeBSD's prefix tracks
# its default Python (py312-, not py311-), and on OpenBSD/NetBSD plain
# "ansible" is the full 14.x bundle rather than the core we want.
case "$OS" in
FreeBSD)
if command -v pkg >/dev/null 2>&1; then PKGAVAIL=$(pkg search -q '^py3[0-9]*-ansible-core-' 2>/dev/null | tr '\n' ',' | sed 's/,$//'); fi
FIRST=$(echo "$PKGAVAIL" | cut -d, -f1 | sed 's/-[0-9].*$//')
if [ -n "$FIRST" ] && [ "$FIRST" != "not-found" ]; then PKGCMD="pkg install $FIRST"; else PKGCMD="pkg search ansible-core   # then: pkg install <name>"; fi
;;
OpenBSD)
if command -v pkg_info >/dev/null 2>&1; then PKGAVAIL=$(pkg_info -Q ansible-core 2>/dev/null | head -5 | tr '\n' ',' | sed 's/,$//'); fi
PKGCMD="pkg_add ansible-core"
;;
NetBSD)
if command -v pkgin >/dev/null 2>&1; then PKGAVAIL=$(pkgin -p search '^ansible-core' 2>/dev/null | head -5 | cut -d';' -f1 | tr '\n' ',' | sed 's/,$//'); fi
PKGCMD="pkgin install ansible-core"
;;
Darwin)
PKGCMD="brew install ansible"
if command -v brew >/dev/null 2>&1; then PKGAVAIL=$(brew info --json=v2 ansible 2>/dev/null | grep -o '"versions":{"stable":"[^"]*"' | head -1 | sed 's/.*"stable":"//;s/"//'); fi
;;
Linux)
if command -v apt-cache >/dev/null 2>&1; then PKGCMD="apt-get install ansible-core"; PKGAVAIL=$(apt-cache policy ansible-core 2>/dev/null | sed -n 's/ *Candidate: //p'); fi
if command -v dnf >/dev/null 2>&1; then PKGCMD="dnf install ansible-core"; PKGAVAIL=$(dnf --quiet list --available ansible-core 2>/dev/null | tail -1 | awk '{print $2}'); fi
if command -v zypper >/dev/null 2>&1; then PKGCMD="zypper install ansible"; PKGAVAIL=$(zypper --quiet info ansible 2>/dev/null | sed -n 's/^Version *: //p'); fi
if command -v apk >/dev/null 2>&1; then PKGCMD="apk add ansible-core"; PKGAVAIL=$(apk policy ansible-core 2>/dev/null | sed -n '2p' | tr -d ' :'); fi
;;
*) PKGCMD="(unsupported as a control node -- see the Windows note in the header)" ;;
esac
[ -z "$PKGAVAIL" ] && PKGAVAIL="not-found"
echo "package_command=$PKGCMD"
echo "package_available=$PKGAVAIL"

# --- if ansible IS present, prove a local-connection play actually runs ------
LOCALPLAY="skipped-no-ansible"
if [ "$ACORE" != "absent" ] && command -v ansible-playbook >/dev/null 2>&1; then
TMPD=$(mktemp -d 2>/dev/null || echo /tmp/sm-ansible-probe.$$)
mkdir -p "$TMPD"
cat > "$TMPD/p.yml" <<'YML'
- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: probe write
      ansible.builtin.copy:
        content: "sysmanage probe\n"
        dest: "{{ dest }}"
        mode: '0600'
    - name: probe rewrite (must report changed=false)
      ansible.builtin.copy:
        content: "sysmanage probe\n"
        dest: "{{ dest }}"
        mode: '0600'
YML
if ANSIBLE_LOCALHOST_WARNING=False ANSIBLE_INVENTORY_UNPARSED_WARNING=False ansible-playbook "$TMPD/p.yml" -e "dest=$TMPD/probe.txt" >"$TMPD/out" 2>&1; then LOCALPLAY=$(sed -n 's/.*: *ok=\([0-9]*\).*changed=\([0-9]*\).*/ok=\1,changed=\2/p' "$TMPD/out" | head -1); else LOCALPLAY="FAILED (see $TMPD/out)"; fi
[ -z "$LOCALPLAY" ] && LOCALPLAY="ran-but-no-recap"
fi
echo "local_play=$LOCALPLAY"

# --- one greppable line to send back ----------------------------------------
echo "PROBE-RESULT os=$OS rel=$REL arch=$ARCH python=$PYV ansible_python=$APY max_core=$CORE_MAX installed=$ACORE pkg_available=$PKGAVAIL local_play=$LOCALPLAY"
