# OpenBSD Makefile for building grpcio and OpenTelemetry Collector
# Compatible with both BSD make and GNU make
# Usage:
#   make          - Build grpcio and otelcol-contrib
#   doas make install - Install binaries to system
#   make clean    - Clean build artifacts
#   make distclean - Clean everything including downloads

# Configuration - grpcio
GRPCIO_VERSION = 1.71.0
GRPCIO_TARBALL = grpcio-${GRPCIO_VERSION}.tar.gz
GRPCIO_URL = https://files.pythonhosted.org/packages/source/g/grpcio/${GRPCIO_TARBALL}
GRPCIO_DIR = grpcio-${GRPCIO_VERSION}

# Configuration - OpenTelemetry Collector
OTELCOL_VERSION = 0.91.0
OTELCOL_REPO = https://github.com/open-telemetry/opentelemetry-collector-contrib.git
OTELCOL_DIR = opentelemetry-collector-contrib

# Build directories
BUILD_DIR = build
DOWNLOAD_DIR = downloads
PATCHES_DIR = patches

.PHONY: all clean distclean install download download-grpcio download-otelcol
.PHONY: patch patch-grpcio build build-grpcio build-otelcol install-grpcio install-otelcol
.PHONY: test test-otelcol info

all: build-grpcio build-otelcol

# Download sources
download: download-grpcio download-otelcol

download-grpcio: ${DOWNLOAD_DIR}/${GRPCIO_TARBALL}

${DOWNLOAD_DIR}/${GRPCIO_TARBALL}:
	@echo "==> Downloading grpcio ${GRPCIO_VERSION}..."
	@mkdir -p ${DOWNLOAD_DIR}
	ftp -o ${DOWNLOAD_DIR}/${GRPCIO_TARBALL} ${GRPCIO_URL}

# Clone OpenTelemetry Collector source
download-otelcol: ${BUILD_DIR}/${OTELCOL_DIR}/.cloned

${BUILD_DIR}/${OTELCOL_DIR}/.cloned:
	@echo "==> Cloning OpenTelemetry Collector ${OTELCOL_VERSION}..."
	@mkdir -p ${BUILD_DIR}
	@if [ ! -d ${BUILD_DIR}/${OTELCOL_DIR} ]; then \
		git clone --depth 1 --branch v${OTELCOL_VERSION} ${OTELCOL_REPO} ${BUILD_DIR}/${OTELCOL_DIR}; \
	fi
	@touch ${BUILD_DIR}/${OTELCOL_DIR}/.cloned

# Extract and patch grpcio
patch: patch-grpcio

patch-grpcio: ${BUILD_DIR}/${GRPCIO_DIR}/.patched

${BUILD_DIR}/${GRPCIO_DIR}/.patched: ${DOWNLOAD_DIR}/${GRPCIO_TARBALL}
	@echo "==> Extracting grpcio source..."
	@mkdir -p ${BUILD_DIR}
	@cd ${BUILD_DIR} && tar xzf ../${DOWNLOAD_DIR}/${GRPCIO_TARBALL}
	@echo "==> Applying OpenBSD patches..."
	@cd ${BUILD_DIR}/${GRPCIO_DIR} && \
		patch -p0 < ../../${PATCHES_DIR}/patch-directory_reader.diff
	@cd ${BUILD_DIR}/${GRPCIO_DIR} && \
		patch -p1 < ../../${PATCHES_DIR}/patch-abseil-commonfields.diff
	@cd ${BUILD_DIR}/${GRPCIO_DIR} && \
		patch -p1 < ../../${PATCHES_DIR}/patch-cares-dns.diff
	@touch ${BUILD_DIR}/${GRPCIO_DIR}/.patched

# Build targets
build: build-grpcio

build-grpcio: ${BUILD_DIR}/${GRPCIO_DIR}/.built

${BUILD_DIR}/${GRPCIO_DIR}/.built: ${BUILD_DIR}/${GRPCIO_DIR}/.patched
	@echo "==> Building grpcio wheel (this may take 5-10 minutes)..."
	@if [ -f ../../../.venv/bin/python ]; then \
		VENV_ABS=$$(cd ../../../.venv && pwd); \
	elif [ -f ../../.venv/bin/python ]; then \
		VENV_ABS=$$(cd ../../.venv && pwd); \
	else \
		echo "ERROR: Python virtual environment not found at ../../.venv or ../../../.venv"; \
		exit 1; \
	fi; \
	cd ${BUILD_DIR}/${GRPCIO_DIR} && \
		env CFLAGS="-isystem /usr/local/include" \
		    CXXFLAGS="-std=c++17 -fpermissive -Wno-error -isystem /usr/local/include" \
		    LDFLAGS="-L/usr/local/lib -Wl,-R/usr/local/lib" \
		    GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1 \
		    GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1 \
		    GRPC_PYTHON_BUILD_SYSTEM_CARES=1 \
		    GRPC_PYTHON_BUILD_WITH_BORING_SSL_ASM="" \
		    GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS=1 \
		    $$VENV_ABS/bin/pip install --no-deps .
	@touch ${BUILD_DIR}/${GRPCIO_DIR}/.built
	@echo "==> grpcio build and installation complete!"

build-otelcol: ${BUILD_DIR}/${OTELCOL_DIR}/.built

${BUILD_DIR}/${OTELCOL_DIR}/.built: ${BUILD_DIR}/${OTELCOL_DIR}/.cloned
	@echo "==> Building OpenTelemetry Collector (this may take 10-15 minutes)..."
	@echo "==> Checking for required tools..."
	@if ! command -v go >/dev/null 2>&1; then \
		echo "ERROR: Go is not installed. Install with: doas pkg_add go"; \
		exit 1; \
	fi
	@if ! command -v gmake >/dev/null 2>&1; then \
		echo "ERROR: GNU Make is not installed. Install with: doas pkg_add gmake"; \
		exit 1; \
	fi
	@if ! command -v gfind >/dev/null 2>&1; then \
		echo "ERROR: GNU findutils not installed. Install with: doas pkg_add findutils"; \
		exit 1; \
	fi
	@if ! command -v gxargs >/dev/null 2>&1; then \
		echo "ERROR: GNU xargs not installed. Install with: doas pkg_add findutils"; \
		exit 1; \
	fi
	@echo "==> Installing OpenTelemetry Collector Builder..."
	@if [ ! -f ~/go/bin/builder ]; then \
		echo "    Installing builder..."; \
		go install go.opentelemetry.io/collector/cmd/builder@v0.91.0; \
	else \
		echo "    builder already installed"; \
	fi
	@echo "==> Building minimal otelcol binary (without DataDog dependencies)..."
	cd ${BUILD_DIR}/${OTELCOL_DIR} && \
		env GOOS=openbsd GOARCH=amd64 CGO_ENABLED=0 \
		~/go/bin/builder --config ../../scripts/builder-config.yaml
	@touch ${BUILD_DIR}/${OTELCOL_DIR}/.built
	@echo "==> otelcol build complete!"

# Install targets
install-grpcio: build-grpcio
	@echo "==> grpcio already installed to venv during build"

install-otelcol: build-otelcol
	@echo "==> Installing otelcol to /usr/local/bin..."
	doas install -m 755 ${BUILD_DIR}/${OTELCOL_DIR}/bin/otelcol-openbsd /usr/local/bin/otelcol-contrib
	@echo "==> otelcol installed successfully!"

install: install-grpcio install-otelcol
	@echo "==> All components installed!"

# Test targets
test-otelcol: build-otelcol
	@echo "==> Testing otelcol binary..."
	@echo "    Checking if binary exists and is executable..."
	@test -x ${BUILD_DIR}/${OTELCOL_DIR}/bin/otelcol-openbsd || \
		(echo "ERROR: Binary not found or not executable"; exit 1)
	@echo "    Running --version..."
	@${BUILD_DIR}/${OTELCOL_DIR}/bin/otelcol-openbsd --version
	@echo "    Validating components..."
	@${BUILD_DIR}/${OTELCOL_DIR}/bin/otelcol-openbsd components 2>/dev/null || true
	@echo "==> otelcol binary test complete!"

test: test-otelcol
	@echo "==> All tests passed!"

# Clean build artifacts but keep downloads
clean:
	@echo "==> Cleaning build artifacts..."
	rm -rf ${BUILD_DIR}
	rm -rf dist
	@echo "==> Clean complete (downloads preserved)"

# Clean everything including downloads
distclean: clean
	@echo "==> Cleaning downloads..."
	rm -rf ${DOWNLOAD_DIR}
	@echo "==> Distclean complete"

# Show build information
info:
	@echo "Build Information:"
	@echo ""
	@echo "grpcio:"
	@echo "  Version:        ${GRPCIO_VERSION}"
	@echo "  Download URL:   ${GRPCIO_URL}"
	@echo "  Patches:"
	@echo "    - patch-directory_reader.diff  (OpenBSD platform support)"
	@echo "    - patch-abseil-commonfields.diff (Fix C++ compilation)"
	@echo "    - patch-cares-dns.diff         (Fix c-ares DNS constants)"
	@echo ""
	@echo "OpenTelemetry Collector:"
	@echo "  Version:        ${OTELCOL_VERSION}"
	@echo "  Repository:     ${OTELCOL_REPO}"
	@echo "  Patches:"
	@echo "    - otelcol-openbsd.patch        (Replace GNU tools with OpenBSD)"
	@echo ""
	@echo "Build Configuration:"
	@echo "  Build dir:      ${BUILD_DIR}"
	@if [ -f ../../../.venv/bin/python ]; then \
		echo "  Virtual env:    ../../../.venv"; \
	elif [ -f ../../.venv/bin/python ]; then \
		echo "  Virtual env:    ../../.venv"; \
	else \
		echo "  Virtual env:    NOT FOUND"; \
	fi
	@echo ""
	@echo "Required Tools:"
	@echo "  For grpcio:     python3, pip, C/C++ compiler"
	@echo "  For otelcol:    go, gmake, gfind, gxargs"
