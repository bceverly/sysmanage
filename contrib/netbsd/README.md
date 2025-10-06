# NetBSD Contrib Directory

This directory contains NetBSD-specific build systems and patches for components that require special handling on NetBSD.

## Contents

### opentelemetry/
Build system for OpenTelemetry components on NetBSD 10.x:
- **grpcio**: Python gRPC library with NetBSD patches for GCC 14
- **otelcol-contrib**: OpenTelemetry Collector standalone service

Features:
- Self-contained Makefile using NetBSD's native make (bmake)
- Builds both Python grpcio wheel and Go otelcol binary
- Uses GCC 14 from `/usr/pkg/gcc14` for C++17 support
- Installs grpcio to virtual environment and otelcol to `/usr/pkg/bin`
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
# From the contrib/netbsd directory:
tar czf /tmp/otel-netbsd.tar.gz opentelemetry

# Transfer to remote machine via sysmanage-agent
# Extract and run make
```

The build system downloads its own source code, so the tarball is small (~10KB) - only Makefiles and patches.

## NetBSD-Specific Features

- Uses NetBSD's native `make` (bmake) instead of GNU make
- GCC 14 required for C++17 support (from pkgsrc: `pkgin install gcc14`)
- Uses `/var/tmp` for build artifacts (larger temp space)
- Installs to `/usr/pkg/bin` (pkgsrc standard location)
- No GNU tools required (findutils, coreutils, etc.)
