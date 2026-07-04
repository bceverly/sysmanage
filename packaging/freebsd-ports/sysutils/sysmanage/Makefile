# Created by: Bryan Everly <bryan@theeverlys.com>
# $FreeBSD$
#
# Phase 11.8 stub — sysmanage (server).  ``DISTVERSION`` is sed-replaced
# from ``0.0.0`` to the release tag value by the ``freebsd-ports`` job
# in .github/workflows/build-and-release.yml.  Do not hand-edit on
# release.  ``distinfo`` (TIMESTAMP / SHA256 / SIZE) is also regenerated
# by the same job against the GitHub source tarball.

PORTNAME=	sysmanage
DISTVERSION=	0.0.0
CATEGORIES=	sysutils python
MASTER_SITES=	https://github.com/bceverly/sysmanage/archive/refs/tags/
DISTFILES=	v${DISTVERSION}${EXTRACT_SUFX}
DIST_SUBDIR=	sysmanage

MAINTAINER=	bryan@theeverlys.com
COMMENT=	Centralized system management server with web-based interface
WWW=		https://github.com/bceverly/sysmanage

LICENSE=	AGPLv3+
LICENSE_FILE=	${WRKSRC}/LICENSE

RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}aiohttp>=3.13.5:www/py-aiohttp@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}aiofiles>=24.1.0:devel/py-aiofiles@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}alembic>=1.16.5:databases/py-alembic@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}argon2-cffi>0:security/py-argon2-cffi@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}bcrypt>=4.0.0:security/py-bcrypt@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}cryptography>=46.0.7:security/py-cryptography@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}defusedxml>=0.7.1:devel/py-defusedxml@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}fastapi>0:www/py-fastapi@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}httpx>=0.27.2:www/py-httpx@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}jinja2>=3.1.6:devel/py-jinja2@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}Mako>=1.3.12:textproc/py-Mako@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}orjson>=3.11.6:devel/py-orjson@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}Pillow>=12.2.0:graphics/py-Pillow@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}psutil>0:sysutils/py-psutil@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}psycopg>=3.2:databases/py-psycopg@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pydantic>0:devel/py-pydantic@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}yaml>0:devel/py-yaml@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}sqlalchemy20>=2.0.43:databases/py-sqlalchemy20@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}starlette>0:www/py-starlette@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}uvicorn>0:www/py-uvicorn@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}websockets>=15.0.1:www/py-websockets@${PY_FLAVOR} \
		postgresql15-server>0:databases/postgresql15-server \
		nginx>0:www/nginx

USES=		python:3.9+ shebangfix
USE_PYTHON=	autoplist
USE_GITHUB=	yes
GH_ACCOUNT=	bceverly
GH_PROJECT=	sysmanage
GH_TAGNAME=	v${DISTVERSION}

USE_RC_SUBR=	sysmanage

NO_ARCH=	yes
NO_BUILD=	yes

PLIST_SUB+=	PORTNAME=${PORTNAME} VERSION=${DISTVERSION}

do-install:
	${MKDIR} ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}
	cd ${WRKSRC} && ${COPYTREE_SHARE} backend ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}
	cd ${WRKSRC} && ${COPYTREE_SHARE} alembic ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}
	${INSTALL_DATA} ${WRKSRC}/alembic.ini ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}/
	${MKDIR} ${STAGEDIR}${PREFIX}/etc
	${INSTALL_DATA} ${WRKSRC}/installer/opensuse/sysmanage.yaml.example \
		${STAGEDIR}${PREFIX}/etc/sysmanage.yaml.sample
	${MKDIR} ${STAGEDIR}${PREFIX}/etc/nginx
	${INSTALL_DATA} ${WRKSRC}/installer/opensuse/sysmanage-nginx.conf \
		${STAGEDIR}${PREFIX}/etc/nginx/sysmanage-nginx.conf.sample

.include <bsd.port.mk>
