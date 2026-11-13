# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Alpine and FreeBSD tools repositories of an air-gapped site (ROADMAP
25.9): written as abuild-sign and pkg repo write them, signed with the site's
RSA key -- both proven with real clients on 2026-11-13 (apk-tools 3.0.6 on
Alpine 3.23, pkg 2.8.4 on FreeBSD 14.4: indexes accepted, packages fetched,
another key refused).  These tests hold the formats to what those clients
accepted."""

# pylint: disable=protected-access

import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import zlib

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from backend.services import airgap_repoint_service as repoint
from backend.services import airgap_tools as tools
from backend.services import airgap_tools_formats as formats


@pytest.fixture(scope="module")
def site_key(tmp_path_factory):
    folder = tmp_path_factory.mktemp("site")
    key, public = formats.ensure_rsa_key(
        str(folder / "private"), str(folder / "public")
    )
    with open(public, "rb") as handle:
        return key, handle.read()


def _apk(folder, name="restate", version="3.2.1.6-r0", arch="x86_64"):
    pkginfo = (f"pkgname = {name}\npkgver = {version}\npkgdesc = test\narch = {arch}\n"
               "size = 100\ndepend = gzip\ndepend = gpgv\n").encode()  # fmt: skip
    sign = gzip.compress(formats._tar([(".SIGN.RSA.x.rsa.pub", b"sig")], cut=True))
    control = gzip.compress(formats._tar([(".PKGINFO", pkginfo)], cut=True))
    data = gzip.compress(formats._tar([("usr/bin/x", b"x")]))
    path = os.path.join(folder, f"{name}-{version}-alpine3.23-{arch}.apk")
    with open(path, "wb") as out:
        out.write(sign + control + data)
    return path, control


def test_the_apk_index_is_signed_as_apk_checks_it(tmp_path, site_key):
    key, public = site_key
    folder = tmp_path / "alpine"
    folder.mkdir()
    _path, control = _apk(str(folder))
    _apk(str(folder), "restate-proxy")
    assert formats.build_apk_repository(str(folder), key, public) is None
    # apk fetches <arch>/<name>-<version>.apk
    assert sorted(os.listdir(folder / "x86_64")) == [
        "APKINDEX.tar.gz", "restate-3.2.1.6-r0.apk", "restate-proxy-3.2.1.6-r0.apk"]  # fmt: skip
    data = (folder / "x86_64" / "APKINDEX.tar.gz").read_bytes()
    first = zlib.decompressobj(16 + zlib.MAX_WBITS)
    head = first.decompress(data)
    payload = first.unused_data
    sign = tarfile.open(fileobj=io.BytesIO(head + b"\0" * 1024)).getmembers()[0]
    assert sign.name == f".SIGN.RSA256.{formats.key_name(public)}.rsa.pub"
    assert any(head[1024:]) is False  # cut short of its end blocks, as abuild-tar --cut
    signature = (
        tarfile.open(fileobj=io.BytesIO(head + b"\0" * 1024)).extractfile(sign).read()
    )
    serialization.load_pem_public_key(public).verify(
        signature, payload, padding.PKCS1v15(), hashes.SHA256()
    )
    index = (
        tarfile.open(fileobj=io.BytesIO(gzip.decompress(payload)))
        .extractfile("APKINDEX")
        .read()
        .decode()
    )
    q1 = (
        "C:Q1" + __import__("base64").b64encode(hashlib.sha1(control).digest()).decode()
    )
    assert (
        q1 in index
        and "P:restate\nV:3.2.1.6-r0\nA:x86_64" in index
        and "D:gzip gpgv" in index
    )


def _freebsd_pkg(folder):
    if shutil.which("zstd") is None:
        pytest.skip("needs zstd")
    manifest = {"name": "restate", "origin": "sysutils/restate", "version": "3.2.1.6",
                "comment": "c", "maintainer": "m", "www": "w", "abi": "FreeBSD:14:amd64",
                "arch": "freebsd:14:x86:64", "prefix": "/usr/local", "flatsize": 10,
                "licenselogic": "single", "licenses": ["BSD2CLAUSE"], "desc": "d"}  # fmt: skip
    raw = formats._tar(
        [("+COMPACT_MANIFEST", json.dumps(manifest).encode()), ("+MANIFEST", b"{}")]
    )
    path = os.path.join(folder, "restate-3.2.1.6-freebsd-14.4-amd64.pkg")
    with open(path, "wb") as out:
        out.write(
            subprocess.run(
                ["zstd", "-q", "-c"], input=raw, capture_output=True, check=True
            ).stdout
        )
    return path


def test_the_pkg_catalog_is_signed_as_pkg_checks_it(tmp_path, site_key):
    key, public = site_key
    folder = tmp_path / "freebsd"
    folder.mkdir()
    path = _freebsd_pkg(str(folder))
    expected_sum = formats.pkg_sum(path)
    assert formats.build_pkg_repository(str(folder), key) is None
    assert (folder / "meta.conf").read_text() == formats.META
    with tarfile.open(folder / "packagesite.pkg") as tar:
        assert tar.getnames() == ["signature", "packagesite.yaml"]
        signature = tar.extractfile("signature").read()
        catalog = tar.extractfile("packagesite.yaml").read()
    assert signature.endswith(b"\0")  # NUL-terminated, as pkg writes it
    serialization.load_pem_public_key(public).verify(
        signature[:-1],
        hashlib.sha256(catalog).hexdigest().encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    entry = json.loads(catalog.splitlines()[0])
    assert (
        entry["sum"] == expected_sum
        and entry["path"] == "All/restate-3.2.1.6-freebsd-14.4-amd64.pkg"
    )
    assert list(entry)[:9] == ["name", "origin", "version", "comment", "maintainer", "www", "abi",
                               "arch", "prefix"]  # fmt: skip


def test_pkgs_sum_is_its_base32_of_blake2b(tmp_path):
    """The value pkg 2.8.4 wrote for restate 3.2.1.6's FreeBSD 14.4 package
    starts 2$34kfyzqb; the encoding takes each byte's bits from the low end."""
    path = tmp_path / "x"
    path.write_bytes(b"")
    digest = hashlib.blake2b(b"").digest()
    out, acc, bits = [], 0, 0
    for byte in digest:
        acc |= byte << bits
        bits += 8
        while bits >= 5:
            out.append(formats._PKG_B32[acc & 31])
            acc >>= 5
            bits -= 5
    out.append(formats._PKG_B32[acc & 31])
    assert (
        formats.pkg_sum(str(path)) == "2$" + "".join(out)
        and len(formats.pkg_sum(str(path))) == 105
    )


def test_alpine_and_freebsd_resolve_from_the_releases(monkeypatch):
    def assets(repo):
        names = ({"restate": ["restate-3.2-r0-alpine3.22-x86_64.apk", "restate-doc-3.2-r0-alpine3.22-x86_64.apk",
                              "restate-3.2-r0-alpine3.23-x86_64.apk", "restate-3.2-freebsd-14.4-amd64.pkg",
                              "restate-3.2-freebsd-14.5-amd64.pkg", "restate-3.2-freebsd-15.1-amd64.pkg"],
                  "sysmanage-agent": ["sysmanage-agent-3.13-alpine322.apk", "sysmanage-agent-3.13.pkg",
                                      "sysmanage-agent-3.13-macos.pkg"]})[repo.split("/")[1]]  # fmt: skip
        return {n: {"url": f"https://x/{n}", "sha256": "a" * 64} for n in names}

    monkeypatch.setattr(tools, "_github_assets", assets)
    assert {i["name"] for i in tools.resolve("alpine", "3.22")} == {
        "restate-3.2-r0-alpine3.22-x86_64.apk", "sysmanage-agent-3.13-alpine322.apk"}  # fmt: skip
    assert {i["name"] for i in tools.resolve("freebsd", "14")} == {
        "restate-3.2-freebsd-14.5-amd64.pkg", "sysmanage-agent-3.13.pkg"}  # fmt: skip


KEY = "-----BEGIN PUBLIC KEY-----\nx\n-----END PUBLIC KEY-----\n"


def test_alpine_hosts_get_both_repositories_and_the_named_key():
    _kind, plan = repoint.repoint_plan("alpine", "http://r/airgap-repo/alpine/3.22", "")
    url = "http://r/airgap-tools/alpine/3.22"
    plan = repoint._with_tools("apk", plan, url, KEY)
    files = {f["path"]: f["content"] for f in plan["files"]}
    assert (
        files["/etc/apk/repositories"]
        == "http://r/airgap-repo/alpine/3.22\n" + url + "\n"
    )
    assert files[f"/etc/apk/keys/{formats.key_name(KEY.encode())}.rsa.pub"] == KEY
    assert [f["path"] for f in plan["files"]].count("/etc/apk/repositories") == 1


def test_freebsd_hosts_check_the_catalog_with_the_site_key():
    _kind, plan = repoint.repoint_plan("freebsd", "http://r/airgap-repo/freebsd/14", "")
    plan = repoint._with_tools("pkg", plan, "http://r/airgap-tools/freebsd/14", KEY)
    files = {f["path"]: f["content"] for f in plan["files"]}
    conf = files["/usr/local/etc/pkg/repos/sysmanage-tools.conf"]
    assert 'signature_type: "pubkey"' in conf and repoint.TOOLS_PKG_KEY in conf
    assert files[repoint.TOOLS_PKG_KEY] == KEY
    assert "FreeBSD: { enabled: no }" in files["/usr/local/etc/pkg/repos/FreeBSD.conf"]
