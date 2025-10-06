# FreeBSD Contrib Directory

This directory contains FreeBSD-specific build systems and patches for components that require special handling on FreeBSD.

## Contents

### opentelemetry/
Build system for OpenTelemetry components on FreeBSD 14.x:
- **grpcio**: Python gRPC library with FreeBSD patches
- **otelcol-contrib**: OpenTelemetry Collector standalone service

Features:
- Self-contained Makefile using FreeBSD's native make
- Builds both Python grpcio wheel and Go otelcol binary
- Uses base system clang/clang++ for C++17 support
- Installs grpcio to virtual environment and otelcol to `/usr/local/bin`
- See `opentelemetry/README.md` for details

## Usage

```sh
cd opentelemetry/
make                  # Build both grpcio and otelcol-contrib
sudo make install     # Install both components
make clean            # Clean build artifacts
```

## Transferring to Remote Machines

Create ephemeral tarballs to transfer via sysmanage-agent:

```sh
# From the contrib/freebsd directory:
tar czf /tmp/otel-freebsd.tar.gz opentelemetry

# Transfer to remote machine via sysmanage-agent
# Extract and run make
```

The build system downloads its own source code, so the tarball is small (~10KB) - only Makefiles and patches.

## FreeBSD-Specific Features

- Uses FreeBSD's native `make` instead of GNU make
- Base system clang provides C++17 support (no external compiler needed)
- Uses `fetch` instead of `curl`/`ftp` for downloads
- Uses `~/tmp` for Go build cache and temporary files
- Installs to `/usr/local/bin` (FreeBSD standard location)
- No GNU tools required (findutils, coreutils, etc.)