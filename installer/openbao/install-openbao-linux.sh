#!/bin/sh
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# install-openbao-linux.sh -- install + configure the local OpenBAO secrets
# broker for the SysManage server's Linux packages (deb and rpm).
#
# Shipped at /usr/share/sysmanage/openbao/ (root-owned: root runs it, so it
# deliberately does NOT live under /opt/sysmanage, which the package chowns
# to the unprivileged sysmanage user).  The SysManage template config ships
# next to it as openbao.hcl.
#
# Usage:
#   install-openbao-linux.sh [--format deb|rpm] [ensure]
#       Install OpenBAO if missing, then configure + start it.  This is the
#       command for an operator to run by hand (for example once a server
#       that installed offline has network again).  Waits for the package
#       manager lock, so it must NOT be run from inside a package scriptlet.
#   install-openbao-linux.sh [--format deb|rpm] postinst
#       For the package scriptlets (deb postinst, rpm %posttrans).  dpkg and
#       rpm hold their database lock while a scriptlet runs, so a nested
#       `dpkg -i` / `rpm -U` fails ("dpkg database lock was locked by another
#       process").  This mode therefore stages a verified package now and
#       hands the actual install to a detached job that runs `ensure` once
#       the package transaction has released its lock.  If `bao` is already
#       installed it just configures OpenBAO in place.
#
# Install order:
#   1. `bao` already on PATH                       -> keep it
#   2. a package bundled under /opt/sysmanage/installer/openbao/ (air-gap)
#   3. the pinned OpenBAO GitHub release package for this architecture,
#      its sha256 verified against checksums-linux.txt from the SAME release
#      (refused on a mismatch or a missing entry)
#
# Never pipes a download into a shell.  Exits nonzero when OpenBAO could not
# be installed (callers in scriptlets add `|| true`: a network problem must
# never fail the SysManage package transaction).

OPENBAO_VERSION="2.5.4"
OPENBAO_RELEASE_URL="${OPENBAO_RELEASE_URL:-https://github.com/openbao/openbao/releases/download/v${OPENBAO_VERSION}}"

SHARE_DIR="${SYSMANAGE_OPENBAO_SHARE:-/usr/share/sysmanage/openbao}"
BUNDLE_DIR="${SYSMANAGE_OPENBAO_BUNDLE:-/opt/sysmanage/installer/openbao}"
STAGE_DIR="${SYSMANAGE_OPENBAO_STAGE:-/var/cache/sysmanage/openbao}"
LOG_FILE="${SYSMANAGE_OPENBAO_LOG:-/var/log/sysmanage/openbao-install.log}"
ETC_DIR="${OPENBAO_ETC_DIR:-/etc/openbao}"
DATA_DIR="${OPENBAO_DATA_DIR:-/var/lib/openbao}"
SYSMANAGE_CONFIG="${SYSMANAGE_CONFIG:-/etc/sysmanage.yaml}"
LOCK_WAIT="${OPENBAO_LOCK_WAIT:-1800}"
UNIT="sysmanage-openbao-install"

# The first line of our template carries this marker.  Older SysManage
# packages shipped the template without it; LEGACY_MARKER recognizes those.
MARKER="# Managed by SysManage"
LEGACY_MARKER="# SysManage-managed OpenBAO configuration."

case "$0" in
	/*) SELF="$0" ;;
	*) SELF="$(pwd)/$0" ;;
esac
FORMAT=""
COMMAND="ensure"
PACKAGE=""

say() { printf '%s\n' "$*"; }
warn() { printf '[!] %s\n' "$*" >&2; }

usage() {
	say "usage: $SELF [--format deb|rpm] [--package FILE] [ensure|postinst]"
}

while [ $# -gt 0 ]; do
	case "$1" in
		--format) FORMAT="$2"; shift 2 ;;
		--package) PACKAGE="$2"; shift 2 ;;
		ensure|postinst) COMMAND="$1"; shift ;;
		-h|--help) usage; exit 0 ;;
		*) usage >&2; exit 2 ;;
	esac
done

if [ -z "$FORMAT" ]; then
	if command -v dpkg >/dev/null 2>&1 && [ -d /var/lib/dpkg ]; then
		FORMAT="deb"
	elif command -v rpm >/dev/null 2>&1; then
		FORMAT="rpm"
	fi
fi
case "$FORMAT" in
	deb) DEBIAN_FRONTEND=noninteractive; export DEBIAN_FRONTEND ;;
	rpm) ;;
	*) warn "cannot tell whether this is a deb or rpm system (use --format)"; exit 2 ;;
esac

have_bao() { command -v bao >/dev/null 2>&1; }

# Release asset architecture: OpenBAO names both its .deb and .rpm assets
# with the Go architecture (amd64/arm64).
release_arch() {
	if [ "$FORMAT" = "deb" ] && command -v dpkg >/dev/null 2>&1; then
		arch="$(dpkg --print-architecture 2>/dev/null)"
	else
		arch="$(uname -m)"
	fi
	case "$arch" in
		amd64|x86_64) echo "amd64" ;;
		arm64|aarch64) echo "arm64" ;;
		*) echo "" ;;
	esac
}

asset_name() {
	echo "openbao_${OPENBAO_VERSION}_linux_$(release_arch).${FORMAT}"
}

download() {
	# download URL DEST
	if command -v curl >/dev/null 2>&1; then
		curl -fsSL --retry 3 --connect-timeout 20 -o "$2" "$1"
	elif command -v wget >/dev/null 2>&1; then
		wget -q -T 20 -t 3 -O "$2" "$1"
	else
		warn "neither curl nor wget is installed; cannot download OpenBAO"
		return 1
	fi
}

sha256_of() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
	elif command -v openssl >/dev/null 2>&1; then
		openssl dgst -sha256 -r "$1" | awk '{print $1}'
	else
		echo ""
	fi
}

# verify FILE CHECKSUMS -- the entry for FILE's basename must exist in the
# checksums file and match.  Returns nonzero (and says why) otherwise.
verify() {
	file="$1"
	sums="$2"
	base="$(basename "$file")"
	expected="$(awk -v n="$base" '$2 == n || $2 == "*" n {print $1; exit}' "$sums")"
	if [ -z "$expected" ]; then
		warn "no checksum entry for $base in $(basename "$sums"); refusing to install it"
		return 1
	fi
	actual="$(sha256_of "$file")"
	if [ -z "$actual" ]; then
		warn "no sha256 tool (sha256sum or openssl) available; refusing to install $base unverified"
		return 1
	fi
	if [ "$actual" != "$expected" ]; then
		warn "CHECKSUM MISMATCH for $base: expected $expected, got $actual; refusing to install it"
		return 1
	fi
	say "Verified sha256 of $base"
	return 0
}

# Echo the path of a package bundled for an offline install, if any.  A
# checksums-linux.txt shipped next to it is honored; without one the bundle
# itself is the trust root (it was produced by buildAirGapBundle.sh).
find_bundled() {
	[ -d "$BUNDLE_DIR" ] || return 1
	arch="$(release_arch)"
	for candidate in "$BUNDLE_DIR"/openbao*"$arch"*."$FORMAT" "$BUNDLE_DIR"/openbao*."$FORMAT"; do
		[ -f "$candidate" ] || continue
		if [ -f "$BUNDLE_DIR/checksums-linux.txt" ]; then
			verify "$candidate" "$BUNDLE_DIR/checksums-linux.txt" >&2 || return 1
		fi
		echo "$candidate"
		return 0
	done
	return 1
}

# Download + verify the pinned release package into STAGE_DIR; echo its path.
fetch_release() {
	arch="$(release_arch)"
	if [ -z "$arch" ]; then
		warn "no OpenBAO ${FORMAT} package is published for architecture '$(uname -m)'"
		return 1
	fi
	name="$(asset_name)"
	umask 077
	mkdir -p "$STAGE_DIR" || return 1
	chmod 700 "$STAGE_DIR"
	tmp="$STAGE_DIR/.download.$$"
	rm -rf "$tmp"
	mkdir "$tmp" || return 1
	say "Downloading OpenBAO ${OPENBAO_VERSION} (${name}) from ${OPENBAO_RELEASE_URL}/ ..." >&2
	if ! download "$OPENBAO_RELEASE_URL/checksums-linux.txt" "$tmp/checksums-linux.txt"; then
		warn "could not download checksums-linux.txt (no network, or the release URL is unreachable)"
		rm -rf "$tmp"
		return 1
	fi
	if ! download "$OPENBAO_RELEASE_URL/$name" "$tmp/$name"; then
		warn "could not download $name (no network, or the release URL is unreachable)"
		rm -rf "$tmp"
		return 1
	fi
	if ! verify "$tmp/$name" "$tmp/checksums-linux.txt" >&2; then
		rm -rf "$tmp"
		return 1
	fi
	mv -f "$tmp/$name" "$STAGE_DIR/$name"
	mv -f "$tmp/checksums-linux.txt" "$STAGE_DIR/checksums-linux.txt"
	rm -rf "$tmp"
	echo "$STAGE_DIR/$name"
}

# Run "$@" until it succeeds, retrying only while the failure is a package
# manager lock held by someone else (the transaction that scheduled us).
run_with_lock_retry() {
	deadline=$(( $(date +%s) + LOCK_WAIT ))
	out="$STAGE_DIR/.pm-output.$$"
	mkdir -p "$STAGE_DIR"
	while :; do
		if "$@" >"$out" 2>&1; then
			cat "$out"
			rm -f "$out"
			return 0
		fi
		if grep -qiE 'could not get lock|database lock|lock-frontend|transaction lock|is locked|\.lock' "$out" && [ "$(date +%s)" -lt "$deadline" ]; then
			sleep 5
			continue
		fi
		cat "$out" >&2
		rm -f "$out"
		return 1
	done
}

install_package_file() {
	pkg="$1"
	say "Installing $pkg ..."
	if [ "$FORMAT" = "deb" ]; then
		# --force-confold: on a host upgraded from a SysManage package that
		# shipped /etc/openbao/openbao.hcl itself, dpkg keeps that live file
		# (an obsolete conffile) and writes the stock one as .dpkg-dist,
		# instead of stopping at an interactive conffile prompt.
		if command -v apt-get >/dev/null 2>&1; then
			# apt resolves the package's Depends (openssl) and waits for
			# the dpkg lock itself.
			run_with_lock_retry apt-get install -y -q \
				-o "DPkg::Lock::Timeout=$LOCK_WAIT" \
				-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold \
				"$pkg" && return 0
		fi
		run_with_lock_retry dpkg -i --force-confdef --force-confold "$pkg"
	else
		# The sha256 above is the integrity check; the local file is not in
		# a repository, so repository GPG checking does not apply to it.
		if command -v dnf >/dev/null 2>&1; then
			run_with_lock_retry dnf install -y --nogpgcheck "$pkg" && return 0
		elif command -v zypper >/dev/null 2>&1; then
			run_with_lock_retry zypper --non-interactive --no-gpg-checks install --allow-unsigned-rpm "$pkg" && return 0
		fi
		run_with_lock_retry rpm -Uvh "$pkg"
	fi
}

is_ours() {
	[ -f "$1" ] && grep -qF -e "$MARKER" -e "$LEGACY_MARKER" "$1"
}

ensure_openbao_user() {
	getent passwd openbao >/dev/null 2>&1 && return 0
	if command -v useradd >/dev/null 2>&1; then
		useradd --system --user-group --home-dir "$DATA_DIR" --no-create-home \
			--shell /usr/sbin/nologin --comment "OpenBAO" openbao >/dev/null 2>&1 || true
	elif command -v adduser >/dev/null 2>&1; then
		adduser --system --group --home "$DATA_DIR" --no-create-home \
			--disabled-password --disabled-login --gecos "OpenBAO" openbao >/dev/null 2>&1 || true
	fi
}

# RPM upgrade from a package that owned openbao.hcl: rpm saved an edited copy
# as .rpmsave when it dropped the file.  Put the operator's file back -- and
# do it BEFORE the openbao package is installed, so that package's
# config(noreplace) keeps it (stock lands as .rpmnew) instead of laying its
# own config down where ours belongs.
restore_rpmsave() {
	hcl="$ETC_DIR/openbao.hcl"
	if [ ! -f "$hcl" ] && is_ours "$hcl.rpmsave"; then
		mv -f "$hcl.rpmsave" "$hcl"
		say "Restored the SysManage OpenBAO config from $hcl.rpmsave"
	fi
}

# Put SysManage's config at /etc/openbao/openbao.hcl, set ownership, start.
configure_openbao() {
	template="$SHARE_DIR/openbao.hcl"
	hcl="$ETC_DIR/openbao.hcl"
	changed=0
	ensure_openbao_user
	mkdir -p "$ETC_DIR" "$DATA_DIR/data"

	restore_rpmsave

	if is_ours "$hcl"; then
		say "$hcl is already the SysManage config; leaving it as is"
	elif [ -f "$template" ]; then
		if [ -f "$hcl" ]; then
			# The stock config from the openbao package listens on 0.0.0.0
			# with a self-signed cert; keep it for reference only.
			cp -p "$hcl" "$hcl.dist"
			say "Saved the stock OpenBAO config as $hcl.dist"
		fi
		cp "$template" "$hcl"
		changed=1
		say "Installed the SysManage OpenBAO config at $hcl"
	else
		warn "SysManage OpenBAO template $template is missing"
		return 1
	fi
	chown root:openbao "$hcl" 2>/dev/null || true
	chmod 640 "$hcl"

	# The stock unit reads EnvironmentFile=/etc/openbao/openbao.env.
	[ -f "$ETC_DIR/openbao.env" ] || : >"$ETC_DIR/openbao.env"
	chown root:openbao "$ETC_DIR/openbao.env" 2>/dev/null || true
	chmod 640 "$ETC_DIR/openbao.env"

	# Only the storage directory belongs to openbao.  The init/unseal
	# material (init.json: unseal key + root token) stays root-only, so this
	# is deliberately NOT a recursive chown of the whole directory.
	chown root:openbao "$DATA_DIR" 2>/dev/null || true
	chmod 750 "$DATA_DIR"
	chown -R openbao:openbao "$DATA_DIR/data" 2>/dev/null || true
	if [ -f "$DATA_DIR/init.json" ]; then
		chown root:root "$DATA_DIR/init.json"
		chmod 600 "$DATA_DIR/init.json"
	fi

	if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
		systemctl daemon-reload >/dev/null 2>&1 || true
		systemctl enable openbao.service >/dev/null 2>&1 || true
		systemctl enable sysmanage-openbao-init.service >/dev/null 2>&1 || true
		if [ "$changed" = 1 ] || ! systemctl is-active --quiet openbao.service; then
			systemctl restart openbao.service >/dev/null 2>&1 \
				|| warn "openbao.service did not start; check 'systemctl status openbao'"
		fi
		# restart, not start: the init unit is a RemainAfterExit oneshot, so
		# `start` would be a no-op after OpenBAO restarted (and resealed).
		if systemctl restart sysmanage-openbao-init.service >/dev/null 2>&1; then
			say "OpenBAO is running and unsealed on 127.0.0.1:8200"
		else
			warn "OpenBAO init/unseal did not complete; check 'systemctl status sysmanage-openbao-init'"
		fi
	else
		say "systemd is not running; enable openbao.service and sysmanage-openbao-init.service at boot"
	fi
	return 0
}

# Print the "vault" block's enabled value and url from the SysManage config
# (block style YAML, as the example and secure-installation write it).
vault_setting() {
	awk -v want="$1" '
		/^vault:[[:space:]]*(#.*)?$/ { inblock = 1; indent = -1; next }
		inblock && /^[^[:space:]#]/ { inblock = 0 }
		inblock && /^[[:space:]]+[^[:space:]#]/ {
			match($0, /^[[:space:]]+/)
			if (indent < 0) indent = RLENGTH
			if (RLENGTH != indent) next
			line = substr($0, RLENGTH + 1)
			if (line ~ "^" want ":") {
				sub("^" want ":[[:space:]]*", "", line)
				sub(/[[:space:]]+#.*$/, "", line)
				gsub(/["\047]/, "", line)
				print line
				exit
			}
		}' "$SYSMANAGE_CONFIG" 2>/dev/null
}

# With no local OpenBAO, a config pointing vault at the local broker makes
# every SysManage start and every secret read wait on a dead 127.0.0.1:8200.
# Turn that one setting off (backup kept); never touch a remote vault.url.
disable_local_vault_if_enabled() {
	[ -f "$SYSMANAGE_CONFIG" ] || return 0
	enabled="$(vault_setting enabled)"
	case "$enabled" in
		true|True|TRUE|yes|Yes|on|On) ;;
		*) return 0 ;;
	esac
	url="$(vault_setting url)"
	case "$url" in
		""|http://127.0.0.1:8200*|http://localhost:8200*|https://127.0.0.1:8200*|https://localhost:8200*) ;;
		*)
			say "  $SYSMANAGE_CONFIG uses a remote OpenBAO ($url); leaving vault.enabled as is."
			return 0
			;;
	esac
	backup="$SYSMANAGE_CONFIG.pre-openbao-$(date +%Y%m%d%H%M%S)"
	cp -p "$SYSMANAGE_CONFIG" "$backup" || return 0
	tmp="$SYSMANAGE_CONFIG.openbao-tmp.$$"
	awk '
		/^vault:[[:space:]]*(#.*)?$/ { inblock = 1; indent = -1; print; next }
		inblock && /^[^[:space:]#]/ { inblock = 0 }
		inblock && !done && /^[[:space:]]+[^[:space:]#]/ {
			match($0, /^[[:space:]]+/)
			if (indent < 0) indent = RLENGTH
			if (RLENGTH == indent && substr($0, RLENGTH + 1) ~ /^enabled:/) {
				sub(/enabled:[[:space:]]*[^[:space:]#]+/, "enabled: false")
				done = 1
			}
		}
		{ print }' "$SYSMANAGE_CONFIG" >"$tmp"
	if [ -s "$tmp" ] && [ "$(vault_setting_of "$tmp" enabled)" = "false" ]; then
		cat "$tmp" >"$SYSMANAGE_CONFIG"   # keeps owner + mode of the original
		rm -f "$tmp"
		say "  Set vault.enabled to false in $SYSMANAGE_CONFIG (backup: $backup)."
		say "  Set it back to true once OpenBAO is installed and running."
	else
		rm -f "$tmp" "$backup"
		say "  Could not edit $SYSMANAGE_CONFIG safely.  Change this line under 'vault:'"
		say "      enabled: true"
		say "  to"
		say "      enabled: false"
		say "  then restart SysManage: systemctl restart sysmanage"
	fi
}

vault_setting_of() {
	SYSMANAGE_CONFIG="$1" vault_setting "$2"
}

fail_loudly() {
	reason="$1"
	name="$(asset_name)"
	if [ "$FORMAT" = "deb" ]; then
		install_cmd="sudo apt-get install ./$name"
	else
		install_cmd="sudo dnf install ./$name   (openSUSE: sudo zypper install ./$name)"
	fi
	say ""
	say "=================================================================="
	say "[!] OpenBAO WAS NOT INSTALLED"
	say "=================================================================="
	say "  What failed: $reason"
	say ""
	say "  OpenBAO is the local secrets broker SysManage needs for"
	say "  multi-tenancy and for storing secrets.  SysManage itself was"
	say "  installed; OpenBAO has to be added before those features work."
	say ""
	say "  Once this server can reach github.com, run:"
	say "      sudo sh $SHARE_DIR/install-openbao-linux.sh"
	say "  or install it by hand:"
	say "      curl -fLO $OPENBAO_RELEASE_URL/$name"
	say "      curl -fLO $OPENBAO_RELEASE_URL/checksums-linux.txt"
	say "      sha256sum --ignore-missing -c checksums-linux.txt"
	say "      $install_cmd"
	say "      sudo sh $SHARE_DIR/install-openbao-linux.sh"
	say ""
	disable_local_vault_if_enabled
	say "=================================================================="
	say ""
}

# Hand `ensure` to a job outside the package transaction's process tree.
schedule_ensure() {
	pkg="$1"
	mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
	if [ -d /run/systemd/system ] && command -v systemd-run >/dev/null 2>&1; then
		if systemctl is-active --quiet "$UNIT.service" 2>/dev/null; then
			say "An OpenBAO install job is already running ($UNIT)."
			return 0
		fi
		systemctl reset-failed "$UNIT.service" >/dev/null 2>&1 || true
		# The inner script is single-quoted on purpose: systemd-run's /bin/sh
		# expands $0/$@/$LOG, appending the job's output to the log file.
		# shellcheck disable=SC2016
		if systemd-run --unit="$UNIT" --description="SysManage: install OpenBAO" \
			--collect --no-block --setenv=LOG="$LOG_FILE" \
			/bin/sh -c 'exec /bin/sh "$0" "$@" >>"$LOG" 2>&1' \
			"$SELF" --format "$FORMAT" --package "$pkg" ensure >/dev/null 2>&1; then
			:
		else
			warn "systemd-run failed; starting the OpenBAO install job in the background"
			nohup /bin/sh "$SELF" --format "$FORMAT" --package "$pkg" ensure \
				>>"$LOG_FILE" 2>&1 </dev/null &
		fi
	else
		nohup /bin/sh "$SELF" --format "$FORMAT" --package "$pkg" ensure \
			>>"$LOG_FILE" 2>&1 </dev/null &
	fi
	say "OpenBAO ${OPENBAO_VERSION} is verified and staged; it is installed, configured and"
	say "started as soon as this package transaction finishes."
	say "  Progress: $LOG_FILE"
	say "  If it does not come up: sudo sh $SHARE_DIR/install-openbao-linux.sh"
}

# Locate an install source (bundled, then download).  Echoes the package path.
find_package() {
	if [ -n "$PACKAGE" ]; then
		# Re-verify a staged download right before installing it.
		if [ -f "$(dirname "$PACKAGE")/checksums-linux.txt" ]; then
			verify "$PACKAGE" "$(dirname "$PACKAGE")/checksums-linux.txt" >&2 || return 1
		fi
		echo "$PACKAGE"
		return 0
	fi
	if bundled="$(find_bundled)"; then
		say "Using the bundled OpenBAO package $bundled" >&2
		echo "$bundled"
		return 0
	fi
	fetch_release
}

cmd_ensure() {
	restore_rpmsave
	if have_bao; then
		say "OpenBAO is already installed ($(command -v bao))"
	else
		if ! pkg="$(find_package)"; then
			fail_loudly "no bundled package, and the pinned ${OPENBAO_VERSION} release could not be downloaded and verified"
			return 1
		fi
		if ! install_package_file "$pkg" || ! have_bao; then
			fail_loudly "installing $pkg failed (see the output above)"
			return 1
		fi
		say "OpenBAO installed: $(bao version 2>/dev/null)"
		# A staged download has done its job; do not keep ~70 MB around.
		case "$pkg" in
			"$STAGE_DIR"/*) rm -f "$pkg" ;;
		esac
	fi
	configure_openbao
}

cmd_postinst() {
	restore_rpmsave
	if have_bao; then
		configure_openbao
		return $?
	fi
	if ! pkg="$(find_package)"; then
		fail_loudly "no bundled package, and the pinned ${OPENBAO_VERSION} release could not be downloaded and verified"
		return 1
	fi
	schedule_ensure "$pkg"
}

case "$COMMAND" in
	ensure) cmd_ensure ;;
	postinst) cmd_postinst ;;
esac
