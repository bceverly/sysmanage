# $OpenBSD$

COMMENT =		centralized system management server

GH_ACCOUNT =		bceverly
GH_PROJECT =		sysmanage
GH_TAGNAME =ttv0.9.0.9
REVISION =		0

CATEGORIES =		sysutils www

HOMEPAGE =		https://sysmanage.org

MAINTAINER =		Bryan Everly <bryan@theeverlys.com>

# AGPLv3
PERMIT_PACKAGE =	Yes

MODULES =		lang/python

MODPY_VERSION =		${MODPY_DEFAULT_VERSION_3}

# Python backend dependencies
RUN_DEPENDS =		databases/py-sqlalchemy${MODPY_FLAVOR} \
			databases/py-alembic${MODPY_FLAVOR} \
			databases/py-psycopg2${MODPY_FLAVOR} \
			devel/py-babel${MODPY_FLAVOR} \
			net/py-websockets${MODPY_FLAVOR} \
			security/py-cryptography${MODPY_FLAVOR} \
			textproc/py-yaml${MODPY_FLAVOR} \
			www/py-aiohttp${MODPY_FLAVOR} \
			www/py-uvicorn${MODPY_FLAVOR} \
			www/py-fastapi${MODPY_FLAVOR}

# PostgreSQL is required for production
RUN_DEPENDS +=		databases/postgresql

NO_BUILD =		Yes
NO_TEST =		Yes

# Installation directories
SUBST_VARS +=		SYSCONFDIR LOCALSTATEDIR

# User and group for the daemon
SYSMANAGE_USER =	_sysmanage
SYSMANAGE_GROUP =	_sysmanage

do-install:
	# Backend Python application
	${INSTALL_DATA_DIR} ${PREFIX}/libexec/sysmanage/backend
	test -d ${WRKSRC}/backend && \
		cp -R ${WRKSRC}/backend ${PREFIX}/libexec/sysmanage/ || true
	test -d ${WRKSRC}/alembic && \
		cp -R ${WRKSRC}/alembic ${PREFIX}/libexec/sysmanage/ || true
	test -f ${WRKSRC}/alembic.ini && \
		${INSTALL_DATA} ${WRKSRC}/alembic.ini ${PREFIX}/libexec/sysmanage/ || true

	# Frontend static files
	${INSTALL_DATA_DIR} ${PREFIX}/share/sysmanage/frontend
	test -d ${WRKSRC}/frontend/dist && \
		cp -R ${WRKSRC}/frontend/dist/* ${PREFIX}/share/sysmanage/frontend/ || true

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

.include <bsd.port.mk>
