# Phase 11.8 stub — sysmanage (server).  ``DISTVERSION`` is sed-replaced
# from ``0.0.0`` to the release tag value by the ``freebsd-ports`` job
# in .github/workflows/build-and-release.yml.  Do not hand-edit on
# release.  ``distinfo`` (TIMESTAMP / SHA256 / SIZE) is also regenerated
# by the same job against the GitHub source tarball.

PORTNAME=	sysmanage
DISTVERSION=	0.0.0
CATEGORIES=	sysutils python
# No MASTER_SITES / DISTFILES / DIST_SUBDIR ASSIGNMENT here on purpose: USE_GITHUB
# below derives all three from GH_ACCOUNT/GH_PROJECT/GH_TAGNAME, and a plain "="
# would redefine what it derived — portlint flags that, and the two can disagree
# about what is fetched.  Further down, MASTER_SITES is APPENDED (+=) with a
# :prefetch group for the node-modules distfile USES=npm generates; += adds to
# what USE_GITHUB derived rather than replacing it.

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

# python:...,run — the build compiles the web UI with node, not python, so
# python is a RUN dependency only even though this port does build.
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
# python:3.10+, NOT 3.9+.  The Debian control file requires python3 (>= 3.10)
# and the backend uses syntax that 3.9 cannot parse; declaring 3.9+ would let
# the port install against a 3.9 default and fail at first import, which no
# build-time check catches.  (The AGENT is genuinely 3.9-compatible — it has a
# 3.9 CI leg — so the two ports differ here on purpose.)
# nodejs:build MUST come with an explicit ``build`` argument.  npm.mk includes
# nodejs.mk itself, and nodejs.mk's own default registers node as a RUN
# dependency -- so USES=npm alone put www/node24 in RUN_DEPENDS, making every
# user of the binary package install a ~100 MB Node runtime that is never
# executed (the port runs node once, at build time, to compile the web UI).
# Confirmed 2026-08-10 with ``make run-depends-list | grep node``; nothing in
# the build, poudriere, check-plist or stage-qa notices, because a superfluous
# runtime dependency is not an error -- just a cost paid by everyone.
USES=		nodejs:build npm:npm,build pgsql:15+ python:3.10+,run shebangfix

# shebangfix does nothing without SHEBANG_FILES: it rewrites only the files
# named here.  sysmanage_migrate.py starts with "#!/usr/bin/env python3",
# which stage-qa flags and which would resolve to whatever python3 happens to
# be first in PATH rather than the interpreter this port depends on.
SHEBANG_FILES=	scripts/sysmanage_migrate.py
WANT_PGSQL=	server
USE_GITHUB=	yes
GH_ACCOUNT=	bceverly
GH_PROJECT=	sysmanage
GH_TAGNAME=	v${DISTVERSION}

# The web UI is BUILT HERE, from the source in the GitHub tarball -- this port
# runs ``vite build`` itself.  It does not install anyone's pre-built HTML.
#
# Dependency handling is the ports framework's, not ours.  USES=npm drives it:
# during the FETCH phase (targets npm-fetch-node-modules / npm-archive-node-
# modules) it runs ``npm ci`` against the lockfile stored in PKGJSONSDIR and
# archives the result into ONE distfile,
#     ${PORTNAME}-${DISTVERSION}-node-modules${EXTRACT_SUFX}
# in the :prefetch group, which it also adds to DISTFILES itself.  Everything
# after fetch is offline, which is what the package cluster requires.
#
# ``build`` is passed EXPLICITLY and must stay.  npm.mk's no-argument default
# branch reads ``!defied(_NPM_EXTRACT_DEP)`` -- a typo for !defined -- so
# omitting the stage argument takes a branch that does not evaluate.  (Reported
# upstream; zero ports in the tree currently use USES=npm, which is consistent
# with that path never having been exercised.)
#
# PKGJSONSDIR keeps directory hierarchy, so files/packagejsons/frontend/
# lands node_modules at ${WRKSRC}/frontend/node_modules exactly where vite
# expects it -- no NPM_EXTRACT_WRKSRC override needed.
# NPM_PKGFILE is not cosmetic.  npm.mk enables the whole prefetch mechanism on
# ``exists(${PKGJSONSDIR}/${NPM_PKGFILE})``, which defaults to
# files/packagejsons/package.json -- a path we do not have, because this
# application keeps its frontend in a subdirectory.  With the default the probe
# fails, NPM_PREFETCH turns itself off, no node-modules distfile is generated
# or checksummed, and the port sails through makesum looking healthy right up
# until do-build cannot find vite.  Found 2026-08-10: distinfo came back with
# only the GitHub tarball in it.
NPM_PKGFILE=	frontend/package.json

MASTER_SITES+=	https://repo.sysmanage.org/server/freebsd/:prefetch

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
# The AGENT creates a SEPARATE account (sysmanage-agent, uid 255) and must
# keep it separate: its sudoers policy is root-equivalent, and sharing one
# account would let a compromise of this web application inherit those
# grants.  The two ports must never converge on one user.
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

# The bootstrap wrapper and the package message both need substitution.
# USE_RC_SUBR handles the rc script; SUB_FILES covers the rest.
SUB_FILES=	pkg-message sysmanage-nginx.conf

# NO_ARCH stays: the PACKAGE is architecture-independent (Python source plus
# the static JS/CSS vite emits).  The BUILD is not — it runs node — but that is
# a build-time property and does not make the package arch-specific.
NO_ARCH=	yes

# NO_BUILD is deliberately GONE.  The port compiles the web UI itself in
# do-build below.
#
# Everything here exists so the build works on the FreeBSD package cluster,
# where poudriere gives the build jail NO network and NO writable home.  npm
# will, unasked, try to reach the registry for audit/funding metadata and will
# write a cache into $HOME; either one fails the build in the jail, and the
# failure reads as a dependency problem rather than an environment one.
#   HOME             -> WRKDIR, so nothing is written outside the work area
#   npm_config_cache -> WRKDIR, same reason
#   offline=true     -> refuse to hit the network at all, so a missing vendored
#                       package fails LOUDLY here instead of silently
#                       downloading on a developer's networked machine and then
#                       failing only on the cluster
#   audit/fund=false -> both are pure network calls with no build value
# npm writes a cache into $HOME and phones home for update notices; inside the
# package cluster's jail there is neither a writable home nor a network, and
# either failure reads as a dependency problem rather than an environment one.
# USES=npm already passes the equivalent flags to its own fetch command; this
# covers the ``npm run build`` invocation in do-build.
MAKE_ENV+=	HOME=${WRKDIR} \
		npm_config_cache=${WRKDIR}/.npm \
		npm_config_update_notifier=false

PLIST_SUB+=	PORTNAME=${PORTNAME} VERSION=${DISTVERSION}

# Build the web UI from source.  ``vite build`` is what package.json's build
# script runs, and it is invoked through npm so the port does not encode vite's
# internal entry point.
#
# The explicit test afterwards matters: vite can exit 0 having emitted nothing
# useful, and an empty dist/ produces a package that installs cleanly and
# serves a blank page.  Fail here instead.
do-build:
	cd ${WRKSRC}/frontend && ${SETENV} ${MAKE_ENV} ${LOCALBASE}/bin/npm run build
	@${TEST} -s ${WRKSRC}/frontend/dist/index.html || { \
		${ECHO_MSG} "ERROR: vite produced no frontend/dist/index.html." ; \
		exit 1 ; }

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
# The schema tool.  Nothing runs alembic at startup, so without this the
# database stays empty and the server has no tables — it is the step the Debian
# postinst prints as "3. Database Migration".
#
# Only THIS script, not all of scripts/.  The Debian package ships the whole
# directory (debian/install: "scripts/* opt/sysmanage/scripts/"), but that is
# 1.8 MB and 87 entries of development tooling — i18n checkers, CI gates,
# CodeQL dumpers, test-network builders — none of which belongs in a runtime
# package, and most of which carries bash shebangs that would drag
# shells/bash in as a dependency for no runtime benefit.  It resolves its
# project root as the PARENT of its own directory, so the scripts/ level must
# be preserved for backend/ and alembic/ to be importable.
	${MKDIR} ${STAGEDIR}${PREFIX}/libexec/${PORTNAME}/scripts
	${INSTALL_SCRIPT} ${WRKSRC}/scripts/sysmanage_migrate.py \
		${STAGEDIR}${PREFIX}/libexec/${PORTNAME}/scripts/
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
# The shipped conf serves the web UI from /opt/sysmanage/frontend/dist, a Linux
# install path that does not exist on FreeBSD and that nothing here creates, so
# the sample would look configured while returning 404 for every page.  Rewrite
# it to a hier(7)-correct location.  NOTE: this port does NOT ship the frontend
# -- frontend/dist is gitignored, so it is absent from the release tarball, and
# a port cannot run npm at build time (no network).  The directory is therefore
# empty unless an admin deploys a build into it; pkg-message says so plainly.
# From files/, NOT from the tarball -- see the header of that file.
	${INSTALL_DATA} ${WRKDIR}/sysmanage-nginx.conf \
		${STAGEDIR}${PREFIX}/etc/nginx/sysmanage-nginx.conf.sample
# Where the admin puts the TLS keypair nginx serves.  Created empty and
# root-only: nginx reads certificates as root before dropping privileges, so
# the private key never needs to be readable by the www user, and 0700 keeps a
# mistake from exposing it.  The port does NOT generate a certificate -- see
# the nginx sample for why.
	${MKDIR} ${STAGEDIR}${PREFIX}/etc/sysmanage/tls
# The built web UI, from the :frontend distfile.  Fail LOUDLY if it is absent
# rather than quietly producing a package with no user interface — that is the
# defect this whole distfile exists to prevent, and a silent empty directory
# looks identical to a working install until someone opens a browser.  The
# OpenBSD port guards the same way for the same reason.
	${MKDIR} ${STAGEDIR}${PREFIX}/www/${PORTNAME}
	cd ${WRKSRC}/frontend/dist && \
		${COPYTREE_SHARE} . ${STAGEDIR}${PREFIX}/www/${PORTNAME}
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
		${STAGEDIR}${PREFIX}/libexec/${PORTNAME}/alembic \
		${STAGEDIR}${PREFIX}/www/${PORTNAME} -type f \
		| ${SED} -e 's,^${STAGEDIR}${PREFIX}/,,' >> ${TMPPLIST}

.include <bsd.port.mk>
