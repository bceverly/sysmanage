Name:           sysmanage
Version:        3.0.0.10
Release:        1%{?dist}
Summary:        Centralized system management server with web-based interface

License:        AGPLv3
URL:            https://sysmanage.org
Source0:        %{name}-%{version}.tar.gz
Source1:        %{name}-vendor-%{version}.tar.gz

# Disable debug package generation (no debug symbols in Python bytecode)
%global debug_package %{nil}
%global _enable_debug_package 0
%global __os_install_post /usr/lib/rpm/brp-compress %{nil}

# Disable automatic Python dependency generation
# We manually specify python3 version in Requires (3.11 on EL8, 3.12 on EL9, 3.12+ elsewhere)
%global __requires_exclude ^python\\(abi\\)
# Exclude the bundled venv from BOTH auto Provides and Requires scanning.
# The vendored wheels (cryptography, Pillow, psycopg2, …) ship private
# copies of libssl/libcrypto/libjpeg/libtiff/etc. with mangled sonames
# (e.g. libcrypto-ea28cefb.so.1.1); RPM's auto-dep generator would emit
# Requires on those phantom sonames that nothing provides, making the RPM
# uninstallable via dnf.  The prior %{_libdir}/sysmanage/venv pattern never
# matched — the real install path is /opt/sysmanage/.venv.
%global __requires_exclude_from ^/opt/sysmanage/.venv/.*$
%global __provides_exclude_from ^/opt/sysmanage/.venv/.*$

# EL8 ships Python 3.6 as default; use the python3.11 AppStream packages instead
%if 0%{?el8}
%global python3_bin python3.11
%global python3_pkg python3.11
%global python3_devel python3.11-devel
%global python3_pip python3.11-pip
%global python3_setuptools python3.11-setuptools
%else
# EL9 ships Python 3.9 as default; use the python3.12 AppStream packages instead
%if 0%{?el9}
%global python3_bin python3.12
%global python3_pkg python3.12
%global python3_devel python3.12-devel
%global python3_pip python3.12-pip
%global python3_setuptools python3.12-setuptools
%else
%global python3_bin python3
%global python3_pkg python3 >= 3.12
%global python3_devel python3-devel >= 3.12
%global python3_pip python3-pip
%global python3_setuptools python3-setuptools
%endif
%endif

BuildRequires:  %{python3_devel}
BuildRequires:  %{python3_pip}
BuildRequires:  %{python3_setuptools}
BuildRequires:  systemd-rpm-macros

Requires:       %{python3_pkg}
Requires:       %{python3_pip}
Requires:       systemd
Requires:       nginx
Requires:       postgresql-server >= 12
Requires(pre):  shadow-utils
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd

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

%prep
%autosetup -n %{name}-%{version}
# Extract vendor tarball for offline installation (if present in COPR/OBS builds)
# Local Makefile builds don't provide vendor tarball - will use network install in %post
if [ -f %{SOURCE1} ]; then
    tar xzf %{SOURCE1}
fi

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

# Air-gap bundle dispatcher template — buildAirGapBundle.sh (in scripts/)
# resolves this relative to itself (../installer/airgap-bundle/install.sh),
# so it must be packaged alongside scripts/ or every bundle build dies at
# the "dispatcher template not found" preflight.
install -d %{buildroot}/opt/sysmanage/installer/airgap-bundle
install -m 0755 installer/airgap-bundle/install.sh %{buildroot}/opt/sysmanage/installer/airgap-bundle/install.sh

# Copy frontend static files
install -d %{buildroot}/opt/sysmanage/frontend
cp -r frontend/dist %{buildroot}/opt/sysmanage/frontend/
cp -r frontend/public %{buildroot}/opt/sysmanage/frontend/

# Copy vendor directory for offline installation (if present)
if [ -d vendor ]; then
    cp -r vendor %{buildroot}/opt/sysmanage/
fi

# Create virtualenv and install Python dependencies
# If vendor directory exists (COPR/OBS builds), use offline installation
# If not (local Makefile builds), skip pip install here - will happen in %post with network
%{python3_bin} -m venv %{buildroot}/opt/sysmanage/.venv
if [ -d %{_builddir}/%{name}-%{version}/vendor ]; then
    %{buildroot}/opt/sysmanage/.venv/bin/pip install --upgrade pip --no-index --find-links=%{_builddir}/%{name}-%{version}/vendor
    %{buildroot}/opt/sysmanage/.venv/bin/pip install -r requirements-prod.txt --no-index --find-links=%{_builddir}/%{name}-%{version}/vendor
fi

# Fix virtualenv paths to use final installation directory instead of buildroot
sed -i 's|%{buildroot}||g' %{buildroot}/opt/sysmanage/.venv/pyvenv.cfg
# Also fix any hardcoded paths in activation scripts
find %{buildroot}/opt/sysmanage/.venv/bin -type f -exec sed -i 's|%{buildroot}||g' {} \;

# Install example config
install -m 644 installer/centos/sysmanage.yaml.example %{buildroot}/etc/sysmanage/

# Install systemd service
install -d %{buildroot}/usr/lib/systemd/system
install -m 644 installer/centos/sysmanage.service %{buildroot}/usr/lib/systemd/system/

# Install OpenBAO config + init/unseal one-shot (secrets broker — central to
# SysManage; see docs/planning/openbao-deployment-and-airgap.md)
install -d %{buildroot}/etc/openbao
install -m 640 installer/openbao/openbao.hcl %{buildroot}/etc/openbao/openbao.hcl
install -m 644 installer/openbao/sysmanage-openbao-init.service %{buildroot}/usr/lib/systemd/system/

# Install nginx configuration
install -d %{buildroot}/etc/nginx/conf.d
install -m 644 installer/centos/sysmanage-nginx.conf %{buildroot}/etc/nginx/conf.d/

# Install SBOM (Software Bill of Materials)
install -d %{buildroot}/usr/share/doc/sysmanage/sbom
if [ -f sbom/backend-sbom.json ]; then
    install -m 644 sbom/backend-sbom.json %{buildroot}/usr/share/doc/sysmanage/sbom/
fi
if [ -f sbom/frontend-sbom.json ]; then
    install -m 644 sbom/frontend-sbom.json %{buildroot}/usr/share/doc/sysmanage/sbom/
fi

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

# Fix virtualenv to work with system Python
# Recreate the venv using the system's Python to fix all symlinks and paths
cd /opt/sysmanage
rm -rf .venv
%{python3_bin} -m venv .venv

# Check if we have a vendor directory from the RPM (for COPR/OBS builds)
if [ -d vendor ]; then
  .venv/bin/pip install --quiet --upgrade pip --no-index --find-links=vendor
  .venv/bin/pip install --quiet -r requirements-prod.txt --no-index --find-links=vendor
else
  # Fallback to network install (for direct RPM installs outside COPR/OBS)
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements-prod.txt
fi
cd -

# Create config file if it doesn't exist
if [ ! -f /etc/sysmanage.yaml ]; then
    cp /etc/sysmanage/sysmanage.yaml.example /etc/sysmanage.yaml
    chown sysmanage:sysmanage /etc/sysmanage.yaml
    chmod 640 /etc/sysmanage.yaml
fi

# Configure nginx
if command -v nginx >/dev/null 2>&1; then
    # Test nginx configuration
    nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || echo "[!] nginx configuration may need manual review"
fi

# ---------------------------------------------------------------
# OpenBAO (secrets broker) — install + start + initialize/unseal.
# Native package provides the bao binary, the openbao user, and the
# stock openbao.service; we drop our config + run an init/unseal one-shot.
# ---------------------------------------------------------------
if ! command -v bao >/dev/null 2>&1; then
    echo "Installing OpenBAO..."
    BUNDLED_BAO="$(ls /opt/sysmanage/installer/openbao/*.rpm 2>/dev/null | head -n1 || true)"
    if [ -n "$BUNDLED_BAO" ]; then
        dnf install -y "$BUNDLED_BAO" >/dev/null 2>&1 || rpm -i "$BUNDLED_BAO" >/dev/null 2>&1 || true
    elif command -v dnf >/dev/null 2>&1; then
        cat > /etc/yum.repos.d/openbao.repo <<'EOF'
[openbao]
name=OpenBAO
baseurl=https://pkg.openbao.org/rpm
enabled=1
gpgcheck=1
gpgkey=https://pkg.openbao.org/gpg.key
EOF
        dnf install -y openbao >/dev/null 2>&1 || true
    fi
    if ! command -v bao >/dev/null 2>&1; then
        echo "[!] OpenBAO ('bao') could not be installed automatically."
        echo "    Install it manually (https://openbao.org) or set vault.enabled=false."
    fi
fi

if command -v bao >/dev/null 2>&1; then
    if ! getent passwd openbao >/dev/null; then
        useradd --system --user-group --home-dir /var/lib/openbao --no-create-home \
            --shell /sbin/nologin --comment "OpenBAO" openbao >/dev/null 2>&1 || true
    fi
    mkdir -p /var/lib/openbao/data /etc/openbao
    chown -R openbao:openbao /var/lib/openbao
    chown root:openbao /etc/openbao/openbao.hcl 2>/dev/null || true
    chmod 640 /etc/openbao/openbao.hcl 2>/dev/null || true
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl enable openbao.service >/dev/null 2>&1 || true
    systemctl enable sysmanage-openbao-init.service >/dev/null 2>&1 || true
    systemctl restart openbao.service >/dev/null 2>&1 || true
    systemctl start sysmanage-openbao-init.service >/dev/null 2>&1 \
        || echo "[!] OpenBAO init/unseal did not complete; check 'systemctl status sysmanage-openbao-init'."
fi

# Enable the service (but don't start it yet - user needs to configure first)
%systemd_post sysmanage.service

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
echo "     sudo dnf install postgresql-server postgresql-contrib"
echo "     sudo postgresql-setup --initdb"
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
echo "     cd /opt/sysmanage"
echo "     sudo -u sysmanage .venv/bin/python scripts/sysmanage_migrate.py"
echo ""
echo "4. Start the Services"
echo "   ------------------"
echo "     sudo systemctl start sysmanage"
echo "     sudo systemctl enable sysmanage"
echo ""
echo "5. Access the Web Interface"
echo "   ------------------------"
echo "   Frontend: http://your-server:3000"
echo "   Backend API: http://your-server:8080"
echo ""
echo "   nginx is configured to serve the frontend on port 3000"
echo "   and proxy API requests to the backend on port 8080"
echo ""
echo "Log files: /var/log/sysmanage/"
echo ""

%preun
%systemd_preun sysmanage.service

%postun
%systemd_postun_with_restart sysmanage.service

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

%files
%license LICENSE
%doc README.md
/opt/sysmanage/
/etc/sysmanage/
%dir /var/lib/sysmanage
%dir /var/log/sysmanage
/usr/lib/systemd/system/sysmanage.service
/usr/lib/systemd/system/sysmanage-openbao-init.service
%dir /etc/openbao
%config(noreplace) /etc/openbao/openbao.hcl
%config(noreplace) /etc/nginx/conf.d/sysmanage-nginx.conf
%doc /usr/share/doc/sysmanage/sbom/

%changelog
* Tue Oct 29 2025 Bryan Everly <bryan@theeverlys.com> - 0.9.0-1
- Initial RPM release
- Support for CentOS, RHEL, Fedora, Rocky Linux, AlmaLinux
- Web-based management interface
- PostgreSQL database backend
- nginx reverse proxy configuration
- Comprehensive reporting system with PDF generation
- Software Bill of Materials (SBOM) included
