Name:           sysmanage
Version:        3.12.0.8
Release:        1
Summary:        Centralized system management server with web-based interface

License:        AGPL-3.0-only
URL:            https://sysmanage.org
Source0:        %{name}-%{version}.tar.gz
Source1:        %{name}-vendor-%{version}.tar.gz

# Disable debug package generation (no debug symbols in Python bytecode)
%global debug_package %{nil}
%global _enable_debug_package 0
%global __os_install_post /usr/lib/rpm/brp-compress %{nil}

# Disable automatic Python dependency generation
# We manually specify python3 >= 3.11 in Requires
%global __requires_exclude ^python\\(abi\\)
# Exclude the bundled venv from BOTH auto Provides and Requires scanning.
# The vendored wheels (cryptography, Pillow, psycopg, …) ship private
# copies of libssl/libcrypto/libjpeg/libtiff/etc. with mangled sonames
# (e.g. libcrypto-ea28cefb.so.1.1); RPM's auto-dep generator would emit
# Requires on those phantom sonames that nothing provides, making the RPM
# uninstallable via zypper.  The prior %{_libdir}/sysmanage/venv pattern
# never matched -- the real install path is /opt/sysmanage/.venv.
%global __requires_exclude_from ^/opt/sysmanage/.venv/.*$
%global __provides_exclude_from ^/opt/sysmanage/.venv/.*$

BuildRequires:  python311-devel
BuildRequires:  python311-pip
BuildRequires:  systemd-rpm-macros
BuildRequires:  libffi-devel
BuildRequires:  gcc
BuildRequires:  rust
BuildRequires:  cargo

Requires:       python311
Requires:       python311-pip
Requires:       systemd
Requires:       nginx
Requires:       postgresql-server >= 12
Requires(pre):  shadow
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd

# The outside watcher (Phase 22.9) -- best on another machine, so only
# suggested here.
Suggests:       %{name}-canary = %{version}-%{release}

%description
SysManage is a comprehensive centralized system management server with a
modern web-based interface. It provides:
 * Agent management and monitoring
 * System metrics and health monitoring
 * Comprehensive reporting system with PDF generation
 * JWT-based authentication with mTLS security
 * Multi-user management system with RBAC
 * Package inventory and updates
 * Certificate management
 * Real-time WebSocket communication
 * Cross-platform support (Linux, Windows, macOS, FreeBSD, OpenBSD)

The server runs as a systemd service and communicates with SysManage agents
deployed across your infrastructure to provide centralized management.

%package canary
Summary:        Outside watcher for a SysManage server
BuildArch:      noarch
Requires:       python311
Requires:       python311-PyYAML
Recommends:     python311-psycopg
Requires(pre):  shadow
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd

%description canary
sysmanage-canary checks a SysManage server from the outside -- the web
console, the backend API, the database, the network, and whether agents are
still reporting -- and sends email when something stops working (Phase 22.9).
It runs as its own service and user with its own configuration
(/etc/sysmanage-canary.yaml), on a system Python, so it keeps working when the
server, its virtualenv or its database has failed.  It can run on the server
itself or, better, on another machine.

%prep
%autosetup -n %{name}-%{version}
# Extract vendor tarball for offline pip installation
tar -xzf %{SOURCE1} -C %{_builddir}

%build
# No compile step (Python app w/ pre-built frontend), but stamp the package
# version into backend/__init__.py so backend.__version__ resolves at runtime
# (server-info + federation "Reported version" show it instead of "unknown").
printf '__version__ = "%s"\n' "%{version}" > backend/__init__.py

%install
# Create directory structure
install -d %{buildroot}/opt/sysmanage
install -d %{buildroot}/etc/sysmanage
install -d %{buildroot}/var/lib/sysmanage
install -d %{buildroot}/var/log/sysmanage

# Copy backend application files
cp -r backend %{buildroot}/opt/sysmanage/
cp -r alembic %{buildroot}/opt/sysmanage/
install -m 644 alembic.ini %{buildroot}/opt/sysmanage/
install -m 644 requirements.txt %{buildroot}/opt/sysmanage/
install -m 644 requirements-prod.txt %{buildroot}/opt/sysmanage/
cp -r config %{buildroot}/opt/sysmanage/
cp -r scripts %{buildroot}/opt/sysmanage/
# sysmanage-migrate and sysmanage-provision-bootstrap on PATH: they run
# the scripts with the venv (a bare system python3 has no alembic).
mkdir -p %{buildroot}/usr/bin
ln -sf /opt/sysmanage/scripts/sysmanage-migrate %{buildroot}/usr/bin/sysmanage-migrate
ln -sf /opt/sysmanage/scripts/sysmanage-provision-bootstrap %{buildroot}/usr/bin/sysmanage-provision-bootstrap

# Air-gap bundle dispatcher template -- buildAirGapBundle.sh (in scripts/)
# resolves this relative to itself (../installer/airgap-bundle/install.sh),
# so it must be packaged alongside scripts/ or every bundle build dies at
# the "dispatcher template not found" preflight.
install -d %{buildroot}/opt/sysmanage/installer/airgap-bundle
install -m 0755 installer/airgap-bundle/install.sh %{buildroot}/opt/sysmanage/installer/airgap-bundle/install.sh

# Copy frontend static files
install -d %{buildroot}/opt/sysmanage/frontend
cp -r frontend/dist %{buildroot}/opt/sysmanage/frontend/
cp -r frontend/public %{buildroot}/opt/sysmanage/frontend/

# Create virtualenv and install Python dependencies from vendor tarball (offline)
# Use python3.11 for openSUSE, python3 for Fedora/RHEL
%if 0%{?suse_version}
python3.11 -m venv %{buildroot}/opt/sysmanage/.venv
%else
python3 -m venv %{buildroot}/opt/sysmanage/.venv
%endif
# Install from vendor directory (offline installation - no network required)
%{buildroot}/opt/sysmanage/.venv/bin/pip install --no-index --find-links=%{_builddir}/vendor -r requirements-prod.txt

# Fix virtualenv paths to use final installation directory instead of buildroot
sed -i 's|%{buildroot}||g' %{buildroot}/opt/sysmanage/.venv/pyvenv.cfg
# Also fix any hardcoded paths in activation scripts
find %{buildroot}/opt/sysmanage/.venv/bin -type f -exec sed -i 's|%{buildroot}||g' {} \;

# Install example config
install -m 644 installer/opensuse/sysmanage.yaml.example %{buildroot}/etc/sysmanage/

# Install systemd service
install -d %{buildroot}/usr/lib/systemd/system
install -m 644 installer/opensuse/sysmanage.service %{buildroot}/usr/lib/systemd/system/

# Install OpenBAO config + init/unseal one-shot (secrets broker -- see
# docs/planning/openbao-deployment-and-airgap.md)
# The template + install helper live in a root-owned SysManage path; the
# helper copies the template to /etc/openbao/openbao.hcl (a file of the
# openbao package) at posttrans time -- never package-owned here.
install -d %{buildroot}/usr/share/sysmanage/openbao
install -m 644 installer/openbao/openbao.hcl %{buildroot}/usr/share/sysmanage/openbao/openbao.hcl
install -m 755 installer/openbao/install-openbao-linux.sh %{buildroot}/usr/share/sysmanage/openbao/install-openbao-linux.sh
install -m 644 installer/openbao/sysmanage-openbao-init.service %{buildroot}/usr/lib/systemd/system/

# Install nginx configuration
install -d %{buildroot}/etc/nginx/conf.d
install -m 644 installer/opensuse/sysmanage-nginx.conf %{buildroot}/etc/nginx/conf.d/

# Install SBOM (Software Bill of Materials) if present
if [ -f sbom/backend-sbom.json ] || [ -f sbom/frontend-sbom.json ]; then
    install -d %{buildroot}/usr/share/doc/sysmanage/sbom
    [ -f sbom/backend-sbom.json ] && install -m 644 sbom/backend-sbom.json %{buildroot}/usr/share/doc/sysmanage/sbom/ || true
    [ -f sbom/frontend-sbom.json ] && install -m 644 sbom/frontend-sbom.json %{buildroot}/usr/share/doc/sysmanage/sbom/ || true
fi

# Generate file list for SBOM files (if they exist)
# Create empty file list - will populate only if SBOM files exist
> %{_builddir}/sbom-files.list
if [ -d %{buildroot}/usr/share/doc/sysmanage/sbom ]; then
    echo "%dir /usr/share/doc/sysmanage" >> %{_builddir}/sbom-files.list
    echo "%dir /usr/share/doc/sysmanage/sbom" >> %{_builddir}/sbom-files.list
    find %{buildroot}/usr/share/doc/sysmanage/sbom -type f | \
        sed "s|%{buildroot}||g" >> %{_builddir}/sbom-files.list
fi

# sysmanage-canary (Phase 22.9): its own library, launcher, unit and example.
install -d %{buildroot}/usr/lib/sysmanage-canary %{buildroot}/usr/share/sysmanage-canary %{buildroot}/usr/bin
cp -r canary/sysmanage_canary %{buildroot}/usr/lib/sysmanage-canary/
install -m 755 canary/bin/sysmanage-canary %{buildroot}/usr/bin/sysmanage-canary
install -d %{buildroot}/usr/lib/systemd/system
install -m 644 canary/service/sysmanage-canary.service %{buildroot}/usr/lib/systemd/system/
install -m 644 canary/sysmanage-canary.yaml.example %{buildroot}/usr/share/sysmanage-canary/

%pre
# Create sysmanage user if it doesn't exist
if ! getent passwd sysmanage >/dev/null; then
    useradd --system --user-group --home-dir /nonexistent --no-create-home \
        --shell /sbin/nologin --comment "SysManage Server" sysmanage
fi
exit 0

%post
# Set ownership of application directories
chown -R sysmanage:sysmanage /opt/sysmanage
chown -R sysmanage:sysmanage /var/lib/sysmanage
chown -R sysmanage:sysmanage /var/log/sysmanage
chown -R sysmanage:sysmanage /etc/sysmanage

# Set proper permissions
chmod 755 /opt/sysmanage
chmod 755 /var/lib/sysmanage
chmod 755 /var/log/sysmanage
chmod 750 /etc/sysmanage

# Note: The virtualenv is already installed in %install
# We don't need to recreate it here - just ensure ownership is correct
# The venv paths have been fixed during build to point to /opt/sysmanage

# The helpers below run as root AFTER the chown above: PYTHONDONTWRITEBYTECODE
# keeps them from rewriting a stale .pyc as a root-owned file inside the
# sysmanage-owned venv (OBS fails the build on that filelist change).
# Create config file if it doesn't exist
if [ ! -f /etc/sysmanage.yaml ]; then
    cp /etc/sysmanage/sysmanage.yaml.example /etc/sysmanage.yaml
    chown sysmanage:sysmanage /etc/sysmanage.yaml
    chmod 640 /etc/sysmanage.yaml
    # Generate this install's secrets (Lucky 13 #12): jwt_secret, password_salt and
    # the recovery admin password -- only in a config just created from the example.
    ( cd /opt/sysmanage && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m backend.config.install_secrets --apply /etc/sysmanage.yaml ) || true
fi
# Size the database connection pool for THIS machine (Phase 22.2): adds a
# commented database_pool block only if the config has none -- an
# administrator's own values are never touched.
( cd /opt/sysmanage && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m backend.persistence.pool_sizing --apply /etc/sysmanage.yaml ) || true

# Configure nginx
# BEGIN GENERATED TLS PREFLIGHT - edit scripts/render_nginx_configs.py
if [ ! -f '/etc/sysmanage/tls/server.crt' ] || [ ! -f '/etc/sysmanage/tls/server.key' ]; then
    echo ''
    echo '[!] TLS certificate NOT FOUND - nginx will refuse to start.'
    echo '    expected: /etc/sysmanage/tls/server.crt'
    echo '              /etc/sysmanage/tls/server.key'
    echo '    Install them (see the TLS section above), then run:'
    echo '        nginx -t && systemctl reload nginx'
    echo '    nginx was left alone, so anything already serving keeps serving.'
elif ! command -v nginx >/dev/null 2>&1; then
    echo '[!] nginx is not installed; SysManage serves the console through it.'
elif nginx -t >/dev/null 2>&1; then
    systemctl reload nginx >/dev/null 2>&1 || true
    echo '[OK] nginx configuration is valid; reloaded.'
else
    echo '[!] nginx REJECTED the configuration:'
    nginx -t 2>&1 | sed 's/^/      /'
fi
# END GENERATED TLS PREFLIGHT

# Enable the service (but don't start it yet - user needs to configure first)
%service_add_post sysmanage.service
%service_add_post sysmanage-openbao-init.service

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
echo "   The database can be on this server or a remote host."
echo ""
echo "   To set up a local database:"
echo "     sudo zypper install postgresql-server postgresql-contrib"
echo "     sudo systemctl enable --now postgresql"
echo "     sudo -u postgres createuser sysmanage"
echo "     sudo -u postgres createdb sysmanage -O sysmanage"
echo "     sudo -u postgres psql -c \"ALTER USER sysmanage WITH PASSWORD 'your-password';\""
echo ""
echo "2. Configuration File"
echo "   ------------------"
echo "   Edit: /etc/sysmanage.yaml"
echo ""
echo "   Use the online configuration builder at:"
echo "   https://sysmanage.org/config-builder.html"
echo ""
echo "3. Database Initialization"
echo "   -----------------------"
echo "   Run database migrations (control-plane chains + every tenant database):"
echo "     sudo sysmanage-migrate"
echo ""
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
echo '  /etc/sysmanage/tls/server.crt'
echo '  /etc/sysmanage/tls/server.key'
echo ''
echo 'Or point nginx somewhere else by editing these two lines in:'
echo '  /etc/nginx/conf.d/sysmanage-nginx.conf'
echo ''
echo '  ssl_certificate     /etc/sysmanage/tls/server.crt;'
echo '  ssl_certificate_key /etc/sysmanage/tls/server.key;'
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
echo ''
echo "4. Start the Services"
echo "   ------------------"
echo "     sudo systemctl start sysmanage"
echo "     sudo systemctl enable sysmanage"
echo ""
echo "5. Access the Web Interface"
echo "   ------------------------"
echo "   https://your-server/"
echo ""
echo "   The API and the agent WebSocket share this same origin under /api,"
echo "   so 443 is the only port to open. The backend on 8080 is loopback-only."
echo ""
echo "   nginx is configured to serve the frontend on port 3000"
echo "   and proxy API requests to the backend on port 8080"
echo ""
echo "Log files: /var/log/sysmanage/"
echo ""

%posttrans
# ---------------------------------------------------------------
# OpenBAO (secrets broker) -- install + configure + initialize/unseal.
#
# Runs in posttrans, not post: on an upgrade from a package version that
# owned /etc/openbao/openbao.hcl, rpm erases the old version's files AFTER
# the new post, so only here is the final state of that file known.
#
# The shared helper (/usr/share/sysmanage/openbao/install-openbao-linux.sh,
# also used by the deb) keeps an installed `bao`, else uses a package bundled
# under /opt/sysmanage/installer/openbao/ (air-gap), else downloads the
# pinned OpenBAO release .rpm from GitHub and verifies its sha256 against
# the release's checksums-linux.txt.  rpm holds its database lock until the
# transaction ends, so the helper stages the verified .rpm now and installs
# it from a detached job once this transaction is done; it then puts
# SysManage's config at /etc/openbao/openbao.hcl and starts + unseals
# OpenBAO.  If no OpenBAO can be had it says so loudly and makes sure the
# server is not left waiting on a dead local vault -- but never fails this
# install.
#
# /etc/openbao/openbao.hcl is NOT a file of this package any more (the
# openbao package owns it; shipping it too was a file conflict).  On an
# upgrade from a version that shipped it as config(noreplace), rpm removes
# an unedited copy and saves an edited one as openbao.hcl.rpmsave.  The
# helper restores a SysManage .rpmsave to openbao.hcl (operator edits
# survive) and otherwise installs the SysManage template.
# ---------------------------------------------------------------
if [ -f /usr/share/sysmanage/openbao/install-openbao-linux.sh ]; then
    /bin/sh /usr/share/sysmanage/openbao/install-openbao-linux.sh --format rpm postinst || true
fi

%preun
%service_del_preun sysmanage.service
%service_del_preun sysmanage-openbao-init.service

%postun
%service_del_postun sysmanage.service
%service_del_postun sysmanage-openbao-init.service

# Clean up on purge (erase)
if [ $1 -eq 0 ]; then
    # Remove log files
    rm -rf /var/log/sysmanage || true

    # Remove configuration directory
    rm -rf /etc/sysmanage || true

    # Remove database and runtime data
    rm -rf /var/lib/sysmanage || true

    # Remove user and group
    if getent passwd sysmanage >/dev/null; then
        userdel sysmanage >/dev/null 2>&1 || true
    fi
fi

%files -f %{_builddir}/sbom-files.list
%license LICENSE
%doc README.md
/opt/sysmanage/
/usr/bin/sysmanage-migrate
/usr/bin/sysmanage-provision-bootstrap
/etc/sysmanage/
%dir /var/lib/sysmanage
%dir /var/log/sysmanage
/usr/lib/systemd/system/sysmanage.service
/usr/lib/systemd/system/sysmanage-openbao-init.service
%dir /usr/share/sysmanage
/usr/share/sysmanage/openbao/
%dir /etc/nginx
%dir /etc/nginx/conf.d
%config(noreplace) /etc/nginx/conf.d/sysmanage-nginx.conf

%pre canary
getent group sysmanage-canary >/dev/null || groupadd -r sysmanage-canary
getent passwd sysmanage-canary >/dev/null || \
    useradd -r -g sysmanage-canary -d /nonexistent -s /sbin/nologin \
        -c "SysManage canary" sysmanage-canary
exit 0

%post canary
# The configuration holds passwords: the canary user only, mode 0600; never
# overwritten -- the administrator edits it.  Not enabled until configured.
if [ ! -e /etc/sysmanage-canary.yaml ]; then
    install -m 0600 -o sysmanage-canary -g sysmanage-canary \
        /usr/share/sysmanage-canary/sysmanage-canary.yaml.example /etc/sysmanage-canary.yaml
    echo "sysmanage-canary: edit /etc/sysmanage-canary.yaml, check it with"
    echo "  sudo -u sysmanage-canary sysmanage-canary --check-config"
    echo "then start it: sudo systemctl enable --now sysmanage-canary"
fi
%systemd_post sysmanage-canary.service

%preun canary
%systemd_preun sysmanage-canary.service

%postun canary
%systemd_postun_with_restart sysmanage-canary.service

%files canary
/usr/lib/sysmanage-canary/
/usr/bin/sysmanage-canary
/usr/lib/systemd/system/sysmanage-canary.service
/usr/share/sysmanage-canary/

%changelog
* Tue Oct 29 2024 Bryan Everly <bryan@theeverlys.com> - 0.9.0-1
- Initial RPM release
- Support for OpenSUSE Leap and Tumbleweed
- Web-based management interface
- PostgreSQL database backend
- nginx reverse proxy configuration
- Comprehensive reporting system with PDF generation
- Software Bill of Materials (SBOM) included
