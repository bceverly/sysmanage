# OpenTelemetry for FreeBSD - Quick Start

## One-Line Build and Install

```sh
cd contrib/freebsd/opentelemetry && make && sudo make install
```

That's it! The Makefile will:
1. Download grpcio 1.71.0 source (~12MB)
2. Clone OpenTelemetry Collector v0.91.0 (~200MB)
3. Apply FreeBSD patches to both
4. Build grpcio wheel with base system clang (~5-10 minutes)
5. Build otelcol-contrib binary (~10-15 minutes)
6. Install both components

## What You Need

**For grpcio:**
- Python venv at `../../.venv` or `../../../.venv`
- Base system clang/clang++ (included with FreeBSD)

**For otelcol:**
- Go: `pkg install go`

**Both:**
- FreeBSD 14.x
- Internet connection

## Transfer to Remote Machine

```sh
# On local machine (from sysmanage root):
tar czf /tmp/otel-freebsd.tar.gz -C contrib/freebsd opentelemetry

# Transfer /tmp/otel-freebsd.tar.gz (only ~10KB!)

# On remote machine:
tar xzf otel-freebsd.tar.gz
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
- Install: `pkg install go`

**"Compiler not found"**
- FreeBSD base system should include clang/clang++
- Verify: `clang++ --version`

**Patches fail to apply**
- Run `make distclean` and try again

**Build takes too long**
- Normal! grpcio: 5-10 min, otelcol: 10-15 min
- Total: ~15-25 minutes on modern hardware

## FreeBSD-Specific Notes

- Uses FreeBSD's native `make`, not GNU make
- Base system clang provides C++17 support (no external compiler needed)
- Uses `fetch` for downloads instead of `curl`/`ftp`
- Builds in `~/tmp` for Go cache and temporary files
- Installs to `/usr/local/bin` (FreeBSD standard)