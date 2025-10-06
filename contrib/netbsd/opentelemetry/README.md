# OpenTelemetry Build System for NetBSD 10.x

This directory contains a self-contained build system for building both grpcio and OpenTelemetry Collector (otelcol-contrib) on NetBSD 10.x.

## Quick Start

```sh
cd contrib/netbsd/opentelemetry
make                  # Build both grpcio and otelcol-contrib
sudo make install     # Install both components
```

## Components

### grpcio
Python gRPC library required by OpenTelemetry Python packages. Built with GCC 14 for C++17 support and installed to your virtual environment.

### otelcol-contrib
Standalone OpenTelemetry Collector service with contrib components. Built from source with NetBSD-specific configuration.

## Requirements

**For grpcio:**
- Python 3.12+ with virtual environment at `../../.venv` or `../../../.venv`
- GCC 14: `pkgin install gcc14`
- Development tools: `patch`, `ftp`

**For otelcol-contrib:**
- Go 1.21+: `pkgin install go`

**Both:**
- NetBSD 10.x (may work on other versions)
- Internet connection for downloading sources

## Build Process

The Makefile will:

**For grpcio:**
1. Download grpcio 1.71.0 source tarball from PyPI
2. Extract to `build/grpcio-1.71.0/`
3. Apply two NetBSD-compatible patches
4. Build Python wheel using GCC 14 with C++17 support
5. Install to virtual environment

**For otelcol-contrib:**
1. Clone OpenTelemetry Collector Contrib v0.91.0 from GitHub
2. Build minimal otelcol-contrib binary using Go
3. Install binary to `/usr/pkg/bin/otelcol-contrib`

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
- Fixes Abseil C++ compilation error with GCC
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
  - otelcol-contrib: `/usr/pkg/bin/otelcol-contrib`

## Transferring to Remote Machines

This directory is designed to be transferred to remote NetBSD machines:

```sh
# From sysmanage root, create ephemeral tarball:
tar czf /tmp/otel-netbsd.tar.gz -C contrib/netbsd opentelemetry

# Transfer /tmp/otel-netbsd.tar.gz to remote machine
# (via sysmanage-agent or scp)

# On remote machine:
tar xzf otel-netbsd.tar.gz
cd opentelemetry
make                  # Downloads sources and builds both components
sudo make install     # Installs both components
```

The tarball is small (~10KB) because it only contains Makefiles and patches. The actual source code is downloaded on the remote machine during the build process.

## NetBSD-Specific Features

### Uses Native NetBSD Make (bmake)
- No GNU make required
- Compatible with NetBSD's native `make` implementation
- No `gmake` package needed

### GCC 14 for C++17 Support
- NetBSD's base GCC 10.5 doesn't fully support C++17
- GCC 14 from pkgsrc provides proper C++17 support
- Configured via environment variables in Makefile

### pkgsrc Integration
- Installs to `/usr/pkg/bin` (pkgsrc standard)
- Uses libraries from `/usr/pkg/include` and `/usr/pkg/lib`
- Compatible with NetBSD package management

### Large Temp Space
- Uses `/var/tmp` instead of `/tmp` for builds
- Accommodates large build artifacts (grpcio + Go cache)

## Troubleshooting

### grpcio Issues

**"Python virtual environment not found"**
- Ensure you have a virtual environment at `../../.venv` or `../../../.venv`
- Create one with: `python3.12 -m venv .venv` from the sysmanage root

**"GCC 14 not found"**
- Install GCC 14: `pkgin install gcc14`
- Ensure `/usr/pkg/gcc14/bin/gcc` exists

**Patch fails to apply**
- Run `make distclean` to start fresh
- Patches are version-specific for grpcio 1.71.0

**Compiler errors**
- Verify GCC 14 installation: `/usr/pkg/gcc14/bin/gcc --version`
- Check disk space (build requires ~500MB in /var/tmp)

### otelcol Issues

**"Go is not installed"**
- Install Go: `pkgin install go`
- Ensure `go` is in your PATH

**Git clone fails**
- Check internet connection
- Ensure git is installed: `pkgin install git`

**Build fails with "not enough space"**
- Go cache can be large (~500MB)
- Ensure `/var/tmp` has at least 1GB free

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
- Built for NetBSD 10.x amd64 (may work on other versions/architectures)
- The Makefile uses marker files (`.built`, `.patched`, `.cloned`) to track build state and skip already-completed steps
- GCC 14 library path is configured via LDFLAGS to ensure runtime linking

## Differences from OpenBSD Version

- Uses NetBSD's native `make` instead of `gmake`
- No GNU findutils needed (no `gfind`/`gxargs`)
- No directory_reader patch needed (NetBSD already has GPR_NETBSD support)
- Uses GCC 14 from `/usr/pkg/gcc14` instead of system compiler
- Installs to `/usr/pkg/bin` instead of `/usr/local/bin`
- Uses `/var/tmp` for all temporary build files
