# $OpenBSD$

COMMENT =		centralized system management server

V =			0.0.0		# auto-updated by CI / make installer
DISTNAME =		sysmanage-${V}-openbsd
PKGNAME =		sysmanage-${V}
REVISION =		0

CATEGORIES =		sysutils www

HOMEPAGE =		https://sysmanage.org

MAINTAINER =		Bryan Everly <bryan@theeverlys.com>

# AGPLv3
PERMIT_PACKAGE =	Yes

# --- Offline build model ---------------------------------------------------
#
# This port builds FULLY OFFLINE (no pip / npm / compiler at build time): all
# network access happens in the fetch phase, as OpenBSD ports policy expects.
# It fetches a SINGLE pre-built distfile from the SysManage R2 repository,
# produced by the release pipeline, containing everything needed:
#
#   * the backend source,
#   * the built web UI (frontend/dist),
#   * the pure-Python dependency bundle (pip-packages/).
#
# The pip-packages bundle is 100% pure-Python (no compiled .so), so one distfile
# serves every OpenBSD/python version.  The heavy C/Rust runtime deps
# (cryptography, pydantic, Pillow, ...) are NOT bundled — they come from OpenBSD
# ports (RUN_DEPENDS below), verified present via openbsd.app.  At runtime,
# PYTHONPATH = the app + pip-packages, and the system ports satisfy the rest
# (see files/sysmanage.rc).
MASTER_SITES =		https://repo.sysmanage.org/server/openbsd/

MODULES =		lang/python
MODPY_VERSION =		${MODPY_DEFAULT_VERSION_3}

# Nothing to compile — everything in the distfile is pre-built.
NO_BUILD =		Yes

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
# postgresql is a multi-package port; its ,-main subpackage IS postgresql-client
# (ships libpq.so), so that is the correct dependency spec.
RUN_DEPENDS +=		databases/postgresql,-main

NO_TEST =		Yes

# Installation directories
SUBST_VARS +=		SYSCONFDIR LOCALSTATEDIR

# User and group for the daemon
SYSMANAGE_USER =	_sysmanage
SYSMANAGE_GROUP =	_sysmanage

# Stamp the package version into backend/__init__.py so backend.__version__
# resolves at runtime (server-info + federation "Reported version" show it
# instead of "unknown"); the GitHub source tarball ships it empty.
post-extract:
	printf '__version__ = "%s"\n' "${V}" > ${WRKSRC}/backend/__init__.py

do-install:
	# Backend Python application
	${INSTALL_DATA_DIR} ${PREFIX}/libexec/sysmanage
	cp -R ${WRKSRC}/backend ${PREFIX}/libexec/sysmanage/
	cp -R ${WRKSRC}/alembic ${PREFIX}/libexec/sysmanage/
	${INSTALL_DATA} ${WRKSRC}/alembic.ini ${PREFIX}/libexec/sysmanage/

	# Bundled pure-Python dependencies (from the libs distfile; runtime
	# PYTHONPATH points here — see files/sysmanage.rc).
	@test -d ${WRKSRC}/pip-packages || { \
		echo "ERROR: ${WRKSRC}/pip-packages is missing — the openbsd-libs" ; \
		echo "distfile was not fetched/extracted.  Refusing to package." ; \
		exit 1 ; }
	cp -R ${WRKSRC}/pip-packages ${PREFIX}/libexec/sysmanage/

	# Frontend static files (from the libs distfile).  A missing frontend is a
	# hard error: shipping a server without its UI is exactly the defect this
	# port must never reproduce.
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
