#!/bin/sh
# Docker build script for Alpine .apk packages
# This script runs INSIDE the Alpine Docker container
# Environment variables: VERSION (required)
set -ex

# Get Alpine version for repository URLs
ALPINE_VER=$(cat /etc/alpine-release | cut -d. -f1,2)
echo "Building on Alpine $ALPINE_VER"

# Enable community repository (required for Python packages)
echo "https://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VER}/main" > /etc/apk/repositories
echo "https://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VER}/community" >> /etc/apk/repositories
cat /etc/apk/repositories

# Update package index
apk update

# Install build dependencies
apk add --no-cache \
  alpine-sdk \
  sudo \
  python3 \
  py3-pip \
  nodejs \
  npm

# Set up abuild user (required for building packages)
adduser -D builder
addgroup builder abuild
echo "builder ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Create build directory structure
mkdir -p /home/builder/packages
mkdir -p /home/builder/aports/sysutils/sysmanage

# Copy installer files
cp /workspace/installer/alpine/APKBUILD /home/builder/aports/sysutils/sysmanage/
cp /workspace/installer/alpine/sysmanage.initd /home/builder/aports/sysutils/sysmanage/
cp /workspace/installer/alpine/sysmanage.confd /home/builder/aports/sysutils/sysmanage/
cp /workspace/installer/alpine/sysmanage.post-install /home/builder/aports/sysutils/sysmanage/
cp /workspace/installer/alpine/sysmanage-nginx.conf /home/builder/aports/sysutils/sysmanage/

# Update version in APKBUILD
cd /home/builder/aports/sysutils/sysmanage
sed -i "s/^pkgver=.*/pkgver=$VERSION/" APKBUILD

# Create a local source tarball from the workspace instead of downloading from GitHub.
# This allows building before the tag is pushed, or in air-gapped environments.
mkdir -p /tmp/sysmanage-$VERSION
cp -R /workspace/backend /tmp/sysmanage-$VERSION/
cp -R /workspace/frontend /tmp/sysmanage-$VERSION/
cp -R /workspace/alembic /tmp/sysmanage-$VERSION/ 2>/dev/null || true
cp -R /workspace/sbom /tmp/sysmanage-$VERSION/ 2>/dev/null || true
cp /workspace/alembic.ini /tmp/sysmanage-$VERSION/ 2>/dev/null || true
cp /workspace/requirements.txt /tmp/sysmanage-$VERSION/ 2>/dev/null || true
cp /workspace/requirements-prod.txt /tmp/sysmanage-$VERSION/ 2>/dev/null || true
cp /workspace/sysmanage.yaml.example /tmp/sysmanage-$VERSION/ 2>/dev/null || true
cp /workspace/README.md /tmp/sysmanage-$VERSION/ 2>/dev/null || true
cp /workspace/LICENSE /tmp/sysmanage-$VERSION/ 2>/dev/null || true

# Remove node_modules from the tarball (will be rebuilt by npm ci)
rm -rf /tmp/sysmanage-$VERSION/frontend/node_modules
rm -rf /tmp/sysmanage-$VERSION/frontend/dist

# Create the tarball
DISTDIR="/var/cache/distfiles"
mkdir -p "$DISTDIR"
cd /tmp
tar czf "sysmanage-$VERSION.tar.gz" "sysmanage-$VERSION"
rm -rf "/tmp/sysmanage-$VERSION"

# Place in both the APKBUILD dir (for abuild checksum) and distfiles (for abuild -r)
cp "sysmanage-$VERSION.tar.gz" "$DISTDIR/"
cp "sysmanage-$VERSION.tar.gz" /home/builder/aports/sysutils/sysmanage/
rm "sysmanage-$VERSION.tar.gz"

# Rewrite the APKBUILD source to use the local tarball (no URL, just filename)
cd /home/builder/aports/sysutils/sysmanage
sed -i 's|^\(source="\).*|\1|' APKBUILD
sed -i '/^source="/,/"/{
  /\.tar\.gz::/d
}' APKBUILD
sed -i "s|^source=\"|source=\"\n\tsysmanage-$VERSION.tar.gz|" APKBUILD

# Fix ownership
chown -R builder:builder /home/builder
chmod 777 "$DISTDIR"
chown -R builder:builder "$DISTDIR"

# Generate signing key (for local builds)
sudo -u builder abuild-keygen -a -i -n

# Generate checksums from the local tarball
sudo -u builder abuild checksum

# Build the package
sudo -u builder abuild -r

# Find and copy the built package
find /home/builder/packages -name "*.apk" -type f
cp /home/builder/packages/sysutils/$(uname -m)/*.apk /workspace/ || \
  cp /home/builder/packages/*/$(uname -m)/*.apk /workspace/ || \
  find /home/builder/packages -name "*.apk" -exec cp {} /workspace/ \;

echo "Build complete!"
