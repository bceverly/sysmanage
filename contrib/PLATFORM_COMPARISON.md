# OpenBSD vs NetBSD Build System Comparison

## Overview

Both `contrib/openbsd` and `contrib/netbsd` directories provide self-contained build systems for grpcio and OpenTelemetry Collector. While they share the same core approach, they have important platform-specific differences.

## Key Differences

| Feature | OpenBSD | NetBSD |
|---------|---------|--------|
| **Make System** | Uses `gmake` (GNU Make) | Uses native `make` (bmake) |
| **C++ Compiler** | System GCC/Clang | GCC 14 from pkgsrc |
| **Install Prefix** | `/usr/local` | `/usr/pkg` |
| **Temp Directory** | `/tmp` or `~/tmp` | `/var/tmp` |
| **GNU Tools** | Requires `findutils` (gfind, gxargs) | Not required |
| **Privilege Command** | `doas` preferred | `sudo` standard |

## Detailed Differences

### 1. Make System

**OpenBSD:**
- Requires GNU Make: `pkg_add gmake`
- Uses `gmake` command
- OpenTelemetry Collector build needs GNU tool compatibility

**NetBSD:**
- Uses native NetBSD make (bmake)
- No additional make tools needed
- Simpler dependency chain

### 2. C++ Compiler

**OpenBSD:**
- Uses system compiler (GCC/Clang from base)
- C++17 support built-in
- Standard compiler flags

**NetBSD:**
- Requires GCC 14: `pkgin install gcc14`
- Base GCC 10.5 lacks full C++17 support
- Uses `/usr/pkg/gcc14/bin/gcc` explicitly
- Special LDFLAGS for GCC 14 library paths

### 3. grpcio Patches

**OpenBSD:**
- 3 patches required:
  - `patch-directory_reader.diff` - Adds GPR_OPENBSD support
  - `patch-abseil-commonfields.diff` - Fix C++ compilation
  - `patch-cares-dns.diff` - Fix c-ares DNS constants

**NetBSD:**
- 2 patches required:
  - `patch-abseil-commonfields.diff` - Fix C++ compilation
  - `patch-cares-dns.diff` - Fix c-ares DNS constants
- **No directory_reader patch needed** - NetBSD already has GPR_NETBSD support upstream

### 4. Installation Paths

**OpenBSD:**
- Binary: `/usr/local/bin/otelcol-contrib`
- Libraries: `/usr/local/lib`
- Includes: `/usr/local/include`

**NetBSD:**
- Binary: `/usr/pkg/bin/otelcol-contrib`
- Libraries: `/usr/pkg/lib`
- Includes: `/usr/pkg/include`
- GCC 14: `/usr/pkg/gcc14`

### 5. Build Environment

**OpenBSD:**
```makefile
env CFLAGS="-isystem /usr/local/include" \
    CXXFLAGS="-std=c++17 -fpermissive -Wno-error -isystem /usr/local/include" \
    LDFLAGS="-L/usr/local/lib -Wl,-R/usr/local/lib"
```

**NetBSD:**
```makefile
env CC=/usr/pkg/gcc14/bin/gcc \
    CXX=/usr/pkg/gcc14/bin/g++ \
    CFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" \
    CXXFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" \
    LDFLAGS="-L/usr/pkg/gcc14/lib -Wl,-R/usr/pkg/gcc14/lib -lstdc++" \
    LDSHARED="/usr/pkg/gcc14/bin/g++ -pthread -shared -L/usr/pkg/gcc14/lib -Wl,-R/usr/pkg/gcc14/lib" \
    TMPDIR=/var/tmp
```

### 6. OpenTelemetry Collector Build

**OpenBSD:**
- Requires GNU findutils for Makefile patches
- Uses `gfind` and `gxargs` in build process
- Patches replace native tools with GNU equivalents

**NetBSD:**
- No GNU tools required
- Native `find` and `xargs` work fine
- Cleaner build process

### 7. Package Installation

**OpenBSD:**
```sh
doas pkg_add go gmake findutils
```

**NetBSD:**
```sh
pkgin install go gcc14
```

## Similarities

Both versions share:
- Self-contained Makefile design
- Download sources on demand (~10KB tarball)
- grpcio 1.71.0 + OpenTelemetry Collector v0.91.0
- Same builder configuration (minimal components)
- Similar build times (~15-25 minutes total)
- Virtual environment integration
- Marker files for build state tracking

## Transferring Between Platforms

Each version creates its own tarball:

**OpenBSD:**
```sh
tar czf /tmp/otel-openbsd.tar.gz -C contrib/openbsd opentelemetry
```

**NetBSD:**
```sh
tar czf /tmp/otel-netbsd.tar.gz -C contrib/netbsd opentelemetry
```

## Which Version to Use?

- **On OpenBSD 7.7+**: Use `contrib/openbsd`
- **On NetBSD 10.x+**: Use `contrib/netbsd`
- **On FreeBSD**: Adapt OpenBSD version (uses similar package paths)

## Migration Notes

If adapting one for the other:

**OpenBSD → NetBSD:**
1. Remove `gmake` requirement
2. Add GCC 14 paths
3. Change `/usr/local` → `/usr/pkg`
4. Remove GNU tool dependencies
5. Remove directory_reader patch
6. Add TMPDIR=/var/tmp

**NetBSD → OpenBSD:**
1. Add `gmake` requirement
2. Remove GCC 14 specific paths
3. Change `/usr/pkg` → `/usr/local`
4. Add GNU findutils requirement
5. Add directory_reader patch
6. Use `~/tmp` for TMPDIR (OpenBSD /tmp is small)
