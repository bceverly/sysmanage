# $OpenBSD$

COMMENT =		centralized system management server

GH_ACCOUNT =		bceverly
GH_PROJECT =		sysmanage
GH_TAGNAME =		v0.0.0		# auto-updated by CI / make installer
REVISION =		0

CATEGORIES =		sysutils www

HOMEPAGE =		https://sysmanage.org

MAINTAINER =		Bryan Everly <bryan@theeverlys.com>

# AGPLv3
PERMIT_PACKAGE =	Yes

MODULES =		lang/python
MODPY_VERSION =		${MODPY_DEFAULT_VERSION_3}

# --- Runtime Python dependencies -------------------------------------------
#
# The server has ~60 runtime Python deps.  We split them (see the Alpine
# APKBUILD, which uses the same hybrid model):
#
#   * The heavy C / Rust extension deps come from OpenBSD ports below, so they
#     are NEVER compiled from source in the (emulated, slow) build VM.  Every
#     path here was verified present in the current ports tree via openbsd.app.
#     Transitive C/Rust deps (py-pydantic-core, py-greenlet, py-cffi,
#     py-MarkupSafe, ...) are pulled in automatically by these top-level ports.
#   * The remaining ~45 pure-Python deps are bundled at their exact,
#     CVE-pinned versions into a private ${PREFIX}/libexec/sysmanage/pip-packages
#     directory by the pip step in do-build (PYTHONPATH points there at
#     runtime — see files/sysmanage.rc).  Bundling keeps our security pins
#     (which ports may lag) for the pure-Python surface.
#
# The frontend cannot be built on OpenBSD at all (Vite/rolldown ships no
# OpenBSD native binary), so the built frontend/dist is produced on Linux in CI
# and rsynced into ${WRKSRC}/frontend/dist before the build — see
# .github/workflows/build-openbsd-packages.yml.
RUN_DEPENDS =		databases/py-alembic${MODPY_FLAVOR} \
			databases/py-sqlalchemy${MODPY_FLAVOR} \
			devel/py-babel${MODPY_FLAVOR} \
			devel/py-gevent${MODPY_FLAVOR} \
			devel/py-pydantic${MODPY_FLAVOR} \
			graphics/py-Pillow${MODPY_FLAVOR} \
			net/py-websockets${MODPY_FLAVOR} \
			print/py-reportlab${MODPY_FLAVOR} \
			security/py-argon2-cffi${MODPY_FLAVOR} \
			security/py-bcrypt${MODPY_FLAVOR} \
			security/py-cryptography${MODPY_FLAVOR} \
			textproc/py-orjson${MODPY_FLAVOR} \
			textproc/py-yaml${MODPY_FLAVOR} \
			www/py-aiohttp${MODPY_FLAVOR} \
			www/py-jinja2${MODPY_FLAVOR}

# libpq for the (pure-Python) psycopg 3 adapter bundled via pip — OpenBSD has
# no psycopg 3 port (only databases/py-psycopg2, a different module), so plain
# `psycopg` is pip-bundled and loads libpq.so at runtime from postgresql-client.
RUN_DEPENDS +=		databases/postgresql-client

# The ports above must be present at BUILD time too, so `pip install --target`
# sees them already satisfied and does NOT drag their C/Rust deps back into the
# pip resolution (which would compile cryptography/pydantic-core/... from
# source).  py-pip drives the bundle step.  CI runs the build with
# FETCH_PACKAGES=Yes so these are pkg_add'd as binaries, not built.
BUILD_DEPENDS =		${RUN_DEPENDS} \
			devel/py-pip${MODPY_FLAVOR}

NO_TEST =		Yes

# Installation directories
SUBST_VARS +=		SYSCONFDIR LOCALSTATEDIR

# User and group for the daemon
SYSMANAGE_USER =	_sysmanage
SYSMANAGE_GROUP =	_sysmanage

# PyPI distributions already provided by the RUN_DEPENDS ports above (and their
# port-provided transitive C/Rust builders).  These lines are stripped from
# requirements-prod.txt before the pip bundle so their exact security pins do
# not force a from-source rebuild of the very extensions we took from ports.
# NB: psycopg is intentionally NOT here — it is pip-bundled (see above).
PIP_PORT_PROVIDED =	aiohttp alembic annotated-types argon2-cffi Babel \
			bcrypt cffi cryptography gevent greenlet Jinja2 Mako \
			MarkupSafe orjson Pillow pycparser pydantic \
			pydantic-core PyYAML reportlab SQLAlchemy \
			websockets zope.event zope.interface

# PyPI distributions deliberately NOT shipped on OpenBSD, each because it would
# drag a heavy compiled toolchain into the VM for functionality that degrades
# gracefully:
#   * opentelemetry-exporter-otlp pulls grpcio (a large C++ build with no
#     OpenBSD port); backend/telemetry/otel_config.py imports the OTLP exporter
#     under try/except ImportError and disables telemetry when it is absent.
#   * watchfiles is a Rust extension used only by `uvicorn --reload` (dev);
#     production uvicorn runs fine without it.
PIP_OMIT =		opentelemetry-exporter-otlp watchfiles

# Stamp the package version into backend/__init__.py so backend.__version__
# resolves at runtime (server-info + federation "Reported version" show it
# instead of "unknown"); the GitHub source tarball ships it empty.
post-extract:
	printf '__version__ = "%s"\n' "${GH_TAGNAME:S/^v//}" > ${WRKSRC}/backend/__init__.py

# Build the private pip bundle of the pure-Python deps not provided by ports.
# The exclusion alternation is built from PIP_PORT_PROVIDED; each excluded name
# must be followed by a version/marker boundary so e.g. "pydantic" does not also
# strip "pydantic-settings" / "pydantic-extra-types" (both pip-bundled).
do-build:
	@cd ${WRKSRC} && { \
		excl=$$(echo '${PIP_PORT_PROVIDED} ${PIP_OMIT}' | tr ' ' '|') ; \
		grep -viE "^($$excl)( |>|<|=|!|~|;|\[|$$)" requirements-prod.txt \
			| sed -E 's/psycopg\[binary\]/psycopg/' \
			> ${WRKDIR}/pip-bundle.txt ; \
		echo "=== pip bundle (pure-Python deps not from ports) ===" ; \
		cat ${WRKDIR}/pip-bundle.txt ; }
	${MODPY_BIN} -m pip install \
		--target=${WRKSRC}/pip-packages \
		--no-compile --no-cache-dir \
		-r ${WRKDIR}/pip-bundle.txt
	# Drop bundled *.libs shims and __pycache__ so the package stays lean and
	# does not ship duplicate copies of system shared libraries.
	@find ${WRKSRC}/pip-packages -type d -name '*.libs' -exec rm -rf {} + 2>/dev/null || true
	@find ${WRKSRC}/pip-packages -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

do-install:
	# Backend Python application
	${INSTALL_DATA_DIR} ${PREFIX}/libexec/sysmanage
	cp -R ${WRKSRC}/backend ${PREFIX}/libexec/sysmanage/
	cp -R ${WRKSRC}/alembic ${PREFIX}/libexec/sysmanage/
	${INSTALL_DATA} ${WRKSRC}/alembic.ini ${PREFIX}/libexec/sysmanage/

	# Bundled pure-Python dependencies (runtime PYTHONPATH; see files/sysmanage.rc)
	cp -R ${WRKSRC}/pip-packages ${PREFIX}/libexec/sysmanage/

	# Frontend static files.  A missing frontend is a hard error: shipping a
	# server without its UI is exactly the defect this port must never
	# reproduce.  CI injects the Linux-built dist into ${WRKSRC}/frontend/dist.
	${INSTALL_DATA_DIR} ${PREFIX}/share/sysmanage/frontend
	@test -d ${WRKSRC}/frontend/dist || { \
		echo "ERROR: ${WRKSRC}/frontend/dist is missing — the frontend was" ; \
		echo "not built/injected.  Refusing to package a UI-less server." ; \
		exit 1 ; }
	cp -R ${WRKSRC}/frontend/dist/* ${PREFIX}/share/sysmanage/frontend/

	# Example configuration
	${INSTALL_DATA_DIR} ${PREFIX}/share/examples/sysmanage
	test -f ${WRKSRC}/sysmanage.yaml.example && \
		${INSTALL_DATA} ${WRKSRC}/sysmanage.yaml.example \
			${PREFIX}/share/examples/sysmanage/sysmanage.yaml || true

	# Documentation
	${INSTALL_DATA_DIR} ${PREFIX}/share/doc/sysmanage
	${INSTALL_DATA} ${WRKSRC}/README.md ${PREFIX}/share/doc/sysmanage/
	test -f ${WRKSRC}/LICENSE && \
		${INSTALL_DATA} ${WRKSRC}/LICENSE ${PREFIX}/share/doc/sysmanage/ || true

	# SBOM
	${INSTALL_DATA_DIR} ${PREFIX}/share/doc/sysmanage/sbom
	test -f ${WRKSRC}/sbom/backend-sbom.json && \
		${INSTALL_DATA} ${WRKSRC}/sbom/backend-sbom.json \
			${PREFIX}/share/doc/sysmanage/sbom/ || true
	test -f ${WRKSRC}/sbom/frontend-sbom.json && \
		${INSTALL_DATA} ${WRKSRC}/sbom/frontend-sbom.json \
			${PREFIX}/share/doc/sysmanage/sbom/ || true

	# RC script
	${INSTALL_DATA_DIR} ${DESTDIR}/etc/rc.d
	${INSTALL_SCRIPT} ${FILESDIR}/sysmanage.rc \
		${DESTDIR}/etc/rc.d/sysmanage

	# OpenBAO secrets broker (Phase 13.1.H/13.1.I): rc.d service + the shared
	# config + the init/unseal helper.  OpenBSD has no OpenBAO package, so the
	# rc script provisions the verified prebuilt 'bao' binary on first start.
	${INSTALL_SCRIPT} ${FILESDIR}/openbao.rc \
		${DESTDIR}/etc/rc.d/openbao
	${INSTALL_DATA_DIR} ${PREFIX}/share/examples/openbao
	test -f ${WRKSRC}/installer/openbao/openbao.hcl && \
		${INSTALL_DATA} ${WRKSRC}/installer/openbao/openbao.hcl \
			${PREFIX}/share/examples/openbao/openbao.hcl || true
	${INSTALL_DATA_DIR} ${PREFIX}/libexec/sysmanage/scripts
	test -f ${WRKSRC}/scripts/openbao_init_unseal.py && \
		${INSTALL_SCRIPT} ${WRKSRC}/scripts/openbao_init_unseal.py \
			${PREFIX}/libexec/sysmanage/scripts/openbao_init_unseal.py || true

.include <bsd.port.mk>
