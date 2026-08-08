# Phase 11.8 stub — sysmanage (server).  ``DISTVERSION`` is sed-replaced
# from ``0.0.0`` to the release tag value by the ``freebsd-ports`` job
# in .github/workflows/build-and-release.yml.  Do not hand-edit on
# release.  ``distinfo`` (TIMESTAMP / SHA256 / SIZE) is also regenerated
# by the same job against the GitHub source tarball.

PORTNAME=	sysmanage
DISTVERSION=	0.0.0
CATEGORIES=	sysutils python
# No MASTER_SITES / DISTFILES / DIST_SUBDIR here on purpose: USE_GITHUB below
# derives all three from GH_ACCOUNT/GH_PROJECT/GH_TAGNAME.  Setting both is
# redundant, portlint flags it, and the two can disagree about what is fetched.

MAINTAINER=	bryan@theeverlys.com
COMMENT=	Centralized system management server with web-based interface
WWW=		https://github.com/bceverly/sysmanage

LICENSE=	AGPLv3+
LICENSE_FILE=	${WRKSRC}/LICENSE

RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}aiohttp>0:www/py-aiohttp@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}aiofiles>0:devel/py-aiofiles@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}alembic>0:databases/py-alembic@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}argon2-cffi>0:security/py-argon2-cffi@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}bcrypt>0:security/py-bcrypt@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}cryptography>0:security/py-cryptography@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}defusedxml>0:devel/py-defusedxml@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}fastapi>0:www/py-fastapi@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}httpx>0:www/py-httpx@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}Jinja2>0:devel/py-Jinja2@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}mako>0:textproc/py-mako@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}orjson>0:devel/py-orjson@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pillow>0:graphics/py-pillow@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}psutil>0:sysutils/py-psutil@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}psycopg>0:databases/py-psycopg@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pydantic2>0:devel/py-pydantic2@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pyjwt>0:www/py-pyjwt@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pyotp>0:security/py-pyotp@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pyyaml>0:devel/py-pyyaml@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}requests>0:www/py-requests@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}sqlalchemy20>0:databases/py-sqlalchemy20@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}starlette>0:www/py-starlette@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}urllib3>0:net/py-urllib3@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}uvicorn>0:www/py-uvicorn@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}websockets>0:devel/py-websockets@${PY_FLAVOR} \
		postgresql15-server>0:databases/postgresql15-server \
		nginx>0:www/nginx

# python:...,run — NO_BUILD means python is only needed at RUN time.
# Deliberately NO ``USE_PYTHON=autoplist``: autoplist generates the packing
# list for setuptools-installed modules, and this port has no setup.py — it
# stages source trees by hand below.  Together they produce a wrong plist.
USES=		python:3.9+,run shebangfix
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

# ``backend`` and ``alembic`` are hundreds of files that change every release,
# so they cannot be enumerated by hand in pkg-plist — an unlisted staged file
# fails stage-qa, which the 3-line plist would have done on the first real
# build.  Appending the staged trees to ${TMPPLIST} is the in-tree idiom for a
# generated file set.  pkg-plist keeps the fixed entries.
post-install:
	@${FIND} -s ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}/backend \
		${STAGEDIR}${PREFIX}/libexec/${PORTNAME}/alembic -type f \
		| ${SED} -e 's,^${STAGEDIR}${PREFIX}/,,' >> ${TMPPLIST}

.include <bsd.port.mk>
