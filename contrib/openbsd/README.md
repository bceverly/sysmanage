# OpenBSD Contrib Directory

This directory contains OpenBSD-specific build systems and patches for components that don't have official OpenBSD support.

## Contents

### opentelemetry/
Build system for OpenTelemetry components on OpenBSD 7.7:
- **grpcio**: Python gRPC library with OpenBSD patches
- **otelcol-contrib**: OpenTelemetry Collector standalone service

Features:
- Self-contained Makefile that downloads sources and applies patches
- Builds both Python grpcio wheel and Go otelcol binary
- Installs grpcio to virtual environment and otelcol to `/usr/local/bin`
- See `opentelemetry/README.md` for details

## Usage

```sh
cd opentelemetry/
make                  # Build both grpcio and otelcol-contrib
doas make install     # Install both components
make clean            # Clean build artifacts
```

## Transferring to Remote Machines

Create ephemeral tarballs to transfer via sysmanage-agent:

```sh
# From the contrib/openbsd directory:
tar czf /tmp/otel-openbsd.tar.gz opentelemetry

# Transfer to remote machine via sysmanage-agent
# Extract and run make
```

The build system downloads its own source code, so the tarball is small (~10KB) - only Makefiles and patches.
