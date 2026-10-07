#!/bin/sh
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# postinstall for sysmanage-canary-<version>-macos.pkg (Phase 22.9).
#
# The canary needs PyYAML and psycopg, which macOS does not ship, so it gets a
# private venv beside its library.  That venv is the canary's own: it must
# keep working when the server's environment is broken.  The daemon is
# installed but NOT loaded -- the configuration has to be filled in first.

LOGFILE="/tmp/sysmanage-canary-install.log"
exec >>"$LOGFILE" 2>&1
echo "=== sysmanage-canary postinstall $(date) ==="

LIB=/usr/local/lib/sysmanage-canary
CONFIG=/usr/local/etc/sysmanage-canary.yaml
EXAMPLE=/usr/local/share/sysmanage-canary/sysmanage-canary.yaml.example
LOGDIR=/usr/local/var/log
PLIST=/Library/LaunchDaemons/org.sysmanage.canary.plist
ACCOUNT=_sysmanage_canary

# A hidden service account (uid below 500), created once.
if ! dscl . -read "/Users/$ACCOUNT" >/dev/null 2>&1; then
	uid=300
	while dscl . -search /Users UniqueID "$uid" | grep -q . ||
		dscl . -search /Groups PrimaryGroupID "$uid" | grep -q .; do
		uid=$((uid + 1))
	done
	dscl . -create "/Groups/$ACCOUNT"
	dscl . -create "/Groups/$ACCOUNT" PrimaryGroupID "$uid"
	dscl . -create "/Users/$ACCOUNT"
	dscl . -create "/Users/$ACCOUNT" UniqueID "$uid"
	dscl . -create "/Users/$ACCOUNT" PrimaryGroupID "$uid"
	dscl . -create "/Users/$ACCOUNT" UserShell /usr/bin/false
	dscl . -create "/Users/$ACCOUNT" NFSHomeDirectory /var/empty
	dscl . -create "/Users/$ACCOUNT" RealName "SysManage canary"
	dscl . -create "/Users/$ACCOUNT" IsHidden 1
	echo "Created $ACCOUNT (uid $uid)"
fi

# A Python 3.8+ to build the venv from.  Apple's Command Line Tools Python
# first: it stays put, while a venv on Homebrew's python breaks the day
# `brew upgrade` removes that minor version -- and a watcher that silently
# stops is worse than none.  /usr/bin/python3 is only a stub until the Command
# Line Tools are installed (calling it opens an install dialog), hence the
# xcode-select test.  Homebrew is the fallback.
PYTHON=""
if xcode-select -p >/dev/null 2>&1; then
	PYTHON=/usr/bin/python3
else
	for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
		[ -x "$candidate" ] && PYTHON="$candidate" && break
	done
fi
if [ -n "$PYTHON" ] && "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 8))'; then
	rm -rf "$LIB/venv"
	if "$PYTHON" -m venv "$LIB/venv" &&
		"$LIB/venv/bin/python3" -m pip install --quiet --no-cache-dir --disable-pip-version-check \
			pyyaml "psycopg[binary]"; then
		echo "venv ready ($("$LIB/venv/bin/python3" --version))"
	else
		echo "WARNING: could not build $LIB/venv; see the pip output above"
	fi
else
	echo "WARNING: no Python 3.8+ found (install Homebrew python or the Command"
	echo "Line Tools, then reinstall this package)"
fi

if [ ! -e "$CONFIG" ]; then
	mkdir -p "$(dirname "$CONFIG")"
	install -m 0600 -o "$ACCOUNT" "$EXAMPLE" "$CONFIG"
	echo "Installed $CONFIG from the example"
fi
mkdir -p "$LOGDIR"
touch "$LOGDIR/sysmanage-canary.log"
chown "$ACCOUNT" "$LOGDIR/sysmanage-canary.log"

# An upgrade restarts a canary that is already running; a fresh install
# leaves it stopped until the configuration is filled in.
if launchctl print system/org.sysmanage.canary >/dev/null 2>&1; then
	launchctl kickstart -k system/org.sysmanage.canary || true
	echo "Restarted the running canary"
else
	echo "Edit $CONFIG, check it with"
	echo "  sysmanage-canary --config $CONFIG --check-config"
	echo "then start it with"
	echo "  sudo launchctl bootstrap system $PLIST"
fi
exit 0
