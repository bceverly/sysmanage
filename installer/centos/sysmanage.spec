Name:           sysmanage
Version:        0.9.0
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
# We manually specify python3 >= 3.12 in Requires
%global __requires_exclude ^python\\(abi\\)
%global __provides_exclude_from ^%{_libdir}/sysmanage/venv/.*$

BuildRequires:  python3-devel >= 3.12
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  systemd-rpm-macros

Requires:       python3 >= 3.12
Requires:       python3-pip
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
# No build step needed - Python application with pre-built frontend

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
python3 -m venv %{buildroot}/opt/sysmanage/.venv
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
python3 -m venv .venv

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
echo "   Run database migrations:"
echo "     cd /opt/sysmanage"
echo "     sudo -u sysmanage .venv/bin/python -m alembic upgrade head"
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
