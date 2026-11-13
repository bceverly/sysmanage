# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The SysManage tools repository of an air-gapped site (ROADMAP 25.9).

An air-gapped site's hosts reach no PPA, COPR or GitHub, so "Equip for
backup" there installs restate from the site's own repositories -- which
held only the operating systems' mirrors.  This module carries the agent,
restate and restate-proxy across the gap and serves them as a separate,
signed repository beside each mirror:

* **Collector (internet side).**  :func:`resolve` names, for each target
  distribution, the exact packages and their SHA-256 -- from the Launchpad
  PPAs' ``Packages`` indexes (Ubuntu), Fedora COPR's repodata, or the GitHub
  releases' asset digests -- and :func:`fetch_plan` has the mirror host's
  agent download them into the staging tree (``sysmanage-tools/<distro>/
  <version>/``), each checked with ``sha256sum``.  The list goes into the
  media's signed manifest (``tools``), so a file swapped on the way is
  refused on the other side.  A tool that cannot be fetched never fails the
  operating-system mirror run.

* **Repository (air-gapped side).**  After an ingest, :func:`build` checks
  every copied file against the signed manifest, keeps only those that
  match, and builds a repository of them under ``airgap-tools/`` -- apt for
  Ubuntu (``Packages``, ``Release``, a clear-signed ``InRelease``), rpm-md
  for Fedora, EL and openSUSE (``createrepo_c``, a detached
  ``repomd.xml.asc``) -- signed with the site's own OpenPGP key.  The key is
  made on the repository server the first time and never leaves it; its
  public half is published beside the repositories (``sysmanage-tools.asc``)
  for :mod:`airgap_repoint_service` to install on the hosts.  The upstream
  mirrors are not touched: their own signed indexes stay as they came.

Alpine and FreeBSD need keys of another kind (an RSA ``abuild`` key, a
``pkg repo`` signing key) and are not served yet; their hosts install from
the agent bundle.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import shutil
import subprocess  # nosec B404
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from defusedxml import ElementTree

logger = logging.getLogger(__name__)

TOOLS_DIR = "sysmanage-tools"
KEY_FILE = "sysmanage-tools.asc"
KEY_UID = "SysManage tools repository <tools@sysmanage.invalid>"
FETCH_LIMIT = 64 << 20
INDEX_LIMIT = 32 << 20
GITHUB_API = "https://api.github.com/repos"
PPA_BASE = "https://ppa.launchpadcontent.net/bceverly"
COPR_BASE = "https://download.copr.fedorainfracloud.org/results/bceverly"
_CACHE_SECONDS = 600
_cache: Dict[str, Tuple[float, Any]] = {}

UBUNTU_CODENAMES = {
    "22.04": "jammy",
    "24.04": "noble",
    "25.10": "questing",
    "26.04": "resolute",
}
DEB_ARCHES = ("amd64", "arm64")
RPM_ARCHES = ("x86_64", "aarch64")
_EL = ("rhel", "rocky", "alma", "almalinux", "centos")


def family(distro: str) -> Optional[str]:
    """``apt``, ``rpm``, ``apk`` or ``pkg`` where a tools repository is
    built, else None."""
    distro = (distro or "").lower()
    if distro.startswith("ubuntu"):
        return "apt"
    if distro.startswith("alpine"):
        return "apk"
    if distro.startswith("freebsd"):
        return "pkg"
    if distro.startswith(("fedora", "opensuse", "sles")) or distro.startswith(_EL):
        return "rpm"
    return None


# --- the internet side ------------------------------------------------------


def _get(url: str, limit: int = INDEX_LIMIT) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"not https: {url}")
    request = urllib.request.Request(
        url, headers={"User-Agent": "sysmanage-airgap-collector"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{url}: larger than {limit} bytes")
    return data


def _cached(key: str, load):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_SECONDS:
        return hit[1]
    value = load()
    _cache[key] = (time.monotonic(), value)
    return value


def _github_assets(repo: str) -> Dict[str, Dict[str, str]]:
    """``{name: {url, sha256}}`` of a project's latest release, by GitHub's
    own asset digests."""

    def load():
        release = json.loads(_get(f"{GITHUB_API}/{repo}/releases/latest"))
        found = {}
        for asset in release.get("assets") or []:
            digest = asset.get("digest") or ""
            if digest.startswith("sha256:") and asset.get("browser_download_url"):
                found[asset["name"]] = {
                    "url": asset["browser_download_url"],
                    "sha256": digest.split(":", 1)[1],
                }
        return found

    return _cached(f"gh:{repo}", load)


def _ppa_packages(ppa: str, codename: str, arch: str) -> Dict[str, Dict[str, str]]:
    """``{package: {url, sha256}}`` from a PPA's ``Packages`` index: the last
    stanza of each name, which Launchpad lists newest last."""

    def load():
        base = f"{PPA_BASE}/{ppa}/ubuntu"
        text = gzip.decompress(
            _get(f"{base}/dists/{codename}/main/binary-{arch}/Packages.gz")
        ).decode("utf-8", "replace")
        found = {}
        for stanza in text.split("\n\n"):
            fields = {}
            for line in stanza.splitlines():
                if ": " in line and not line.startswith(" "):
                    key, value = line.split(": ", 1)
                    fields[key] = value.strip()
            if (
                fields.get("Package")
                and fields.get("Filename")
                and fields.get("SHA256")
            ):
                found[fields["Package"]] = {
                    "url": f"{base}/{fields['Filename']}",
                    "sha256": fields["SHA256"],
                }
        return found

    return _cached(f"ppa:{ppa}:{codename}:{arch}", load)


_RPM_NS = {"repo": "http://linux.duke.edu/metadata/repo",
           "common": "http://linux.duke.edu/metadata/common"}  # fmt: skip


def _copr_packages(project: str, chroot: str) -> Dict[str, Dict[str, str]]:
    """``{package: {url, sha256}}`` from a COPR chroot's repodata (its
    newest build of each name)."""

    def load():
        base = f"{COPR_BASE}/{project}/{chroot}"
        repomd = ElementTree.fromstring(_get(f"{base}/repodata/repomd.xml"))
        href = None
        for data in repomd.findall("repo:data", _RPM_NS):
            if data.get("type") == "primary":
                location = data.find("repo:location", _RPM_NS)
                href = location.get("href") if location is not None else None
        if not href:
            return {}
        primary = ElementTree.fromstring(gzip.decompress(_get(f"{base}/{href}")))
        found = {}
        for package in primary.findall("common:package", _RPM_NS):
            name = package.findtext("common:name", default="", namespaces=_RPM_NS)
            if package.findtext("common:arch", default="", namespaces=_RPM_NS) == "src":
                continue
            checksum = package.find("common:checksum", _RPM_NS)
            location = package.find("common:location", _RPM_NS)
            if not name or checksum is None or location is None:
                continue
            if checksum.get("type") != "sha256":
                continue
            found[name] = {
                "url": f"{base}/{location.get('href')}",
                "sha256": checksum.text,
            }
        return found

    return _cached(f"copr:{project}:{chroot}", load)


def _pick(
    assets: Dict[str, Dict[str, str]], *, starts: str, ends: str
) -> List[Dict[str, str]]:
    return [
        {"name": name, **info}
        for name, info in sorted(assets.items())
        if name.startswith(starts) and name.endswith(ends)
    ]


def _ubuntu(version: str) -> List[Dict[str, str]]:
    codename = UBUNTU_CODENAMES.get(version, version)
    items = []
    for arch in DEB_ARCHES:
        for ppa, names in (("restate", ("restate", "restate-proxy")),
                           ("sysmanage-agent", ("sysmanage-agent",))):  # fmt: skip
            found = _ppa_packages(ppa, codename, arch)
            for name in names:
                if name in found:
                    url = found[name]["url"]
                    items.append({"name": url.rsplit("/", 1)[1], **found[name]})
    return items


def _agent_rpm(arch: str, suffix: str = "-1") -> List[Dict[str, str]]:
    assets = _github_assets("bceverly/sysmanage-agent")
    return _pick(assets, starts="sysmanage-agent-", ends=f"{suffix}.{arch}.rpm")


def _rpm_family(distro: str, version: str) -> List[Dict[str, str]]:
    distro = distro.lower()
    restate = _github_assets("bceverly/restate")
    items: List[Dict[str, str]] = []
    if distro.startswith("opensuse") or distro.startswith("sles"):
        items += [
            i
            for i in _pick(restate, starts="restate", ends=".rpm")
            if ".opensuseleap" in i["name"]
        ]
        items += _agent_rpm("x86_64", "-0.opensuse-leap")
        return items
    for arch in RPM_ARCHES:
        if distro.startswith("fedora"):
            found = _copr_packages("restate", f"fedora-{version}-{arch}")
            for name in ("restate", "restate-proxy"):
                if name in found:
                    url = found[name]["url"]
                    items.append({"name": url.rsplit("/", 1)[1], **found[name]})
        else:  # EL
            major = version.split(".")[0]
            items += _pick(restate, starts="restate", ends=f".el{major}.{arch}.rpm")
        items += _agent_rpm(arch)
    return items


def _alpine(version: str) -> List[Dict[str, str]]:
    """restate's packages for this Alpine release (both processors), and the
    agent's (noarch, one per release: ``alpine322`` for 3.22)."""
    restate = _github_assets("bceverly/restate")
    items = [
        {"name": name, **info}
        for name, info in sorted(restate.items())
        if name.startswith(("restate-", "restate-proxy-"))
        and not name.startswith("restate-doc-")
        and f"-r0-alpine{version}-" in name
        and name.endswith(".apk")
    ]
    agent = _github_assets("bceverly/sysmanage-agent")
    items += _pick(
        agent, starts="sysmanage-agent-", ends=f"-alpine{version.replace('.', '')}.apk"
    )
    return items


def _freebsd(version: str) -> List[Dict[str, str]]:
    """restate's packages for the newest point release of this FreeBSD major
    (all of a major share pkg's ABI), and the agent's FreeBSD package."""
    major = version.split(".")[0]
    restate = _github_assets("bceverly/restate")
    marker = f"-freebsd-{major}."
    releases = sorted(
        {
            name.split(marker, 1)[1].split("-", 1)[0]
            for name in restate
            if marker in name
        },
        key=lambda r: [int(p) for p in r.split(".") if p.isdigit()],
    )
    items: List[Dict[str, str]] = []
    if releases:
        tail = f"-freebsd-{major}.{releases[-1]}-"
        items = [{"name": n, **i} for n, i in sorted(restate.items())
                 if tail in n and n.endswith(".pkg")]  # fmt: skip
    agent = _github_assets("bceverly/sysmanage-agent")
    # The FreeBSD package is the bare one (macOS's is ``-macos.pkg``).
    items += [{"name": n, **i} for n, i in agent.items()
              if n.startswith("sysmanage-agent-") and n.endswith(".pkg")
              and n.count("-") == 2]  # fmt: skip
    return items


def resolve(distro: str, version: str) -> List[Dict[str, str]]:
    """``[{name, url, sha256}]`` for this target's tools; empty where none
    are served or the sources cannot be read (logged, never raised)."""
    kind = family(distro)
    try:
        if kind == "apt":
            return _ubuntu(str(version))
        if kind == "rpm":
            return _rpm_family(distro, str(version))
        if kind == "apk":
            return _alpine(str(version))
        if kind == "pkg":
            return _freebsd(str(version))
    except Exception as error:  # pylint: disable=broad-exception-caught
        logger.warning(
            "SysManage tools for %s %s could not be resolved: %s",
            distro,
            version,
            error,
        )
    return []


def target_dir(distro: str, version: str) -> str:
    return f"{TOOLS_DIR}/{distro}/{version}"


def fetch_plan(staging_dir: str, tools: List[Dict[str, Any]]) -> Dict[str, List]:
    """``{files, commands}`` the mirror host's agent appends to a collection
    plan: each package downloaded with ``sudo curl`` and checked with
    ``sudo sha256sum -c``.  Every step ignores errors: a missing tool must
    never fail the operating-system mirror run -- the repository side keeps
    only what matches the signed manifest."""
    files, commands = [], []
    for target in tools:
        folder = f"{staging_dir}/{target_dir(target['distro'], target['version'])}"
        items = target.get("items") or []
        if not items:
            continue
        commands.append(
            _cmd(["sudo", "mkdir", "-p", folder], 60, f"tools folder {folder}")
        )
        for item in items:
            commands.append(_cmd(
                ["sudo", "curl", "-fsSL", "--max-time", "1800", "-o", f"{folder}/{item['name']}", item["url"]],
                1900, f"fetch {item['name']}",
            ))  # fmt: skip
        sums = "".join(f"{i['sha256']}  {i['name']}\n" for i in items)
        files.append({"path": f"{folder}/SHA256SUMS", "content": sums, "permissions": "0644",
                      "owner_uid": 0, "owner_gid": 0})  # fmt: skip
        commands.append(_cmd(["sudo", "sha256sum", "-c", "--quiet", f"{folder}/SHA256SUMS"], 600,
                             f"check the tools for {target['distro']} {target['version']}"))  # fmt: skip
    return {"files": files, "commands": commands}


def _cmd(argv, timeout, description):
    return {
        "argv": argv,
        "timeout": timeout,
        "ignore_errors": True,
        "description": description,
    }


def manifest_entries(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What the signed manifest carries: per target, each file's name and
    SHA-256 (never a URL: the other side has no use for one)."""
    return [
        {"distro": t["distro"], "version": t["version"],
         "files": [{"name": i["name"], "sha256": i["sha256"]} for i in t.get("items") or []]}
        for t in tools if t.get("items")
    ]  # fmt: skip


# --- the air-gapped side ----------------------------------------------------


def tools_root(repo_root: str) -> str:
    """Beside the mirror root (which each ingest's rsync --delete rewrites)."""
    return os.path.join(os.path.dirname(repo_root.rstrip("/")), "airgap-tools")


def _gnupg_home(root: str) -> str:
    return os.path.join(os.path.dirname(root), "airgap", "tools-gnupg")


def _run(argv: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None,
         stdout=None) -> Tuple[int, str]:  # fmt: skip
    try:
        done = subprocess.run(  # nosec B603
            argv, env=env, cwd=cwd, stdout=stdout or subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=600, check=False,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, str(error)
    return done.returncode, (done.stderr or b"").decode("utf-8", "replace")


def ensure_key(root: str) -> Optional[str]:
    """The site's tools-repository key: made here the first time (RSA 3072,
    no passphrase, its home 0700 and the server's alone), its public half
    exported to ``<root>/sysmanage-tools.asc``.  Returns the public key's
    path, or None when gpg is missing or fails."""
    if shutil.which("gpg") is None:
        logger.warning(
            "SysManage tools repository: gpg is not installed; nothing is signed"
        )
        return None
    home = _gnupg_home(root)
    os.makedirs(home, mode=0o700, exist_ok=True)
    env = {**os.environ, "GNUPGHOME": home}
    code, _err = _run(["gpg", "--batch", "--list-secret-keys", KEY_UID], env=env)
    if code != 0:
        code, err = _run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key", KEY_UID,
                          "rsa3072", "sign", "never"], env=env)  # fmt: skip
        if code != 0:
            logger.error(
                "SysManage tools repository: the key could not be made: %s", err.strip()
            )
            return None
    os.makedirs(root, exist_ok=True)
    public = os.path.join(root, KEY_FILE)
    with open(public, "wb") as out:
        code, err = _run(
            ["gpg", "--batch", "--armor", "--export", KEY_UID], env=env, stdout=out
        )
    return public if code == 0 else None


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _verified_copy(source: str, dest: str, files: List[Dict[str, str]]) -> List[str]:
    """Copy the files whose SHA-256 matches the signed manifest; the rest
    are left out and logged."""
    os.makedirs(dest, exist_ok=True)
    kept = []
    for entry in files:
        name = os.path.basename(str(entry.get("name") or ""))
        path = os.path.join(source, name)
        if not name or not os.path.isfile(path):
            continue
        if _sha256(path) != entry.get("sha256"):
            logger.error(
                "SysManage tools: %s does not match the signed manifest; left out", path
            )
            continue
        shutil.copyfile(path, os.path.join(dest, name))
        kept.append(name)
    return kept


def _apt_index(folder: str, env: Dict[str, str]) -> Optional[str]:
    if shutil.which("apt-ftparchive") is None:
        return "apt-ftparchive is not installed (apt-utils)"
    with open(os.path.join(folder, "Packages"), "wb") as out:
        code, err = _run(["apt-ftparchive", "packages", "."], cwd=folder, stdout=out)
    if code:
        return err
    with open(os.path.join(folder, "Packages"), "rb") as src, gzip.open(
        os.path.join(folder, "Packages.gz"), "wb"
    ) as gz:
        shutil.copyfileobj(src, gz)
    with open(os.path.join(folder, "Release.tmp"), "wb") as out:
        code, err = _run(["apt-ftparchive", "-o", "APT::FTPArchive::Release::Origin=SysManage",
                          "release", "."], cwd=folder, stdout=out)  # fmt: skip
    if code:
        return err
    os.replace(os.path.join(folder, "Release.tmp"), os.path.join(folder, "Release"))
    code, err = _run(["gpg", "--batch", "--yes", "--local-user", KEY_UID, "--clearsign",
                      "-o", "InRelease", "Release"], env=env, cwd=folder)  # fmt: skip
    return err if code else None


def _rpm_index(folder: str, env: Dict[str, str]) -> Optional[str]:
    if shutil.which("createrepo_c") is None:
        return "createrepo_c is not installed"
    code, err = _run(["createrepo_c", "--update", "."], cwd=folder)
    if code:
        return err
    code, err = _run(["gpg", "--batch", "--yes", "--local-user", KEY_UID, "--armor",
                      "--detach-sign", "repodata/repomd.xml"], env=env, cwd=folder)  # fmt: skip
    return err if code else None


def _index(kind: str, folder: str, env: Dict[str, str], root: str) -> Optional[str]:
    """The signed index of one tools repository: OpenPGP for apt and rpm-md,
    the site's RSA key for apk and pkg (services/airgap_tools_formats.py)."""
    if kind == "apt":
        return _apt_index(folder, env)
    if kind == "rpm":
        return _rpm_index(folder, env)
    # pylint: disable-next=import-outside-toplevel
    from backend.services import airgap_tools_formats as formats  # noqa: PLC0415

    key, public = formats.ensure_rsa_key(_gnupg_home(root), root)
    if kind == "apk":
        with open(public, "rb") as handle:
            return formats.build_apk_repository(folder, key, handle.read())
    return formats.build_pkg_repository(folder, key)


def build(repo_root: str, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build and sign a tools repository per target the signed manifest
    lists (``tools``).  ``[{distro, version, kept, error}]``."""
    entries = manifest.get("tools") if isinstance(manifest, dict) else None
    if not isinstance(entries, list) or not entries:
        return []
    root = tools_root(repo_root)
    public = ensure_key(root)
    env = {**os.environ, "GNUPGHOME": _gnupg_home(root)}
    results = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        distro, version = str(entry.get("distro") or ""), str(
            entry.get("version") or ""
        )
        kind = family(distro)
        if (
            not kind
            or not distro
            or not version
            or "/" in distro + version
            or ".." in distro + version
        ):
            continue
        source = os.path.join(repo_root, target_dir(distro, version))
        if not os.path.isdir(source):
            # Not on this disc (a multi-disc set carries the tools on disc 1
            # only): what an earlier disc built stays.
            continue
        dest = os.path.join(root, distro, version)
        shutil.rmtree(dest, ignore_errors=True)
        kept = _verified_copy(source, dest,
                              entry.get("files") or [])  # fmt: skip
        error = None
        if not kept:
            error = "no package matched the signed manifest"
        elif public is None and kind in ("apt", "rpm"):
            error = "no signing key (gpg missing)"
        else:
            error = _index(kind, dest, env, root)
        if error:
            shutil.rmtree(dest, ignore_errors=True)
            logger.error(
                "SysManage tools repository for %s %s not built: %s",
                distro,
                version,
                error,
            )
        else:
            logger.info("SysManage tools repository for %s %s: %d package(s), signed",
                        distro, version, len(kept))  # fmt: skip
        results.append(
            {"distro": distro, "version": version, "kept": kept, "error": error}
        )
    return results


def served(repo_root: str, distro: str, version: str) -> bool:
    """A signed tools repository exists for this target."""
    folder = os.path.join(tools_root(repo_root), distro, version)
    kind = family(distro)
    markers = {
        "apt": ["InRelease"],
        "rpm": [os.path.join("repodata", "repomd.xml.asc")],
        "apk": [os.path.join(a, "APKINDEX.tar.gz") for a in ("x86_64", "aarch64")],
        "pkg": ["packagesite.pkg"],
    }.get(kind, [])
    return any(os.path.isfile(os.path.join(folder, m)) for m in markers)


def public_key(repo_root: str, kind: str = "apt") -> Optional[str]:
    """The site's published key: OpenPGP for apt and rpm-md, RSA (PEM) for
    apk and pkg."""
    # pylint: disable-next=import-outside-toplevel
    from backend.services.airgap_tools_formats import RSA_PUB  # noqa: PLC0415

    name = RSA_PUB if kind in ("apk", "pkg") else KEY_FILE
    path = os.path.join(tools_root(repo_root), name)
    try:
        with open(path, encoding="ascii") as handle:
            return handle.read()
    except OSError:
        return None
