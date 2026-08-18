#!/usr/bin/env bash
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

set -e

LOGFILE="/tmp/sysmanage-server-install.log"
exec >> "$LOGFILE" 2>&1

echo "=== SysManage Server Installation ==="
echo "Date: $(date)"
echo "Architecture: $(uname -m)"
echo "Python: $(which python3)"
echo "Python version: $(python3 --version)"

cd /usr/local/lib/sysmanage

if [ -d ".venv" ]; then
	echo "Removing old virtual environment..."
	rm -rf .venv
fi

echo "Creating virtual environment..."
ACTUAL_ARCH=$(sysctl -n machdep.cpu.brand_string | grep -q "Apple" && echo "arm64" || uname -m)
echo "Detected architecture: $ACTUAL_ARCH"

if [ "$ACTUAL_ARCH" = "arm64" ]; then
	echo "Apple Silicon detected - forcing ARM64 architecture"
	export ARCHFLAGS="-arch arm64"
	export _PYTHON_HOST_PLATFORM="macosx-11.0-arm64"
	arch -arm64 python3 -m venv .venv
	echo "Installing Python dependencies for ARM64..."
	arch -arm64 ./.venv/bin/pip install --upgrade pip setuptools wheel
	arch -arm64 ./.venv/bin/pip install -r "$([ -f requirements-prod.txt ] && echo requirements-prod.txt || echo requirements.txt)"
else
	echo "Intel architecture detected"
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip setuptools wheel
	./.venv/bin/pip install -r "$([ -f requirements-prod.txt ] && echo requirements-prod.txt || echo requirements.txt)"
fi

if [ ! -f "/etc/sysmanage.yaml" ]; then
	echo "Creating example configuration..."
	cp /usr/local/etc/sysmanage/sysmanage.yaml.example /etc/sysmanage.yaml.example
	echo "IMPORTANT: Configure /etc/sysmanage.yaml before starting the service"
fi

chown -R root:wheel /usr/local/lib/sysmanage
chown -R root:wheel /var/lib/sysmanage
chown -R root:wheel /var/log/sysmanage

# OpenBAO secrets broker — provision the static prebuilt binary (or Homebrew
# package), then load the LaunchDaemon and initialize/unseal.
echo "Provisioning OpenBAO..."
if ! command -v bao >/dev/null 2>&1 && [ ! -x /usr/local/bin/bao ]; then
	if command -v brew >/dev/null 2>&1; then
		brew install openbao >/dev/null 2>&1 || true
	fi
	if [ ! -x /usr/local/bin/bao ] && ! command -v bao >/dev/null 2>&1; then
		OPENBAO_VERSION="2.5.4"
		case "$(uname -m)" in
			arm64) BAO_ARCH="arm64" ;;
			x86_64) BAO_ARCH="x86_64" ;;
			*) BAO_ARCH="" ;;
		esac
		if [ -n "$BAO_ARCH" ]; then
			URL="https://github.com/openbao/openbao/releases/download/v${OPENBAO_VERSION}/bao_${OPENBAO_VERSION}_Darwin_${BAO_ARCH}.tar.gz"
			curl -fsSL "$URL" -o /tmp/bao.tgz 2>/dev/null \
				&& tar -xzf /tmp/bao.tgz -C /usr/local/bin bao 2>/dev/null
			rm -f /tmp/bao.tgz
		fi
	fi
fi
if command -v bao >/dev/null 2>&1 || [ -x /usr/local/bin/bao ]; then
	mkdir -p /var/lib/openbao/data /usr/local/etc/openbao
	chown -R root:wheel /var/lib/openbao
	launchctl load /Library/LaunchDaemons/com.sysmanage.openbao.plist 2>/dev/null || true
	/usr/bin/python3 /usr/local/lib/sysmanage/scripts/openbao_init_unseal.py \
		--addr http://127.0.0.1:8200 --keyfile /var/lib/openbao/init.json \
		--app-token-file /etc/sysmanage/openbao-token 2>/dev/null \
		|| echo "[WARNING] OpenBAO init/unseal did not complete; check /var/log/openbao.log"
else
	echo "[WARNING] OpenBAO ('bao') not installed; install it or set vault.enabled=false."
fi

# nginx is REQUIRED, not optional.  The backend serves no static files, so
# without nginx there is no web console at all -- only a loopback API.  This
# used to say "[INFO] nginx not installed - will need to be installed
# separately" and carry on, which left a macOS install reporting success with an
# unreachable console.
#
# The Homebrew prefix is DETECTED, not assumed: Apple Silicon uses
# /opt/homebrew while Intel uses /usr/local.  Hardcoding /usr/local meant that
# on every Apple Silicon Mac the config was written to a directory that does not
# exist, the script printed a warning, and nothing served the console.
echo "Setting up nginx (required - it serves the web console)..."

BREW_PREFIX=""
if command -v brew >/dev/null 2>&1; then
	BREW_PREFIX="$(brew --prefix 2>/dev/null || true)"
fi
[ -n "$BREW_PREFIX" ] || BREW_PREFIX="/usr/local"

if ! command -v nginx >/dev/null 2>&1; then
	if command -v brew >/dev/null 2>&1; then
		echo "  nginx not found - installing via Homebrew..."
		brew install nginx >/dev/null 2>&1 || true
	fi
fi

if command -v nginx >/dev/null 2>&1; then
	echo "✓ nginx present - configuring"
	# Only the nginx CONFIG DIRECTORY moves with the Homebrew prefix
	# (/opt/homebrew on Apple Silicon, /usr/local on Intel).  The config's
	# own paths are NOT rewritten: this .pkg installs to fixed absolute
	# locations on both architectures -- the frontend is always
	# /usr/local/lib/sysmanage/frontend/dist and the TLS material always
	# /usr/local/etc/sysmanage/tls -- so rewriting them to $BREW_PREFIX would
	# point nginx at directories that do not exist on Apple Silicon.
	NGINX_CONF_DIR="${BREW_PREFIX}/etc/nginx/servers"
	mkdir -p "$NGINX_CONF_DIR"
	cp /usr/local/etc/sysmanage/sysmanage-nginx.conf \
		"$NGINX_CONF_DIR/sysmanage-nginx.conf"
	echo "✓ nginx configuration installed to $NGINX_CONF_DIR/"
	echo "  Apply with: brew services restart nginx"
else
	# Loud and specific.  Do NOT pretend the install succeeded: without nginx
	# the console cannot be reached at all.
	echo "[ERROR] nginx is REQUIRED and could not be installed automatically."
	echo "        SysManage serves its web console THROUGH nginx - the API on"
	echo "        127.0.0.1:8080 does not serve the UI."
	echo "        Install it and re-run this step:"
	echo "            brew install nginx"
	echo "            sudo cp /usr/local/etc/sysmanage/sysmanage-nginx.conf \\"
	echo "                 \"\$(brew --prefix)/etc/nginx/servers/\""
	echo "            brew services restart nginx"
fi

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
if ! command -v psql >/dev/null 2>&1; then
	echo "1. Install PostgreSQL: brew install postgresql@16"
	echo "2. Start PostgreSQL: brew services start postgresql@16"
	echo "3. Create database: createdb sysmanage"
fi
echo "4. Copy and configure: cp /etc/sysmanage.yaml.example /etc/sysmanage.yaml"
echo "5. Run migrations (chains + per-tenant): cd /usr/local/lib/sysmanage && \\"
echo "     .venv/bin/python scripts/sysmanage_migrate.py"
# BEGIN GENERATED TLS MESSAGE - edit scripts/render_nginx_configs.py
echo '====================================================================='
echo 'TLS CERTIFICATE - REQUIRED BEFORE THE SERVER WILL SERVE ANYTHING'
echo '====================================================================='
echo 'SysManage serves everything on port 443, and nginx will REFUSE TO START'
echo 'until a certificate is in place.  That is deliberate: a management console'
echo 'must not come up in cleartext because a certificate was missing, and a'
echo 'certificate a package generated for you is one no agent would trust anyway'
echo '(agents verify by default).'
echo ''
echo 'Install your certificate and private key at:'
echo '  /usr/local/etc/sysmanage/tls/server.crt'
echo '  /usr/local/etc/sysmanage/tls/server.key'
echo ''
echo 'Or point nginx somewhere else by editing these two lines in:'
echo '  /usr/local/etc/nginx/servers/sysmanage-nginx.conf'
echo ''
echo '  ssl_certificate     /usr/local/etc/sysmanage/tls/server.crt;'
echo '  ssl_certificate_key /usr/local/etc/sysmanage/tls/server.key;'
echo ''
echo 'Getting a certificate:'
echo '  certbot certonly --standalone -d your-server.example.com'
echo '  (then point the two lines above at /etc/letsencrypt/live/<name>/'
echo '   fullchain.pem and privkey.pem)'
echo ''
echo 'Check it before starting:'
echo '  nginx -t'
echo ''
echo 'Agents then need outbound 443 to this host and nothing else.  If you are'
echo 'only developing, set `dev_mode: true` in the server configuration instead:'
echo 'that skips nginx entirely and serves the UI and API directly.'
# END GENERATED TLS MESSAGE
# BEGIN GENERATED TLS PREFLIGHT - edit scripts/render_nginx_configs.py
if [ ! -f '/usr/local/etc/sysmanage/tls/server.crt' ] || [ ! -f '/usr/local/etc/sysmanage/tls/server.key' ]; then
    echo ''
    echo '[!] TLS certificate NOT FOUND - nginx will refuse to start.'
    echo '    expected: /usr/local/etc/sysmanage/tls/server.crt'
    echo '              /usr/local/etc/sysmanage/tls/server.key'
    echo '    Install them (see the TLS section above), then run:'
    echo '        nginx -t && nginx -s reload'
    echo '    nginx was left alone, so anything already serving keeps serving.'
elif ! command -v nginx >/dev/null 2>&1; then
    echo '[!] nginx is not installed; SysManage serves the console through it.'
elif nginx -t >/dev/null 2>&1; then
    nginx -s reload >/dev/null 2>&1 || true
    echo '[OK] nginx configuration is valid; reloaded.'
else
    echo '[!] nginx REJECTED the configuration:'
    nginx -t 2>&1 | sed 's/^/      /'
fi
# END GENERATED TLS PREFLIGHT
echo ''
echo "6. Load LaunchDaemon: sudo launchctl load /Library/LaunchDaemons/com.sysmanage.server.plist"
if ! command -v nginx >/dev/null 2>&1; then
	echo "7. Install nginx: brew install nginx"
	echo "8. Configure nginx: cp /usr/local/etc/sysmanage/sysmanage-nginx.conf /usr/local/etc/nginx/servers/"
	echo "9. Start nginx: brew services start nginx"
else
	echo "7. Restart nginx: brew services restart nginx"
fi
