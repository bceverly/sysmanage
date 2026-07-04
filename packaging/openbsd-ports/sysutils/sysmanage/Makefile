# $OpenBSD$
#
# Phase 11.8 ports-tree submission stub — sysmanage (server).
# ``GH_TAGNAME`` is sed-replaced from ``v0.0.0`` to the release tag
# value by the ``openbsd-ports`` job in
# .github/workflows/build-and-release.yml.  Do not hand-edit on release.

COMMENT =		centralized system management server with web-based interface

GH_ACCOUNT =		bceverly
GH_PROJECT =		sysmanage
GH_TAGNAME =		v0.0.0
REVISION =		0

CATEGORIES =		sysutils

HOMEPAGE =		https://github.com/bceverly/sysmanage

MAINTAINER =		Bryan Everly <bryan@theeverlys.com>

# AGPLv3+
PERMIT_PACKAGE =	Yes

MODULES =		lang/python

RUN_DEPENDS =		www/py-aiohttp${MODPY_FLAVOR} \
			devel/py-aiofiles${MODPY_FLAVOR} \
			databases/py-alembic${MODPY_FLAVOR} \
			security/py-argon2-cffi${MODPY_FLAVOR} \
			security/py-bcrypt${MODPY_FLAVOR} \
			security/py-cryptography${MODPY_FLAVOR} \
			textproc/py-defusedxml${MODPY_FLAVOR} \
			www/py-fastapi${MODPY_FLAVOR} \
			www/py-httpx${MODPY_FLAVOR} \
			devel/py-jinja2${MODPY_FLAVOR} \
			textproc/py-mako${MODPY_FLAVOR} \
			devel/py-orjson${MODPY_FLAVOR} \
			graphics/py-Pillow${MODPY_FLAVOR} \
			sysutils/py-psutil${MODPY_FLAVOR} \
			databases/py-psycopg${MODPY_FLAVOR} \
			devel/py-pydantic${MODPY_FLAVOR} \
			textproc/py-yaml${MODPY_FLAVOR} \
			databases/py-sqlalchemy${MODPY_FLAVOR} \
			www/py-starlette${MODPY_FLAVOR} \
			www/py-uvicorn${MODPY_FLAVOR} \
			net/py-websockets${MODPY_FLAVOR} \
			databases/postgresql-server \
			www/nginx

NO_BUILD =		Yes
NO_TEST =		Yes
PKG_ARCH =		*

SUBST_VARS +=		SYSCONFDIR LOCALSTATEDIR

do-install:
	${INSTALL_DATA_DIR} ${PREFIX}/libexec/sysmanage
	cp -R ${WRKSRC}/backend ${PREFIX}/libexec/sysmanage/
	cp -R ${WRKSRC}/alembic ${PREFIX}/libexec/sysmanage/
	${INSTALL_DATA} ${WRKSRC}/alembic.ini ${PREFIX}/libexec/sysmanage/
	${INSTALL_DATA_DIR} ${PREFIX}/share/examples/sysmanage
	${INSTALL_DATA} ${WRKSRC}/installer/opensuse/sysmanage.yaml.example \
		${PREFIX}/share/examples/sysmanage/sysmanage.yaml
	${INSTALL_DATA} ${WRKSRC}/installer/opensuse/sysmanage-nginx.conf \
		${PREFIX}/share/examples/sysmanage/sysmanage-nginx.conf
	${INSTALL_DATA_DIR} ${DESTDIR}/etc/rc.d
	${INSTALL_SCRIPT} ${FILESDIR}/sysmanage.rc \
		${DESTDIR}/etc/rc.d/sysmanage

.include <bsd.port.mk>
