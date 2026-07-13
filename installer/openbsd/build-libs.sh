#!/bin/sh
#
# build-libs.sh — assemble the "complete" OpenBSD distfile for the sysmanage
# port so the port itself can build FULLY OFFLINE (no pip / npm / compiler at
# port-build time; see installer/openbsd/Makefile).
#
# The distfile (sysmanage-<version>-openbsd.tar.gz, top dir
# sysmanage-<version>-openbsd/) bundles:
#   * the backend source,
#   * the pre-built web UI (frontend/dist — must already exist under <srcdir>;
#     it is built on Linux in CI because that is faster than the emulated VM),
#   * the pure-Python dependency bundle (pip-packages/).
#
# The pip bundle is kept 100% pure-Python (no compiled .so) by taking the heavy
# C/Rust deps from OpenBSD ports (they are RUN_DEPENDS of the port and are
# pkg_add'd here only so the --system-site-packages venv treats them as already
# satisfied — otherwise pip would rebuild cryptography/pydantic-core/... from
# source).  That keeps the distfile one-size-fits-all across OpenBSD/python
# versions.
#
# Run on OpenBSD, as root (it pkg_add's).  Usage:
#   build-libs.sh <version> <srcdir> <outdir>
#
set -e

VERSION="$1"
SRC="$2"
OUT="$3"

if [ -z "$VERSION" ] || [ -z "$SRC" ] || [ -z "$OUT" ]; then
	echo "usage: build-libs.sh <version> <srcdir> <outdir>" >&2
	exit 1
fi
if [ ! -d "$SRC/frontend/dist" ]; then
	echo "ERROR: $SRC/frontend/dist is missing — build the frontend first." >&2
	exit 1
fi

TOP="sysmanage-${VERSION}-openbsd"
STAGE="${OUT}/${TOP}"

# PyPI distributions provided by OpenBSD ports (excluded from the bundle) — must
# match RUN_DEPENDS in the port Makefile.  Their transitive C/Rust builders
# (pydantic-core, greenlet, cffi, MarkupSafe, ...) are provided by those ports.
PORT_PROVIDED="aiohttp alembic annotated-types argon2-cffi Babel bcrypt cffi \
cryptography gevent greenlet Jinja2 Mako MarkupSafe orjson Pillow pycparser \
pydantic pydantic-core PyYAML reportlab SQLAlchemy websockets zope.event \
zope.interface"

# Deliberately NOT shipped (keep the bundle pure-Python; all degrade
# gracefully — see the Makefile for the rationale).
OMIT="opentelemetry-exporter-otlp geoip2 maxminddb httptools ujson watchfiles"

# The dep ports, pkg_add'd so the venv sees them satisfied.
PKGS="py3-alembic py3-sqlalchemy py3-babel py3-gevent py3-pydantic py3-Pillow \
py3-websockets py3-reportlab py3-argon2-cffi py3-bcrypt py3-cryptography \
py3-orjson py3-yaml py3-aiohttp py3-jinja2"

echo "=== Installing dependency ports (so the venv skips them) ==="
# shellcheck disable=SC2086
pkg_add -I ${PKGS}

rm -rf "$STAGE"
mkdir -p "$STAGE/pip-packages" "$STAGE/frontend"

echo "=== Building the pure-Python pip bundle ==="
excl=$(echo "$PORT_PROVIDED $OMIT" | tr -s ' ' | tr ' ' '|')
grep -viE "^($excl)( |>|<|=|!|~|;|\[|$)" "$SRC/requirements-prod.txt" \
	| sed -E 's/psycopg\[binary\]/psycopg/' > "${OUT}/pip-bundle.txt"
echo "--- bundle list ---"; grep -vE '^[[:space:]]*#|^[[:space:]]*$' "${OUT}/pip-bundle.txt"

rm -rf "${OUT}/bldvenv"
python3 -m venv --system-site-packages "${OUT}/bldvenv"
PYTHONNOUSERSITE=1 "${OUT}/bldvenv/bin/python" -m pip install --no-cache-dir \
	-r "${OUT}/pip-bundle.txt"
cp -R "${OUT}/bldvenv/lib/python"*/site-packages/* "$STAGE/pip-packages/"
( cd "$STAGE/pip-packages" && rm -rf pip pip-*.dist-info wheel wheel-*.dist-info \
	_distutils_hack distutils-precedence.pth 2>/dev/null ) || true
find "$STAGE/pip-packages" -type d \( -name '__pycache__' -o -name '*.libs' \) \
	-exec rm -rf {} + 2>/dev/null || true

# The bundle MUST stay pure-Python so one distfile serves every version.
if find "$STAGE/pip-packages" -name '*.so' | grep -q .; then
	echo "ERROR: compiled .so found in the pip bundle:" >&2
	find "$STAGE/pip-packages" -name '*.so' >&2
	exit 1
fi

echo "=== Staging backend source + built frontend ==="
for d in backend alembic scripts installer sbom; do
	[ -d "$SRC/$d" ] && cp -R "$SRC/$d" "$STAGE/"
done
for f in alembic.ini requirements-prod.txt README.md LICENSE sysmanage.yaml.example; do
	[ -f "$SRC/$f" ] && cp "$SRC/$f" "$STAGE/"
done
cp -R "$SRC/frontend/dist" "$STAGE/frontend/dist"
# Stamp the version so backend.__version__ resolves at runtime.
printf '__version__ = "%s"\n' "$VERSION" > "$STAGE/backend/__init__.py"

echo "=== Creating ${TOP}.tar.gz ==="
( cd "$OUT" && tar czf "${TOP}.tar.gz" "$TOP" )
ls -lh "${OUT}/${TOP}.tar.gz"
echo "Done."
