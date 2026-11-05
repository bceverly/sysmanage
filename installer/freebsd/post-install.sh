#!/bin/sh
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# post-install for the FreeBSD server package; build_pkg_manifest.py puts
# it in +MANIFEST.

# Create sysmanage user and group if they don't exist
if ! pw groupshow sysmanage >/dev/null 2>&1; then
    pw groupadd sysmanage -g 9998
fi
if ! pw usershow sysmanage >/dev/null 2>&1; then
    pw useradd sysmanage -u 9998 -g sysmanage -h - -s /usr/sbin/nologin \
       -d /usr/local/lib/sysmanage -c "SysManage Server User"
fi

# Create directories
mkdir -p /usr/local/lib/sysmanage
mkdir -p /usr/local/etc/sysmanage
mkdir -p /var/lib/sysmanage
mkdir -p /var/log/sysmanage
mkdir -p /etc/sysmanage

# Set ownership
chown -R sysmanage:sysmanage /usr/local/lib/sysmanage
chown -R sysmanage:sysmanage /var/lib/sysmanage
chown -R sysmanage:sysmanage /var/log/sysmanage
chown -R sysmanage:sysmanage /etc/sysmanage

# The server runs on FreeBSD's own Python packages (this package's py312-*
# dependencies), as the FreeBSD port does.  .venv only gives it a stable
# interpreter path that sees them; nothing is downloaded or compiled.  The
# old post-install pip-installed requirements.txt here, which on FreeBSD
# meant building pydantic-core and cryptography from source.
cd /usr/local/lib/sysmanage
if [ ! -x .venv/bin/python ]; then
    python3.12 -m venv --system-site-packages --without-pip .venv
fi

# Use existing config or create symlink to system config
if [ -f /etc/sysmanage.yaml ]; then
    ln -sf /etc/sysmanage.yaml /usr/local/etc/sysmanage/config.yaml
elif [ ! -f /usr/local/etc/sysmanage/config.yaml ]; then
    cp /usr/local/etc/sysmanage/sysmanage.yaml.example \
       /usr/local/etc/sysmanage/config.yaml
    # Readable by the service account: sysmanage-migrate runs as it.
    chown root:sysmanage /usr/local/etc/sysmanage/config.yaml
    chmod 640 /usr/local/etc/sysmanage/config.yaml
    # Generate this install's secrets (Lucky 13 #12): jwt_secret, password_salt and
    # the recovery admin password -- only in a config just created from the example.
    ( cd /usr/local/lib/sysmanage && .venv/bin/python -m backend.config.install_secrets --apply /usr/local/etc/sysmanage/config.yaml ) || true
fi
# Size the database connection pool for THIS machine (Phase 22.2): adds a
# commented database_pool block only if the config has none -- an
# administrator's own values are never touched.
( cd /usr/local/lib/sysmanage && .venv/bin/python -m backend.persistence.pool_sizing --apply /usr/local/etc/sysmanage/config.yaml ) || true

# nginx: FreeBSD's stock nginx.conf includes no conf.d, so name our config
# once, first in the http block, where its servers become the default for
# ports 80 and 443 ahead of the stock "localhost" server.  The certificate
# goes in /usr/local/etc/sysmanage/tls (server.crt, server.key).
install -d -m 0755 /usr/local/etc/sysmanage/tls
NGINX_CONF=/usr/local/etc/nginx/nginx.conf
if [ -f "$NGINX_CONF" ] && ! grep -q 'sysmanage-nginx.conf' "$NGINX_CONF"; then
    cp -p "$NGINX_CONF" "$NGINX_CONF.before-sysmanage"
    sed -i '' -e '/^[[:space:]]*http[[:space:]]*{/a\
    include /usr/local/etc/nginx/sysmanage-nginx.conf;
' "$NGINX_CONF"
fi

# OpenBAO secrets broker -- install binary, create user, enable + start
# (the openbao rc.d service runs init/unseal in its start_postcmd).
if ! command -v bao >/dev/null 2>&1 && [ ! -x /usr/local/bin/bao ]; then
    pkg install -y openbao >/dev/null 2>&1 || true
    if [ ! -x /usr/local/bin/bao ]; then
        OPENBAO_VERSION="2.5.4"
        case "$(uname -m)" in
            amd64) BAO_ARCH="x86_64" ;;
            arm64|aarch64) BAO_ARCH="arm64" ;;
            *) BAO_ARCH="" ;;
        esac
        if [ -n "$BAO_ARCH" ]; then
            fetch -o /tmp/bao.tgz "https://github.com/openbao/openbao/releases/download/v${OPENBAO_VERSION}/bao_${OPENBAO_VERSION}_Freebsd_${BAO_ARCH}.tar.gz" 2>/dev/null \
                && tar -xzf /tmp/bao.tgz -C /usr/local/bin bao 2>/dev/null
            rm -f /tmp/bao.tgz
        fi
    fi
fi
if command -v bao >/dev/null 2>&1 || [ -x /usr/local/bin/bao ]; then
    if ! pw groupshow openbao >/dev/null 2>&1; then pw groupadd openbao -g 9997; fi
    if ! pw usershow openbao >/dev/null 2>&1; then
        pw useradd openbao -u 9997 -g openbao -h - -s /usr/sbin/nologin \
            -d /var/lib/openbao -c "OpenBAO"
    fi
    mkdir -p /var/lib/openbao/data
    chown -R openbao:openbao /var/lib/openbao
    # bao runs as openbao and must read its config (0640).
    chown root:openbao /usr/local/etc/openbao/openbao.hcl
    # Enabled, not started: pkg reaps every process a package script leaves
    # running, so a daemon started here dies when this script ends (found on
    # FreeBSD 14.5 2026-11-05).  Its first start initializes and unseals it.
    sysrc openbao_enable=YES >/dev/null 2>&1 || true
else
    echo "[!] OpenBAO ('bao') not installed; install it or set vault.enabled=false."
fi

echo ""
echo "=========================================="
echo "SysManage Server installation complete!"
echo "=========================================="
echo ""
echo "[!] IMPORTANT: Configuration Required"
echo ""
echo "Before starting SysManage, you MUST configure:"
echo ""
echo "1. PostgreSQL Database Connection"
echo "   --------------------------------"
echo "   SysManage requires a PostgreSQL database (version 12+)."
echo ""
echo "   To set up a local database:"
echo "     sysrc postgresql_enable=YES"
echo "     service postgresql initdb"
echo "     service postgresql start"
echo "     su - postgres -c 'createuser sysmanage'"
echo "     su - postgres -c 'createdb sysmanage -O sysmanage'"
echo "     su - postgres -c \"psql -c \\\"ALTER USER sysmanage WITH PASSWORD 'your-password';\\\"\""
echo ""
echo "2. Configuration File"
echo "   ------------------"
echo "   Edit: /usr/local/etc/sysmanage/config.yaml"
echo ""
echo "3. Database Initialization"
echo "   -----------------------"
echo "   Run database migrations (control-plane chains + every tenant database),"
echo "   as root, now and after every upgrade:"
echo "     sysmanage-migrate"
echo ""
echo "4. Start the Services"
echo "   ------------------"
echo "     sysrc sysmanage_enable=YES"
echo "     sysrc nginx_enable=YES"
echo "     service openbao start"
echo "     service sysmanage start"
echo "     service nginx start"
echo ""
echo "Log files: /var/log/sysmanage/"
echo ""
# sysmanage-canary (Phase 22.9): its own unprivileged user and a 0600
# config from the example (never overwritten); not enabled until configured.
if ! pw groupshow sysmanage-canary >/dev/null 2>&1; then pw groupadd sysmanage-canary -g 9996; fi
if ! pw usershow sysmanage-canary >/dev/null 2>&1; then
    pw useradd sysmanage-canary -u 9996 -g sysmanage-canary -h - -s /usr/sbin/nologin \
        -d /nonexistent -c "SysManage canary"
fi
if [ ! -e /usr/local/etc/sysmanage-canary.yaml ]; then
    install -m 0600 -o sysmanage-canary -g sysmanage-canary \
        /usr/local/share/sysmanage-canary/sysmanage-canary.yaml.example \
        /usr/local/etc/sysmanage-canary.yaml
fi
echo "Outside watcher: edit /usr/local/etc/sysmanage-canary.yaml, then"
echo "     sysmanage-canary --config /usr/local/etc/sysmanage-canary.yaml --check-config"
echo "     sysrc sysmanage_canary_enable=YES && service sysmanage_canary start"
echo ""
