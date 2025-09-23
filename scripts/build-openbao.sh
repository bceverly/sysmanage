#!/bin/sh
#
# Build OpenBAO from source on OpenBSD
# This script handles downloading, building, and installing OpenBAO
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_DIR/.build"
INSTALL_DIR="$HOME/.local/bin"

echo "OpenBAO Source Build Script for OpenBSD"
echo "======================================="

# Check if Go is installed
if ! command -v go >/dev/null 2>&1; then
    echo "Error: Go is required to build OpenBAO"
    echo "Install with: doas pkg_add go"
    exit 1
fi

GO_VERSION=$(go version | awk '{print $3}' | sed 's/go//')
echo "Found Go version: $GO_VERSION"

# Check if git is installed
if ! command -v git >/dev/null 2>&1; then
    echo "Error: Git is required to download OpenBAO source"
    echo "Install with: doas pkg_add git"
    exit 1
fi

# Create build and install directories
mkdir -p "$BUILD_DIR"
mkdir -p "$INSTALL_DIR"

echo "Build directory: $BUILD_DIR"
echo "Install directory: $INSTALL_DIR"

# Clone or update OpenBAO repository
OPENBAO_DIR="$BUILD_DIR/openbao"
if [ -d "$OPENBAO_DIR" ]; then
    echo "Updating existing OpenBAO repository..."
    cd "$OPENBAO_DIR"
    git fetch origin
    git reset --hard origin/main
else
    echo "Cloning OpenBAO repository..."
    cd "$BUILD_DIR"
    git clone https://github.com/openbao/openbao.git
    cd "$OPENBAO_DIR"
fi

# Get a compatible release tag for older Go versions
echo "Finding compatible release for Go 1.24.1..."
# Try progressively older versions that work with Go 1.24.1
COMPATIBLE_TAGS="v2.2.0 v2.1.0 v2.0.0"

SELECTED_TAG=""
for tag in $COMPATIBLE_TAGS; do
    if git tag -l | grep -q "^$tag$"; then
        SELECTED_TAG="$tag"
        echo "Found compatible version: $SELECTED_TAG"
        break
    fi
done

if [ -z "$SELECTED_TAG" ]; then
    echo "No compatible tagged version found, trying latest..."
    SELECTED_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "main")
    echo "Falling back to: $SELECTED_TAG"
fi

echo "Building OpenBAO version: $SELECTED_TAG (compatible with Go 1.24.1)"
git checkout "$SELECTED_TAG"

# Apply OpenBSD compatibility patches
echo "Applying OpenBSD compatibility patches..."
PATCH_SCRIPT="$SCRIPT_DIR/patch-openbao-goversioncheck.sh"
if [ -f "$PATCH_SCRIPT" ]; then
    sh "$PATCH_SCRIPT"
else
    echo "Warning: Patch script not found at $PATCH_SCRIPT"
fi

# Set up Go environment for OpenBSD
export CGO_ENABLED=0
export GOOS=openbsd
export GOARCH=amd64

# Build OpenBAO
echo "Building OpenBAO (this may take several minutes)..."
echo "Go environment:"
echo "  CGO_ENABLED=$CGO_ENABLED"
echo "  GOOS=$GOOS"
echo "  GOARCH=$GOARCH"

# Use GNU make if available, fallback to system make
MAKE_CMD="make"
if command -v gmake >/dev/null 2>&1; then
    MAKE_CMD="gmake"
    echo "Using GNU make (gmake) for better compatibility"
fi

# Build the bao binary
echo "Running: $MAKE_CMD bootstrap"
$MAKE_CMD bootstrap
echo "Running: $MAKE_CMD dev"
$MAKE_CMD dev

# Check if binary was created
if [ ! -f "bin/bao" ]; then
    echo "Error: Build failed - binary not found at bin/bao"
    exit 1
fi

# Test the binary
echo "Testing built binary..."
if ! ./bin/bao version >/dev/null 2>&1; then
    echo "Error: Built binary is not working correctly"
    exit 1
fi

# Install the binary to user's local bin first
echo "Installing OpenBAO to $INSTALL_DIR/bao..."
cp bin/bao "$INSTALL_DIR/bao"
chmod +x "$INSTALL_DIR/bao"

# Also install to /usr/local/bin for system-wide access
echo "Installing OpenBAO to /usr/local/bin/bao (requires doas)..."
if command -v doas >/dev/null 2>&1; then
    if doas cp bin/bao /usr/local/bin/bao; then
        doas chmod +x /usr/local/bin/bao
        echo "✅ OpenBAO installed system-wide to /usr/local/bin/bao"
    else
        echo "Warning: Could not install to /usr/local/bin (permission denied)"
        echo "Binary available at: $INSTALL_DIR/bao"
    fi
else
    echo "Warning: doas not available, cannot install to /usr/local/bin"
    echo "Binary available at: $INSTALL_DIR/bao"
fi

# Verify installation
if command -v bao >/dev/null 2>&1; then
    echo "✅ OpenBAO installed successfully!"
    echo "Version: $(bao version)"
elif [ -f "/usr/local/bin/bao" ]; then
    echo "✅ OpenBAO installed to /usr/local/bin/bao"
    echo "Version: $(/usr/local/bin/bao version)"
else
    echo "✅ OpenBAO built and installed to $INSTALL_DIR/bao"
    echo "Add $INSTALL_DIR to your PATH to use 'bao' command:"
    echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
    echo ""
    echo "Or add this to your shell profile (.profile, .bashrc, etc.):"
    echo "  echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.profile"
fi

echo ""
echo "Build completed successfully!"
echo "Binary location: $INSTALL_DIR/bao"
echo "Source code: $OPENBAO_DIR"
echo ""
echo "To clean up build files later, run:"
echo "  rm -rf $BUILD_DIR"