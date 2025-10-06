# OpenTelemetry for NetBSD - Quick Start

## One-Line Build and Install

```sh
cd contrib/netbsd/opentelemetry && make && sudo make install
```

That's it! The Makefile will:
1. Download grpcio 1.71.0 source (~12MB)
2. Clone OpenTelemetry Collector v0.91.0 (~200MB)
3. Apply NetBSD patches to both
4. Build grpcio wheel with GCC 14 (~5-10 minutes)
5. Build otelcol-contrib binary (~10-15 minutes)
6. Install both components

## What You Need

**For grpcio:**
- Python venv at `../../.venv` or `../../../.venv`
- GCC 14: `pkgin install gcc14`

**For otelcol:**
- Go: `pkgin install go`

**Both:**
- NetBSD 10.x
- Internet connection

## Transfer to Remote Machine

```sh
# On local machine (from sysmanage root):
tar czf /tmp/otel-netbsd.tar.gz -C contrib/netbsd opentelemetry

# Transfer /tmp/otel-netbsd.tar.gz (only ~10KB!)

# On remote machine:
tar xzf otel-netbsd.tar.gz
cd opentelemetry
make                  # Downloads sources and builds
sudo make install     # Installs both components
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

**"Go is not installed"**
- Install: `pkgin install go`

**"GCC 14 not found"**
- Install: `pkgin install gcc14`

**Patches fail to apply**
- Run `make distclean` and try again

**Build takes too long**
- Normal! grpcio: 5-10 min, otelcol: 10-15 min
- Total: ~15-25 minutes on modern hardware

## NetBSD-Specific Notes

- Uses NetBSD's native `make` (bmake), not GNU make
- GCC 14 required for C++17 support
- Builds in `/var/tmp` for larger temp space
- Installs to `/usr/pkg/bin` (pkgsrc standard)
