Name:           sysmanage
Version:        3.0.0.8
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
# The vendored wheels (cryptography, Pillow, psycopg2, …) ship private
# copies of libssl/libcrypto/libjpeg/libtiff/etc. with mangled sonames
# (e.g. libcrypto-ea28cefb.so.1.1); RPM's auto-dep generator would emit
# Requires on those phantom sonames that nothing provides, making the RPM
# uninstallable via zypper.  The prior %{_libdir}/sysmanage/venv pattern
# never matched — the real install path is /opt/sysmanage/.venv.
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

# Install OpenBAO config + init/unseal one-shot (secrets broker — see
# docs/planning/openbao-deployment-and-airgap.md)
install -d %{buildroot}/etc/openbao
install -m 640 installer/openbao/openbao.hcl %{buildroot}/etc/openbao/openbao.hcl
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
        zypper --non-interactive install --allow-unsigned-rpm "$BUNDLED_BAO" >/dev/null 2>&1 \
            || rpm -i "$BUNDLED_BAO" >/dev/null 2>&1 || true
    elif command -v zypper >/dev/null 2>&1; then
        zypper --non-interactive addrepo --gpgcheck --refresh \
            https://pkg.openbao.org/rpm openbao >/dev/null 2>&1 || true
        rpm --import https://pkg.openbao.org/gpg.key >/dev/null 2>&1 || true
        zypper --non-interactive --gpg-auto-import-keys install openbao >/dev/null 2>&1 || true
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
/etc/sysmanage/
%dir /var/lib/sysmanage
%dir /var/log/sysmanage
/usr/lib/systemd/system/sysmanage.service
/usr/lib/systemd/system/sysmanage-openbao-init.service
%dir /etc/openbao
%config(noreplace) /etc/openbao/openbao.hcl
%dir /etc/nginx
%dir /etc/nginx/conf.d
%config(noreplace) /etc/nginx/conf.d/sysmanage-nginx.conf

%changelog
* Tue Oct 29 2024 Bryan Everly <bryan@theeverlys.com> - 0.9.0-1
- Initial RPM release
- Support for OpenSUSE Leap and Tumbleweed
- Web-based management interface
- PostgreSQL database backend
- nginx reverse proxy configuration
- Comprehensive reporting system with PDF generation
- Software Bill of Materials (SBOM) included
