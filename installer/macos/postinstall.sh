#!/bin/bash
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

echo "Checking for nginx..."
if command -v nginx >/dev/null 2>&1; then
	echo "✓ nginx found - configuring automatically"
	NGINX_CONF_DIR="/usr/local/etc/nginx/servers"
	if [ -d "$NGINX_CONF_DIR" ]; then
		cp /usr/local/etc/sysmanage/sysmanage-nginx.conf "$NGINX_CONF_DIR/"
		echo "✓ nginx configuration installed to $NGINX_CONF_DIR/"
		echo "  Restart nginx to apply: brew services restart nginx"
	else
		echo "[WARNING] nginx servers directory not found at $NGINX_CONF_DIR"
		echo "  Manual configuration needed - see /usr/local/etc/sysmanage/sysmanage-nginx.conf"
	fi
else
	echo "[INFO] nginx not installed - will need to be installed separately"
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
echo "6. Load LaunchDaemon: sudo launchctl load /Library/LaunchDaemons/com.sysmanage.server.plist"
if ! command -v nginx >/dev/null 2>&1; then
	echo "7. Install nginx: brew install nginx"
	echo "8. Configure nginx: cp /usr/local/etc/sysmanage/sysmanage-nginx.conf /usr/local/etc/nginx/servers/"
	echo "9. Start nginx: brew services start nginx"
else
	echo "7. Restart nginx: brew services restart nginx"
fi
