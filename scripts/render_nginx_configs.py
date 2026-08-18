#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Render every platform's nginx config from one template.

    python3 scripts/render_nginx_configs.py            # write them
    python3 scripts/render_nginx_configs.py --check    # fail if any has drifted

WHY THIS EXISTS
---------------
There were eight nginx configs, differing in exactly two paths -- the frontend
root and the air-gap repository root -- and they had already diverged in a way
that mattered: the FreeBSD one terminated TLS on 443, while Ubuntu, CentOS,
openSUSE, Alpine, macOS and NetBSD all served the console and the API over
PLAINTEXT HTTP on port 3000.  Six platforms shipping an unencrypted management
console is not a difference anybody chose; it is what happens when the same file
is maintained in eight places.

That is the duplicated-table defect the Phase 19 roadmap calls out, and this is
the same mitigation used for ``agent_install.pxi``: one canonical source, a
generator, and a drift check wired into ``make lint`` so the copies cannot
quietly disagree again.

ONE PORT
--------
Every rendered config exposes 443 only (80 redirects to it), with the backend on
loopback 8080.  The firewall requirement becomes "inbound 443 on the server,
outbound 443 from each agent", which is what a customer can satisfy without
touching anything else.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import Dict

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "installer" / "nginx" / "sysmanage-nginx.conf.template"

# The ONLY per-platform differences.  Anything else belongs in the template --
# if a platform needs a genuinely different directive, add it here as a
# substitution rather than hand-editing the rendered file, or the drift check
# will (correctly) overwrite it.
#
# FreeBSD keeps %%PREFIX%% because the ports framework substitutes it at install
# time; it is not a placeholder this script resolves.
# Keys that describe the INSTALL rather than substituting into the config.
# Used to generate the post-install message, so the paths an operator is told to
# edit come from the same table that generated the file they are editing.
METADATA_KEYS = frozenset({"CONF_PATH", "RELOAD_CMD"})

PLATFORMS: Dict[str, Dict[str, str]] = {
    "alpine": {
        "RELOAD_CMD": "rc-service nginx reload",
        "CONF_PATH": "/etc/nginx/http.d/sysmanage-nginx.conf",
        "FRONTEND_ROOT": "/usr/share/sysmanage/frontend",
        "AIRGAP_ROOT": "/var/lib/sysmanage/airgap-repo/",
        "TLS_CERT": "/etc/sysmanage/tls/server.crt",
        "TLS_KEY": "/etc/sysmanage/tls/server.key",
    },
    "centos": {
        "RELOAD_CMD": "systemctl reload nginx",
        "CONF_PATH": "/etc/nginx/conf.d/sysmanage-nginx.conf",
        "FRONTEND_ROOT": "/opt/sysmanage/frontend/dist",
        "AIRGAP_ROOT": "/var/lib/sysmanage/airgap-repo/",
        "TLS_CERT": "/etc/sysmanage/tls/server.crt",
        "TLS_KEY": "/etc/sysmanage/tls/server.key",
    },
    "freebsd": {
        "RELOAD_CMD": "service nginx reload",
        "CONF_PATH": "%%PREFIX%%/etc/nginx/sysmanage-nginx.conf",
        "FRONTEND_ROOT": "%%PREFIX%%/www/sysmanage",
        "AIRGAP_ROOT": "/var/db/sysmanage/airgap-repo/",
        "TLS_CERT": "%%PREFIX%%/etc/sysmanage/tls/server.crt",
        "TLS_KEY": "%%PREFIX%%/etc/sysmanage/tls/server.key",
    },
    "macos": {
        # FRONTEND_ROOT tracks where the .pkg ACTUALLY puts the frontend --
        # /usr/local/lib/sysmanage/frontend/dist (Makefile: installer-macos
        # rsyncs frontend/dist there).  It said /opt/sysmanage/frontend/dist,
        # a Linux path that exists on no macOS install, so the console 404'd
        # even on Intel with nginx correctly installed.  postinstall.sh
        # rewrites the /usr/local prefix to $(brew --prefix) on Apple Silicon.
        "RELOAD_CMD": "nginx -s reload",
        "CONF_PATH": "/usr/local/etc/nginx/servers/sysmanage-nginx.conf",
        "FRONTEND_ROOT": "/usr/local/lib/sysmanage/frontend/dist",
        "AIRGAP_ROOT": "/var/lib/sysmanage/airgap-repo/",
        "TLS_CERT": "/usr/local/etc/sysmanage/tls/server.crt",
        "TLS_KEY": "/usr/local/etc/sysmanage/tls/server.key",
    },
    "netbsd": {
        "RELOAD_CMD": "/etc/rc.d/nginx reload",
        "CONF_PATH": "/usr/pkg/etc/nginx/conf.d/sysmanage-nginx.conf",
        "FRONTEND_ROOT": "/opt/sysmanage/frontend/dist",
        "AIRGAP_ROOT": "/var/lib/sysmanage/airgap-repo/",
        "TLS_CERT": "/usr/pkg/etc/sysmanage/tls/server.crt",
        "TLS_KEY": "/usr/pkg/etc/sysmanage/tls/server.key",
    },
    "openbsd": {
        "RELOAD_CMD": "rcctl reload nginx",
        "CONF_PATH": "/etc/nginx/conf.d/sysmanage-nginx.conf",
        "FRONTEND_ROOT": "/var/www/sysmanage",
        "AIRGAP_ROOT": "/var/db/sysmanage/airgap-repo/",
        "TLS_CERT": "/etc/sysmanage/tls/server.crt",
        "TLS_KEY": "/etc/sysmanage/tls/server.key",
    },
    "opensuse": {
        "RELOAD_CMD": "systemctl reload nginx",
        "CONF_PATH": "/etc/nginx/conf.d/sysmanage-nginx.conf",
        "FRONTEND_ROOT": "/opt/sysmanage/frontend/dist",
        "AIRGAP_ROOT": "/var/lib/sysmanage/airgap-repo/",
        "TLS_CERT": "/etc/sysmanage/tls/server.crt",
        "TLS_KEY": "/etc/sysmanage/tls/server.key",
    },
    "ubuntu": {
        "RELOAD_CMD": "systemctl reload nginx",
        "CONF_PATH": "/etc/nginx/sites-available/sysmanage-nginx.conf",
        "FRONTEND_ROOT": "/opt/sysmanage/frontend/dist",
        "AIRGAP_ROOT": "/var/lib/sysmanage/airgap-repo/",
        "TLS_CERT": "/etc/sysmanage/tls/server.crt",
        "TLS_KEY": "/etc/sysmanage/tls/server.key",
    },
    # Windows renders from the SAME template as everything else, deliberately.
    # It was the one platform with no nginx at all: the MSI laid down the built
    # frontend and then nothing served it, while install.ps1 told the operator
    # to open http://localhost:8080 -- which is the API.  So the console was
    # unreachable, with no TLS, no security headers and no /airgap-repo/ route.
    # Hand-writing a ninth config would have put Windows outside the drift gate
    # that exists precisely because eight hand-maintained copies diverged.
    #
    # FORWARD SLASHES: nginx on Windows takes "/"-separated paths even for
    # drive-letter roots ("C:/Program Files/..."), and a backslash would be read
    # as an escape.  Quoted because the default install path contains a space.
    "windows": {
        "RELOAD_CMD": "nssm restart SysManageNginx",
        "CONF_PATH": "C:/Program Files/SysManage Server/nginx/conf/sysmanage-nginx.conf",
        "FRONTEND_ROOT": '"C:/Program Files/SysManage Server/frontend"',
        "AIRGAP_ROOT": '"C:/ProgramData/SysManage/airgap-repo/"',
        "TLS_CERT": '"C:/ProgramData/SysManage/tls/server.crt"',
        "TLS_KEY": '"C:/ProgramData/SysManage/tls/server.key"',
    },
}

# The FreeBSD PORT ships its own copy with a provenance header prepended; it is
# rendered from the same template so the body cannot drift, but the header is
# preserved.
PORT_COPY = (
    REPO
    / "packaging"
    / "freebsd-ports"
    / "sysutils"
    / "sysmanage"
    / "files"
    / "sysmanage-nginx.conf.in"
)


def render(platform: str) -> str:
    """Substitute one platform's paths into the template."""
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in PLATFORMS[platform].items():
        if key in METADATA_KEYS:
            continue  # describes the install, not a placeholder in the config
        text = text.replace(f"@{key}@", value)
    leftovers = [line for line in text.splitlines() if "@" in line and "@@" not in line]
    unresolved = [line for line in leftovers if _has_placeholder(line)]
    if unresolved:
        raise SystemExit(
            f"ERROR: unresolved placeholder(s) rendering {platform}:\n  "
            + "\n  ".join(unresolved)
        )
    return text


def _has_placeholder(line: str) -> bool:
    """Is there an @NAME@ token left in this line?"""
    import re  # noqa: PLC0415

    return bool(re.search(r"@[A-Z_]+@", line))


TLS_MESSAGE = """=====================================================================
TLS CERTIFICATE - REQUIRED BEFORE THE SERVER WILL SERVE ANYTHING
=====================================================================
SysManage serves everything on port 443, and nginx will REFUSE TO START
until a certificate is in place.  That is deliberate: a management console
must not come up in cleartext because a certificate was missing, and a
certificate a package generated for you is one no agent would trust anyway
(agents verify by default).

Install your certificate and private key at:
  @TLS_CERT@
  @TLS_KEY@

Or point nginx somewhere else by editing these two lines in:
  @CONF_PATH@

  ssl_certificate     @TLS_CERT@;
  ssl_certificate_key @TLS_KEY@;

Getting a certificate:
  certbot certonly --standalone -d your-server.example.com
  (then point the two lines above at /etc/letsencrypt/live/<name>/
   fullchain.pem and privkey.pem)

Check it before starting:
  nginx -t

Agents then need outbound 443 to this host and nothing else.  If you are
only developing, set `dev_mode: true` in the server configuration instead:
that skips nginx entirely and serves the UI and API directly.
"""


def tls_message(platform: str) -> str:
    """The post-install TLS instructions for one platform.

    Rendered from the SAME table that generates the nginx config, so the paths
    an operator is told to edit cannot drift from the file they are editing --
    which is precisely what "documented separately" always becomes.
    """
    text = TLS_MESSAGE
    for key, value in PLATFORMS[platform].items():
        text = text.replace(f"@{key}@", value)
    return text


POST_INSTALL_SCRIPTS = {
    "alpine": REPO / "installer" / "alpine" / "sysmanage.post-install",
    "centos": REPO / "installer" / "centos" / "sysmanage.spec",
    "macos": REPO / "installer" / "macos" / "postinstall.sh",
    "netbsd": REPO / "installer" / "netbsd" / "+INSTALL",
    "opensuse": REPO / "installer" / "opensuse" / "sysmanage.spec",
    "ubuntu": REPO / "installer" / "ubuntu" / "debian" / "postinst",
}

BEGIN_MARKER = "# BEGIN GENERATED TLS MESSAGE - edit scripts/render_nginx_configs.py"
END_MARKER = "# END GENERATED TLS MESSAGE"


def shell_block(platform: str, indent: str = "\t") -> str:
    """The TLS message as shell ``echo`` lines, ready to inject.

    Single-quoted so nothing in the text is interpreted -- the message contains
    backticks around ``dev_mode: true``, and inside double quotes a shell would
    try to run that as a command substitution.
    """
    lines = [f"{indent}{BEGIN_MARKER}"]
    for line in tls_message(platform).rstrip("\n").split("\n"):
        if "'" in line:
            raise SystemExit(
                "ERROR: the TLS message must not contain a single quote "
                f"(would break shell quoting): {line!r}"
            )
        lines.append(f"{indent}echo '{line}'" if line else f"{indent}echo ''")
    lines.append(f"{indent}{END_MARKER}")
    return "\n".join(lines) + "\n"


PREFLIGHT = """if [ ! -f '@TLS_CERT@' ] || [ ! -f '@TLS_KEY@' ]; then
    echo ''
    echo '[!] TLS certificate NOT FOUND - nginx will refuse to start.'
    echo '    expected: @TLS_CERT@'
    echo '              @TLS_KEY@'
    echo '    Install them (see the TLS section above), then run:'
    echo '        nginx -t && @RELOAD_CMD@'
    echo '    nginx was left alone, so anything already serving keeps serving.'
elif ! command -v nginx >/dev/null 2>&1; then
    echo '[!] nginx is not installed; SysManage serves the console through it.'
elif nginx -t >/dev/null 2>&1; then
    @RELOAD_CMD@ >/dev/null 2>&1 || true
    echo '[OK] nginx configuration is valid; reloaded.'
else
    echo '[!] nginx REJECTED the configuration:'
    nginx -t 2>&1 | sed 's/^/      /'
fi"""

PREFLIGHT_BEGIN = (
    "# BEGIN GENERATED TLS PREFLIGHT - edit scripts/render_nginx_configs.py"
)
PREFLIGHT_END = "# END GENERATED TLS PREFLIGHT"


def preflight_block(platform: str, indent: str = "") -> str:
    """Shell that checks for the certificate BEFORE touching nginx.

    Without this, a fresh install runs ``nginx -t``, watches it fail because no
    certificate exists yet, and prints "nginx configuration may need manual
    review" -- which describes neither what is wrong nor what to do.  The
    configuration is fine; the certificate is missing, and that is a different
    problem with a different fix.

    It also declines to reload when the certificate is absent.  Reloading would
    take down a site that is currently serving perfectly well on the old
    configuration, in order to apply one nginx has already refused.
    """
    text = PREFLIGHT
    for key, value in PLATFORMS[platform].items():
        text = text.replace(f"@{key}@", value)
    lines = [f"{indent}{PREFLIGHT_BEGIN}"]
    lines += [f"{indent}{line}" if line else "" for line in text.split("\n")]
    lines.append(f"{indent}{PREFLIGHT_END}")
    return "\n".join(lines) + "\n"


def inject_preflight(platform: str, check: bool) -> str:
    """Refresh the generated preflight inside a post-install script."""
    script = POST_INSTALL_SCRIPTS.get(platform)
    if script is None or not script.is_file():
        return ""
    text = script.read_text(encoding="utf-8")
    if PREFLIGHT_BEGIN not in text:
        return ""

    start = text.index(PREFLIGHT_BEGIN)
    line_start = text.rfind("\n", 0, start) + 1
    indent = text[line_start:start]
    end = text.index(PREFLIGHT_END, start) + len(PREFLIGHT_END)
    end_of_line = text.find("\n", end)
    end_of_line = len(text) if end_of_line == -1 else end_of_line + 1

    block = preflight_block(platform, indent)
    updated = text[:line_start] + block + text[end_of_line:]
    if updated == text:
        return ""
    if check:
        return f"{script.relative_to(REPO)}: TLS preflight is stale"
    script.write_text(updated, encoding="utf-8")
    return ""


def inject_message(platform: str, check: bool) -> str:
    """Refresh the generated block inside a post-install script.

    Returns a problem description, or "" when the file is already correct or has
    no markers (a platform that has not opted in yet).
    """
    script = POST_INSTALL_SCRIPTS.get(platform)
    if script is None or not script.is_file():
        return ""
    text = script.read_text(encoding="utf-8")
    if BEGIN_MARKER not in text:
        return ""

    start = text.index(BEGIN_MARKER)
    line_start = text.rfind("\n", 0, start) + 1
    indent = text[line_start:start]
    end = text.index(END_MARKER, start) + len(END_MARKER)
    end_of_line = text.find("\n", end)
    end_of_line = len(text) if end_of_line == -1 else end_of_line + 1

    block = shell_block(platform, indent)
    updated = text[:line_start] + block + text[end_of_line:]
    if updated == text:
        return ""
    if check:
        return f"{script.relative_to(REPO)}: TLS message is stale"
    script.write_text(updated, encoding="utf-8")
    return ""


def message_target_for(platform: str) -> Path:
    return REPO / "installer" / platform / "tls-setup-message.txt"


def target_for(platform: str) -> Path:
    return REPO / "installer" / platform / "sysmanage-nginx.conf"


# The FreeBSD port copy carries this provenance note above the shared body.
# Spelled out rather than sniffed from the existing file: the first attempt
# detected "leading comment lines", which swallowed the template's own opening
# comments too because nothing blank separated them -- and the result was not
# idempotent, so --check failed immediately after a write.
PORT_HEADER = """# Installed by sysutils/sysmanage as %%PREFIX%%/etc/nginx/
# sysmanage-nginx.conf.sample.
#
# This file lives in the PORT, not in the release tarball.  The tarball's
# installer/freebsd/sysmanage-nginx.conf is whatever shipped with the tag,
# so a port that installed it could not fix its own nginx configuration
# without cutting a new release -- on 2026-08-11 the port duly installed a
# tagged copy that still served plain HTTP on port 3000 from a Linux path,
# while the corrected TLS version sat unused in the source tree.

"""


# The Windows nginx version+hash is pinned in TWO files: the installer that
# verifies the archive, and the air-gap bundler that stages it.  They must
# agree -- a bundled archive whose hash the installer does not expect is
# refused on a disconnected network, where nobody can go and check upstream.
# Same duplicated-constant hazard the config drift check exists for, so it is
# checked in the same place.
WIN_INSTALLER = REPO / "installer" / "windows" / "install-nginx.ps1"
WIN_BUNDLER = REPO / "scripts" / "buildAirGapBundle.sh"


def check_windows_nginx_pin() -> list:
    """Problems with the Windows nginx version/hash pin, or []."""
    problems = []
    if not (WIN_INSTALLER.is_file() and WIN_BUNDLER.is_file()):
        return ["windows nginx pin: installer or bundler missing"]
    inst = WIN_INSTALLER.read_text(encoding="utf-8")
    bund = WIN_BUNDLER.read_text(encoding="utf-8")

    def grab(text, pattern):
        found = re.search(pattern, text)
        return found.group(1) if found else None

    iv = grab(inst, r'\$NginxVersion\s*=\s*"([0-9.]+)"')
    ih = grab(inst, r'\$NginxSha256\s*=\s*"([a-f0-9]{64})"')
    bv = grab(bund, r'NGINX_WIN_VERSION="([0-9.]+)"')
    bh = grab(bund, r'NGINX_WIN_SHA256="([a-f0-9]{64})"')

    for name, value in (
        ("installer version", iv),
        ("installer sha256", ih),
        ("bundler version", bv),
        ("bundler sha256", bh),
    ):
        if value is None:
            problems.append(f"windows nginx pin: could not find {name}")
    if problems:
        return problems
    if iv != bv:
        problems.append(
            f"windows nginx VERSION differs: installer {iv} vs bundler {bv}"
        )
    if ih != bh:
        problems.append(
            f"windows nginx SHA256 differs: installer {ih[:16]}... vs "
            f"bundler {bh[:16]}..."
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if any rendered file differs",
    )
    args = parser.parse_args()

    if not TEMPLATE.is_file():
        sys.exit(f"ERROR: template not found at {TEMPLATE}")

    problems = []
    written = []

    # Checked in both modes: a drifted pin is wrong whether or not anything
    # else needs rewriting, and this script cannot repair it (the correct hash
    # depends on which nginx you intend to ship).
    problems.extend(check_windows_nginx_pin())

    for platform in sorted(PLATFORMS):
        target = target_for(platform)
        rendered = render(platform)
        if args.check:
            if not target.is_file():
                problems.append(f"{target.relative_to(REPO)}: missing")
                continue
            current = target.read_text(encoding="utf-8")
            if current != rendered:
                diff = "\n".join(
                    difflib.unified_diff(
                        current.splitlines(),
                        rendered.splitlines(),
                        fromfile=f"{target.relative_to(REPO)} (on disk)",
                        tofile="rendered from template",
                        lineterm="",
                        n=1,
                    )
                )
                problems.append(f"{target.relative_to(REPO)} has drifted:\n{diff}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
            written.append(str(target.relative_to(REPO)))

        message_target = message_target_for(platform)
        message = tls_message(platform)
        if args.check:
            if not message_target.is_file():
                problems.append(f"{message_target.relative_to(REPO)}: missing")
            elif message_target.read_text(encoding="utf-8") != message:
                problems.append(
                    f"{message_target.relative_to(REPO)} has drifted from the template"
                )
        else:
            message_target.write_text(message, encoding="utf-8")
            written.append(str(message_target.relative_to(REPO)))

        for injector in (inject_message, inject_preflight):
            problem = injector(platform, args.check)
            if problem:
                problems.append(problem)

    # The FreeBSD port copy: same body, its own header.
    if PORT_COPY.is_file():
        body = render("freebsd")
        expected = PORT_HEADER + body
        if args.check:
            if PORT_COPY.read_text(encoding="utf-8") != expected:
                problems.append(
                    f"{PORT_COPY.relative_to(REPO)} has drifted from the template"
                )
        else:
            PORT_COPY.write_text(expected, encoding="utf-8")
            written.append(str(PORT_COPY.relative_to(REPO)))

    if args.check:
        if problems:
            print("nginx configs are out of sync with the template:\n")
            for problem in problems:
                print(f"  {problem}\n")
            print("Run: python3 scripts/render_nginx_configs.py")
            return 1
        print(f"[OK] all {len(PLATFORMS)} nginx configs match the template")
        return 0

    for path in written:
        print(f"  wrote {path}")
    print(f"[OK] rendered {len(written)} nginx configs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
