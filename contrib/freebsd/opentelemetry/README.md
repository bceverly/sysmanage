# OpenTelemetry Build System for FreeBSD 14.x

This directory contains a self-contained build system for building both grpcio and OpenTelemetry Collector (otelcol-contrib) on FreeBSD 14.x.

## Quick Start

```sh
cd contrib/freebsd/opentelemetry
make                  # Build both grpcio and otelcol-contrib
sudo make install     # Install both components
```

## Components

### grpcio
Python gRPC library required by OpenTelemetry Python packages. Built with FreeBSD's base system clang for C++17 support and installed to your virtual environment.

### otelcol-contrib
Standalone OpenTelemetry Collector service with contrib components. Built from source with FreeBSD-specific configuration.

## Requirements

**For grpcio:**
- Python 3.12+ with virtual environment at `../../.venv` or `../../../.venv`
- FreeBSD base system clang/clang++ (included in base system)
- Development tools: `patch`, `fetch`

**For otelcol-contrib:**
- Go 1.21+: `pkg install go`

**Both:**
- FreeBSD 14.x (may work on other versions)
- Internet connection for downloading sources

## Build Process

The Makefile will:

**For grpcio:**
1. Download grpcio 1.71.0 source tarball from PyPI
2. Extract to `build/grpcio-1.71.0/`
3. Apply two FreeBSD-compatible patches
4. Build Python wheel using base system clang with C++17 support
5. Install to virtual environment

**For otelcol-contrib:**
1. Clone OpenTelemetry Collector Contrib v0.91.0 from GitHub
2. Build minimal otelcol-contrib binary using Go
3. Install binary to `/usr/local/bin/otelcol-contrib`

## Makefile Targets

**Main targets:**
- `make` or `make all` - Build both grpcio and otelcol-contrib
- `sudo make install` - Install both components
- `make clean` - Remove build artifacts (keeps downloads)
- `make distclean` - Remove everything including downloads
- `make info` - Show build configuration

**Component-specific:**
- `make build-grpcio` - Build only grpcio
- `make build-otelcol` - Build only otelcol-contrib
- `make install-grpcio` - Install only grpcio
- `make install-otelcol` - Install only otelcol-contrib
- `make download-grpcio` - Download grpcio source only
- `make download-otelcol` - Clone otelcol source only

## Patches

### grpcio Patches (in `patches/`)

**patch-abseil-commonfields.diff**
- Fixes Abseil C++ compilation error with clang
- Changes `CommonFields{}` to `CommonFields()` to avoid constructor ambiguity
- Source: https://github.com/abseil/abseil-cpp/issues/1780
- Platform-independent patch

**patch-cares-dns.diff**
- Fixes c-ares DNS constant names for BSD compatibility
- `ns_c_in` → `C_IN`, `ns_t_srv` → `T_SRV`, `ns_t_txt` → `T_TXT`
- Source: BSD c-ares header naming conventions
- Platform-independent patch

## Build Output

- `downloads/` - Downloaded grpcio tarballs
- `build/grpcio-1.71.0/` - Extracted and patched grpcio source
- `build/opentelemetry-collector-contrib/` - Cloned otelcol source
- Installed binaries:
  - grpcio: Installed to virtual environment
  - otelcol-contrib: `/usr/local/bin/otelcol-contrib`

## Transferring to Remote Machines

This directory is designed to be transferred to remote FreeBSD machines:

```sh
# From sysmanage root, create ephemeral tarball:
tar czf /tmp/otel-freebsd.tar.gz -C contrib/freebsd opentelemetry

# Transfer /tmp/otel-freebsd.tar.gz to remote machine
# (via sysmanage-agent or scp)

# On remote machine:
tar xzf otel-freebsd.tar.gz
cd opentelemetry
make                  # Downloads sources and builds both components
sudo make install     # Installs both components
```

The tarball is small (~10KB) because it only contains Makefiles and patches. The actual source code is downloaded on the remote machine during the build process.

## FreeBSD-Specific Features

### Uses Native FreeBSD Make
- No GNU make required
- Compatible with FreeBSD's native `make` implementation
- No `gmake` package needed

### Base System Clang for C++17 Support
- FreeBSD 14.x includes clang 16+ with full C++17 support
- No external compiler packages required
- Uses standard FreeBSD toolchain

### Standard FreeBSD Paths
- Installs to `/usr/local/bin` (FreeBSD standard)
- Uses libraries from `/usr/local/include` and `/usr/local/lib`
- Compatible with FreeBSD ports/pkg system

### Native FreeBSD Tools
- Uses `fetch` instead of `curl`/`ftp` for downloads
- Uses `~/tmp` for Go cache and temporary files
- No GNU tools required (findutils, coreutils, etc.)

## Troubleshooting

### grpcio Issues

**"Python virtual environment not found"**
- Ensure you have a virtual environment at `../../.venv` or `../../../.venv`
- Create one with: `python3.12 -m venv .venv` from the sysmanage root

**"Compiler not found"**
- FreeBSD base system should include clang/clang++
- Verify with: `clang++ --version`

**Patch fails to apply**
- Run `make distclean` to start fresh
- Patches are version-specific for grpcio 1.71.0

**Compiler errors**
- Verify clang installation: `clang++ --version`
- Check disk space (build requires ~500MB in ~/tmp)

### otelcol Issues

**"Go is not installed"**
- Install Go: `pkg install go`
- Ensure `go` is in your PATH

**Git clone fails**
- Check internet connection
- Ensure git is installed: `pkg install git`

**Build fails with "not enough space"**
- Go cache can be large (~500MB)
- Ensure `~/tmp` has at least 1GB free

### General

**Installation fails with permission errors**
- Use `sudo make install` (not just `make install`)

**Build already exists, want to rebuild**
- Use `make clean` to remove build artifacts
- Use `make distclean` to remove everything including downloads

## Notes

- grpcio uses single-threaded compilation (`GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS=1`) to avoid race conditions
- grpcio build time: ~5-10 minutes on modern hardware
- otelcol build time: ~10-15 minutes on modern hardware
- Total disk space required: ~1.5GB (builds + downloads + Go cache)
- Built for FreeBSD 14.x amd64 (may work on other versions/architectures)
- The Makefile uses marker files (`.built`, `.patched`, `.cloned`) to track build state and skip already-completed steps
- Uses standard FreeBSD rpath configuration for runtime linking

## Differences from NetBSD/OpenBSD Versions

- Uses FreeBSD's native `make` instead of `gmake`
- No GNU findutils needed (no `gfind`/`gxargs`)
- No directory_reader patch needed (FreeBSD already has proper support)
- Uses base system clang instead of external GCC packages
- Uses `fetch` instead of `ftp` for downloads
- Installs to `/usr/local/bin` instead of `/usr/pkg/bin`
- Uses `~/tmp` for all temporary build files instead of `/var/tmp`
- Simpler build environment due to better tool compatibility