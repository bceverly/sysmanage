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

# OpenTelemetry is deliberately ABSENT.  backend/telemetry/otel_config.py
# imports the whole stack in one try/except that sets TELEMETRY_AVAILABLE=False
# and degrades gracefully, and three of the packages it needs
# (opentelemetry-exporter-prometheus, -instrumentation-logging,
# -instrumentation-sqlalchemy) do not exist in the ports tree.  Declaring the
# six that DO exist would pull six dependencies and still leave telemetry off,
# because the try block fails on the first missing import.  python-dotenv is
# likewise absent: nothing under backend/ or alembic/ imports it.
RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}aiohttp>0:www/py-aiohttp@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}aiofiles>0:devel/py-aiofiles@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}alembic>0:databases/py-alembic@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}argon2-cffi>0:security/py-argon2-cffi@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}authlib>0:security/py-authlib@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}bcrypt>0:security/py-bcrypt@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}cryptography>0:security/py-cryptography@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}defusedxml>0:devel/py-defusedxml@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}email-validator>0:mail/py-email-validator@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}fastapi>0:www/py-fastapi@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}GeoIP2>0:net/py-GeoIP2@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}gevent>0:devel/py-gevent@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}httptools>0:www/py-httptools@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}httpx>0:www/py-httpx@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}Jinja2>0:devel/py-Jinja2@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}ldap3>0:net/py-ldap3@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}mako>0:textproc/py-mako@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}multipart>0:devel/py-multipart@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}orjson>0:devel/py-orjson@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pillow>0:graphics/py-pillow@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}platformdirs>0:devel/py-platformdirs@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}psutil>0:sysutils/py-psutil@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}psycopg>0:databases/py-psycopg@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pydantic2>0:devel/py-pydantic2@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pydantic-extra-types>0:devel/py-pydantic-extra-types@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pydantic-settings>0:devel/py-pydantic-settings@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pyjwt>0:www/py-pyjwt@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pyotp>0:security/py-pyotp@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pyyaml>0:devel/py-pyyaml@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}reportlab>0:print/py-reportlab@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}requests>0:www/py-requests@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}sqlalchemy20>0:databases/py-sqlalchemy20@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}starlette>0:www/py-starlette@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}ujson>0:devel/py-ujson@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}urllib3>0:net/py-urllib3@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}uvicorn>0:www/py-uvicorn@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}watchfiles>0:devel/py-watchfiles@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}websockets>0:devel/py-websockets@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}zope.event>0:devel/py-zope.event@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}zope.interface>0:devel/py-zope.interface@${PY_FLAVOR} \
		nginx>0:www/nginx

# python:...,run — NO_BUILD means python is only needed at RUN time.
# Deliberately NO ``USE_PYTHON=autoplist``: autoplist generates the packing
# list for setuptools-installed modules, and this port has no setup.py — it
# stages source trees by hand below.  Together they produce a wrong plist.
# pgsql:15+ NOT a hardcoded databases/postgresql15-server RUN_DEPENDS.
# Pinning major 15 conflicts with the rest of the dependency tree: py-psycopg
# pulls the tree's DEFAULT PostgreSQL client (18 as of 2026-08), and
# postgresql15-client cannot coexist with postgresql18-client.  Installing
# both in one transaction silently deinstalled whichever landed first, so the
# port would have forced users onto an old major or failed outright.  USES
# takes the default version that satisfies 15+, matching psycopg.
USES=		pgsql:15+ python:3.9+,run shebangfix
WANT_PGSQL=	server
USE_GITHUB=	yes
GH_ACCOUNT=	bceverly
GH_PROJECT=	sysmanage
GH_TAGNAME=	v${DISTVERSION}

# The rc.d script runs the server as this user, and the port must CREATE it —
# nothing else will.  Without this the service starts and dies with
# "su: unknown login: sysmanage", which no build-time check catches: the
# package is perfectly well-formed, it just cannot run.  Found 2026-08-09
# by installing the package and starting the service.
#
# The matching entries go in ports/UIDs and ports/GIDs and travel WITH this
# port in the submission diff.  253 was free in both as of 2026-08-09;
# portmgr may reassign it, which is routine.
#
# The AGENT deliberately does NOT do this — it runs as root, because it
# manages the system and this port ships no sudoers.  The server is a web
# app and DB client, so least privilege applies here.
USERS=		sysmanage
GROUPS=		sysmanage

USE_RC_SUBR=	sysmanage

# PYTHON_CMD is NOT in the default SUB_LIST — USES=python contributes
# PYTHON_VERSION, PYTHON_VER, PYTHON_SUFFIX and friends, but not the
# interpreter path.  Without this line USE_RC_SUBR leaves the literal
# string %%PYTHON_CMD%% in the installed rc.d script, and the service
# fails at exec with no useful message.  Nothing catches it: the port
# builds, packages, passes check-plist and stage-qa, and installs — the
# placeholder only bites when the service is STARTED.  Found 2026-08-10
# via `sh -x` on the installed rc script.
SUB_LIST+=	PYTHON_CMD=${PYTHON_CMD}

NO_ARCH=	yes
NO_BUILD=	yes

PLIST_SUB+=	PORTNAME=${PORTNAME} VERSION=${DISTVERSION}

do-install:
	${MKDIR} ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}
	cd ${WRKSRC} && ${COPYTREE_SHARE} backend ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}
	cd ${WRKSRC} && ${COPYTREE_SHARE} alembic ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}
# The test suite is 4 MB and has no business in a runtime package: it is the
# only thing under backend/ that imports pytest, and shipping it would make
# pytest look like a runtime dependency to anyone auditing the port.  Pruning
# after the copytree rather than filtering inside it keeps the exclusion
# explicit and obvious; post-install builds the plist from what is actually
# staged, so the packing list follows automatically.
	@${RM} -r ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}/backend/tests \
		${STAGEDIR}${PREFIX}/libexec/${PORTNAME}/backend/benchmarks
	${INSTALL_DATA} ${WRKSRC}/alembic.ini ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}/
	${MKDIR} ${STAGEDIR}${PREFIX}/etc
# The ROOT sysmanage.yaml.example, not installer/opensuse's.  Every
# installer/*/sysmanage.yaml.example except ubuntu's is missing the
# ``api:`` and ``webui:`` sections that backend/config/config.py reads
# unguarded at import, so shipping one of those gives a package that
# installs and then dies with KeyError: 'api'.  The root example is the
# one the code actually matches.  (The stale installer examples are an
# upstream bug affecting centos/opensuse/macos/windows/netbsd/freebsd
# too — tracked separately; this port sidesteps it.)
	${INSTALL_DATA} ${WRKSRC}/sysmanage.yaml.example \
		${STAGEDIR}${PREFIX}/etc/sysmanage.yaml.sample
	${MKDIR} ${STAGEDIR}${PREFIX}/etc/nginx
	${INSTALL_DATA} ${WRKSRC}/installer/freebsd/sysmanage-nginx.conf \
		${STAGEDIR}${PREFIX}/etc/nginx/sysmanage-nginx.conf.sample
# Writable state.  The server runs unprivileged and GENERATES its mTLS CA and
# server certificate on first start; with nowhere to write it aborts in the
# FastAPI lifespan and the service never comes up.  The Linux packaging grants
# exactly this set — ReadWritePaths=/var/lib/sysmanage /var/log/sysmanage
# /etc/sysmanage in all three systemd units — and this port shipped none of it.
#
# /var/db is hier(7)'s home for generated state on FreeBSD, so the certificates
# live there rather than under /etc: they are produced by the program, not
# edited by the admin.  The rc script points SYSMANAGE_CERT_PATH and
# SYSMANAGE_LOG_DIR at these, so nothing depends on the code's built-in
# defaults (/etc/sysmanage/certs, which an unprivileged process cannot create).
#
# Ownership and mode come from the @dir() lines in pkg-plist — 0750, not 0700,
# because ca.crt must be readable by whatever serves it to agents; the private
# keys are chmod 0600 by the application itself.  Staging them here only lets
# check-plist match.  NOTE: pkg-plist has NO comment syntax — every line there
# is an entry, so this rationale has to live in the Makefile.
	${MKDIR} ${STAGEDIR}/var/db/${PORTNAME}/certs \
		${STAGEDIR}/var/log/${PORTNAME}

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
