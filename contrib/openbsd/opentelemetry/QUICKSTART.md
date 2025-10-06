# OpenTelemetry for OpenBSD - Quick Start

## One-Line Build and Install

```sh
cd contrib/openbsd/opentelemetry && make && doas make install
```

That's it! The Makefile will:
1. Download grpcio 1.71.0 source (~12MB)
2. Clone OpenTelemetry Collector v0.91.0 (~200MB)
3. Apply OpenBSD patches to both
4. Build grpcio wheel (~5-10 minutes)
5. Build otelcol-contrib binary (~10-15 minutes)
6. Install both components

## What You Need

**For grpcio:**
- Python venv at `../../.venv` or `../../../.venv`
- C/C++ compiler (built-in on OpenBSD 7.7)

**For otelcol:**
- Go: `doas pkg_add go`
- GNU Make: `doas pkg_add gmake`
- GNU findutils: `doas pkg_add findutils`

**Both:**
- OpenBSD 7.7
- Internet connection

## Transfer to Remote Machine

```sh
# On local machine (from sysmanage root):
tar czf /tmp/otel-openbsd.tar.gz -C contrib/openbsd opentelemetry

# Transfer /tmp/otel-openbsd.tar.gz (only ~10KB!)

# On remote machine:
tar xzf otel-openbsd.tar.gz
cd opentelemetry
make                  # Downloads sources and builds
doas make install     # Installs both components
```

## Individual Component Builds

```sh
# Build only grpcio:
make build-grpcio
make install-grpcio

# Build only otelcol-contrib:
make build-otelcol
make install-otelcol
```

## Cleanup

```sh
make clean      # Remove build files, keep downloads
make distclean  # Remove everything
```

## Troubleshooting

**"Python virtual environment not found"**
- Run from a directory with `../../.venv` or `../../../.venv`

**"Go is not installed" or "gmake not found"**
- Install: `doas pkg_add go gmake findutils`

**Patches fail to apply**
- Run `make distclean` and try again

**Build takes too long**
- Normal! grpcio: 5-10 min, otelcol: 10-15 min
- Total: ~15-25 minutes on modern hardware
