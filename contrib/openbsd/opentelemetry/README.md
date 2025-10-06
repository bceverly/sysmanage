# OpenTelemetry Build System for OpenBSD 7.7

This directory contains a self-contained build system for building both grpcio and OpenTelemetry Collector (otelcol-contrib) on OpenBSD 7.7.

## Quick Start

```sh
cd contrib/openbsd/opentelemetry
make                  # Build both grpcio and otelcol-contrib
doas make install     # Install both components
```

## Components

### grpcio
Python gRPC library required by OpenTelemetry Python packages. Built with OpenBSD-specific patches and installed to your virtual environment.

### otelcol-contrib
Standalone OpenTelemetry Collector service with contrib components. Built from source with OpenBSD compatibility patches.

## Requirements

**For grpcio:**
- Python 3.12+ with virtual environment at `../../.venv` or `../../../.venv`
- Development tools: `gcc`, `g++`, `patch`, `ftp`

**For otelcol-contrib:**
- Go 1.21+: `doas pkg_add go`
- GNU Make: `doas pkg_add gmake`
- GNU findutils: `doas pkg_add findutils` (provides `gfind` and `gxargs`)

**Both:**
- OpenBSD 7.7 (may work on other versions)
- Internet connection for downloading sources

## Build Process

The Makefile will:

**For grpcio:**
1. Download grpcio 1.71.0 source tarball from PyPI
2. Extract to `build/grpcio-1.71.0/`
3. Apply three OpenBSD-specific patches
4. Build Python wheel using single-threaded compilation
5. Install to virtual environment

**For otelcol-contrib:**
1. Clone OpenTelemetry Collector Contrib v0.91.0 from GitHub
2. Apply OpenBSD Makefile patch (replaces GNU tools with OpenBSD equivalents)
3. Build otelcol-contrib binary using Go
4. Install binary to `/usr/local/bin/otelcol-contrib`

## Makefile Targets

**Main targets:**
- `make` or `make all` - Build both grpcio and otelcol-contrib
- `doas make install` - Install both components
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

**patch-directory_reader.diff**
- Adds OpenBSD support to grpcio's directory reader
- Includes `GPR_OPENBSD` in platform detection
- Source: OpenBSD ports tree (`net/grpc`)

**patch-abseil-commonfields.diff**
- Fixes Abseil C++ compilation error with OpenBSD's compiler
- Changes `CommonFields{}` to `CommonFields()` to avoid constructor ambiguity
- Source: https://github.com/abseil/abseil-cpp/issues/1780

**patch-cares-dns.diff**
- Fixes c-ares DNS constant names for OpenBSD compatibility
- `ns_c_in` → `C_IN`, `ns_t_srv` → `T_SRV`, `ns_t_txt` → `T_TXT`
- Source: Custom patch for OpenBSD's c-ares header naming

### otelcol Patches (in `scripts/`)

**otelcol-v0.91.0.patch**
- Replaces GNU tools with OpenBSD/portable equivalents in Makefiles
- `find` → `gfind`, `xargs` → `gxargs`
- Fixes `-exec dirname` syntax
- Version-specific for OpenTelemetry Collector v0.91.0
- Source: Custom patch for OpenBSD build compatibility

## Build Output

- `downloads/` - Downloaded grpcio tarballs
- `build/grpcio-1.71.0/` - Extracted and patched grpcio source
- `build/opentelemetry-collector-contrib/` - Cloned otelcol source
- Installed binaries:
  - grpcio: Installed to virtual environment
  - otelcol-contrib: `/usr/local/bin/otelcol-contrib`

## Transferring to Remote Machines

This directory is designed to be transferred to remote OpenBSD machines:

```sh
# From sysmanage root, create ephemeral tarball:
tar czf /tmp/otel-openbsd.tar.gz -C contrib/openbsd opentelemetry

# Transfer /tmp/otel-openbsd.tar.gz to remote machine
# (via sysmanage-agent or scp)

# On remote machine:
tar xzf otel-openbsd.tar.gz
cd opentelemetry
make                  # Downloads sources and builds both components
doas make install     # Installs both components
```

The tarball is small (~10KB) because it only contains Makefiles and patches. The actual source code is downloaded on the remote machine during the build process.

## Troubleshooting

### grpcio Issues

**"Python virtual environment not found"**
- Ensure you have a virtual environment at `../../.venv` or `../../../.venv`
- Create one with: `python3 -m venv .venv` from the sysmanage root

**Patch fails to apply**
- Run `make distclean` to start fresh
- Patches are version-specific for grpcio 1.71.0

**Compiler errors**
- Install development tools: `doas pkg_add gcc g++`
- Check disk space (build requires ~500MB)

### otelcol Issues

**"Go is not installed" or "gmake not found"**
- Install required tools:
  ```sh
  doas pkg_add go gmake findutils
  ```

**Git clone fails**
- Check internet connection
- Ensure git is installed: `doas pkg_add git`

**Build fails with "command not found: gfind" or "gxargs"**
- Install GNU findutils: `doas pkg_add findutils`

### General

**Installation fails with permission errors**
- Use `doas make install` (not just `make install`)

**Build already exists, want to rebuild**
- Use `make clean` to remove build artifacts
- Use `make distclean` to remove everything including downloads

## Notes

- grpcio uses single-threaded compilation (`GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS=1`) to avoid race conditions
- grpcio build time: ~5-10 minutes
- otelcol build time: ~10-15 minutes
- Total disk space required: ~1.5GB
- Built for OpenBSD 7.7 amd64 (may work on other versions/architectures)
- The Makefile uses marker files (`.built`, `.patched`, `.cloned`) to track build state and skip already-completed steps
