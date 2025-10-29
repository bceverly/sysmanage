#!/bin/bash
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
	arch -arm64 ./.venv/bin/pip install -r requirements.txt
else
	echo "Intel architecture detected"
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip setuptools wheel
	./.venv/bin/pip install -r requirements.txt
fi

if [ ! -f "/etc/sysmanage.yaml" ]; then
	echo "Creating example configuration..."
	cp /usr/local/etc/sysmanage/sysmanage.yaml.example /etc/sysmanage.yaml.example
	echo "IMPORTANT: Configure /etc/sysmanage.yaml before starting the service"
fi

chown -R root:wheel /usr/local/lib/sysmanage
chown -R root:wheel /var/lib/sysmanage
chown -R root:wheel /var/log/sysmanage

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
echo "5. Run migrations: cd /usr/local/lib/sysmanage && .venv/bin/python -m alembic upgrade head"
echo "6. Load LaunchDaemon: sudo launchctl load /Library/LaunchDaemons/com.sysmanage.server.plist"
if ! command -v nginx >/dev/null 2>&1; then
	echo "7. Install nginx: brew install nginx"
	echo "8. Configure nginx: cp /usr/local/etc/sysmanage/sysmanage-nginx.conf /usr/local/etc/nginx/servers/"
	echo "9. Start nginx: brew services start nginx"
else
	echo "7. Restart nginx: brew services restart nginx"
fi
