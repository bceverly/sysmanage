# sysmanage-canary -- the outside watcher for a SysManage server (Phase 22.9).
# ``DISTVERSION`` is sed-replaced from ``0.0.0`` to the release tag value by
# the ``freebsd-ports`` job in .github/workflows/build-and-release.yml, and
# ``distinfo`` is regenerated there too.  Do not hand-edit on release.
#
# A port of its own, not part of sysutils/sysmanage: the canary is meant to
# run on a DIFFERENT machine from the server it watches, and that machine
# should not have to install the server, nginx and PostgreSQL to get it.  It
# is built from the same GitHub tarball (the canary lives in the server's
# repository), so the distfile and its distinfo key are the server port's.

PORTNAME=	sysmanage-canary
DISTVERSION=	0.0.0
CATEGORIES=	sysutils python

MAINTAINER=	bryan@theeverlys.com
COMMENT=	Outside watcher that emails when a SysManage server stops working
WWW=		https://github.com/bceverly/sysmanage

LICENSE=	AGPLv3+
LICENSE_FILE=	${WRKSRC}/LICENSE

# The canary keeps to the standard library plus these two, so that nothing
# the server depends on can break it.  psycopg is for the database checks;
# py-psycopg pulls the tree's default PostgreSQL client library.
RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}psycopg>0:databases/py-psycopg@${PY_FLAVOR} \
		${PYTHON_PKGNAMEPREFIX}pyyaml>0:devel/py-pyyaml@${PY_FLAVOR}

USES=		python:run
USE_GITHUB=	yes
GH_ACCOUNT=	bceverly
GH_PROJECT=	sysmanage
GH_TAGNAME=	v${DISTVERSION}

# The canary runs unprivileged as its OWN account, never the server's
# ``sysmanage``: it holds a database role and SMTP credentials of its own, and
# it is often installed where no server exists.  The matching entries go in
# ports/UIDs and ports/GIDs with this port in the submission diff.  404 was
# free in both upstream as of 2026-10-07 (402/403 are proposed for the server
# and agent ports, whose old 253/255 are taken upstream).
USERS=		sysmanage-canary
GROUPS=		sysmanage-canary

USE_RC_SUBR=	sysmanage_canary
# PYTHON_CMD is not in the default SUB_LIST; the rc script names the
# interpreter for the launcher.
SUB_LIST+=	PYTHON_CMD=${PYTHON_CMD}
SUB_FILES=	pkg-message

NO_ARCH=	yes
NO_BUILD=	yes

# Only the canary/ directory of the tarball is installed.  The launcher looks
# for the library in ${PREFIX}/lib/sysmanage-canary, the same place the
# FreeBSD binary package puts it.
do-install:
	${MKDIR} ${STAGEDIR}${PREFIX}/lib/${PORTNAME}
	cd ${WRKSRC}/canary && ${COPYTREE_SHARE} sysmanage_canary \
		${STAGEDIR}${PREFIX}/lib/${PORTNAME} "! -name *.pyc ! -name __pycache__"
	${INSTALL_SCRIPT} ${WRKSRC}/canary/bin/sysmanage-canary \
		${STAGEDIR}${PREFIX}/bin/
	${INSTALL_DATA} ${WRKSRC}/canary/sysmanage-canary.yaml.example \
		${STAGEDIR}${PREFIX}/etc/sysmanage-canary.yaml.sample

# The library is a tree that grows with each release (one locale file per
# language), so it is appended to the packing list rather than listed by hand.
post-install:
	@${FIND} -s ${STAGEDIR}${PREFIX}/lib/${PORTNAME} -type f \
		| ${SED} -e 's,^${STAGEDIR}${PREFIX}/,,' >> ${TMPPLIST}

.include <bsd.port.mk>
