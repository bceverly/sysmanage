# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Alpine and FreeBSD repositories for the SysManage tools of an air-gapped
site (services/airgap_tools.py, ROADMAP 25.9).

Neither takes an OpenPGP key: Alpine's ``apk`` checks an RSA signature on its
index, FreeBSD's ``pkg`` an RSA signature on its catalog.  The repository
server is usually Linux, with neither ``abuild-sign`` nor ``pkg repo``, so both
are written here, byte for byte as those tools write them (checked against
Alpine's own signed index and against ``pkg repo`` on FreeBSD 14.4, and the
results proven with real ``apk`` and ``pkg`` clients), signed with the site's
own RSA key -- made on the repository server the first time, its private half
the server's alone.

* **Alpine** (``<url>/<arch>/APKINDEX.tar.gz``): two gzip streams -- a tar,
  cut short of its end blocks, holding ``.SIGN.RSA256.<key name>`` (RSA
  PKCS#1 v1.5 over the SHA-256 of the second stream), then the index tar
  (``DESCRIPTION``, ``APKINDEX``).  Each entry comes from the package's own
  ``.PKGINFO``; ``C:Q1...`` is the SHA-1 of its control stream.
* **FreeBSD** (``meta.conf``, ``packagesite.pkg``, ``data.pkg``, ``All/``):
  each archive holds the catalog and ``signature`` -- RSA PKCS#1 v1.5 with
  SHA-256 over the *hex* SHA-256 of the catalog, NUL-terminated, as pkg
  signs.  Entries come from each package's ``+COMPACT_MANIFEST``; ``sum`` is
  ``2$`` and pkg's base32 of the file's BLAKE2b-512.  The archives are gzip
  (pkg reads them by content, whatever ``packing_format`` names); reading the
  packages, which pkg compresses with zstd, needs ``zstd``.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess  # nosec B404
import tarfile
import time
import zlib
from typing import Dict, List, Optional, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

RSA_KEY = "tools-rsa.key"
RSA_PUB = "sysmanage-tools.rsa.pub"


# --- the site's RSA key -----------------------------------------------------


def ensure_rsa_key(
    private_dir: str, public_dir: str
) -> Tuple[Optional[object], Optional[str]]:
    """``(private key, public PEM path)``: made the first time (RSA 4096),
    the private half 0600 in ``private_dir``, the public half published in
    ``public_dir``."""
    os.makedirs(private_dir, mode=0o700, exist_ok=True)
    path = os.path.join(private_dir, RSA_KEY)
    if os.path.isfile(path):
        with open(path, "rb") as handle:
            key = serialization.load_pem_private_key(handle.read(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())  # fmt: skip
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(pem)
    os.makedirs(public_dir, exist_ok=True)
    public = os.path.join(public_dir, RSA_PUB)
    with open(public, "wb") as out:
        out.write(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                serialization.PublicFormat.SubjectPublicKeyInfo))  # fmt: skip
    return key, public


def key_name(public_pem: bytes) -> str:
    """The name the key goes by on a host: ``sysmanage-tools-<8 hex>``."""
    return "sysmanage-tools-" + hashlib.sha256(public_pem).hexdigest()[:8]


def _sign(key, data: bytes, algorithm) -> bytes:
    return key.sign(data, padding.PKCS1v15(), algorithm)


# --- tar and gzip as the tools write them -----------------------------------


def _tar_member(name: str, data: bytes) -> bytes:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o644
    info.mtime = int(time.time())
    info.uname = info.gname = "root"
    return info.tobuf(format=tarfile.USTAR_FORMAT) + data + b"\0" * ((-len(data)) % 512)


def _tar(members: List[Tuple[str, bytes]], cut: bool = False) -> bytes:
    body = b"".join(_tar_member(name, data) for name, data in members)
    return body if cut else body + b"\0" * 1024


def _gzip(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=9, mtime=0)


# --- Alpine -----------------------------------------------------------------


def _gzip_members(data: bytes) -> List[bytes]:
    """The compressed bytes of each gzip member of an .apk."""
    found, pos = [], 0
    while pos < len(data):
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        stream.decompress(data[pos:])
        used = len(data) - pos - len(stream.unused_data)
        if used <= 0:
            break
        found.append(data[pos : pos + used])
        pos += used
    return found


_APK_FIELDS = (
    ("pkgname", "P"), ("pkgver", "V"), ("arch", "A"), (None, "S"), ("size", "I"),
    ("pkgdesc", "T"), ("url", "U"), ("license", "L"), ("origin", "o"),
    ("maintainer", "m"), ("builddate", "t"), ("commit", "c"), ("provider_priority", "k"),
)  # fmt: skip
_APK_LISTS = (("depend", "D"), ("provides", "p"), ("install_if", "i"))


def apk_entry(path: str) -> Optional[Dict[str, str]]:
    """The index entry of one .apk: ``{"arch", "text"}``, or None when it is
    not one."""
    with open(path, "rb") as handle:
        data = handle.read()
    members = _gzip_members(data)
    control = None
    for member in members[:2]:
        raw = gzip.decompress(member)
        with tarfile.open(fileobj=io.BytesIO(raw + b"\0" * 1024)) as tar:
            if ".PKGINFO" in tar.getnames():
                pkginfo = tar.extractfile(".PKGINFO").read()
                control = (member, pkginfo.decode("utf-8", "replace"))
                break
    if control is None:
        return None
    info: Dict[str, List[str]] = {}
    for line in control[1].splitlines():
        if " = " in line and not line.startswith("#"):
            key, value = line.split(" = ", 1)
            info.setdefault(key.strip(), []).append(value.strip())
    lines = [
        # apk's own checksum format, not a security choice of ours.
        "C:Q1"
        + base64.b64encode(
            hashlib.sha1(control[0], usedforsecurity=False).digest()
        ).decode()
    ]
    for key, letter in _APK_FIELDS:
        value = str(len(data)) if key is None else (info.get(key) or [None])[0]
        if value:
            lines.append(f"{letter}:{value}")
    for key, letter in _APK_LISTS:
        if info.get(key):
            lines.append(f"{letter}:{' '.join(info[key])}")
    # apk fetches ``<arch>/<name>-<version>.apk``, whatever the file was called.
    stored = (
        f"{(info.get('pkgname') or ['?'])[0]}-{(info.get('pkgver') or ['?'])[0]}.apk"
    )
    return {"arch": (info.get("arch") or ["noarch"])[0], "text": "\n".join(lines) + "\n",
            "stored": stored}  # fmt: skip


def build_apk_repository(
    folder: str, key, public_pem: bytes, arches=("x86_64", "aarch64")
) -> Optional[str]:
    """Sort the .apk files in ``folder`` into ``<arch>/`` (noarch into every
    one) and write each arch's signed ``APKINDEX.tar.gz``.  None, or why not."""
    entries = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".apk"):
            entry = apk_entry(os.path.join(folder, name))
            if entry:
                entries.append((name, entry))
    if not entries:
        return "no Alpine package could be read"
    for arch in arches:
        chosen = [(n, e) for n, e in entries if e["arch"] in (arch, "noarch")]
        if not chosen:
            continue
        target = os.path.join(folder, arch)
        os.makedirs(target, exist_ok=True)
        for name, entry in chosen:
            shutil.copyfile(
                os.path.join(folder, name), os.path.join(target, entry["stored"])
            )
        index = "\n".join(e["text"] for _n, e in chosen) + "\n"
        payload = _gzip(
            _tar([("DESCRIPTION", b"SysManage tools"), ("APKINDEX", index.encode())])
        )
        signature = _sign(key, payload, hashes.SHA256())
        head = _gzip(
            _tar(
                [(f".SIGN.RSA256.{key_name(public_pem)}.rsa.pub", signature)], cut=True
            )
        )
        with open(os.path.join(target, "APKINDEX.tar.gz"), "wb") as out:
            out.write(head + payload)
    for name, _entry in entries:
        os.unlink(os.path.join(folder, name))
    return None


# --- FreeBSD ----------------------------------------------------------------

_PKG_B32 = "ybndrfg8ejkmcpqxot1uwisza345h769"


def pkg_sum(path: str) -> str:
    """pkg's ``sum``: ``2$`` and its base32 of the file's BLAKE2b-512."""
    digest = hashlib.blake2b()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    out, acc, bits = [], 0, 0
    for byte in digest.digest():
        acc |= byte << bits
        bits += 8
        while bits >= 5:
            out.append(_PKG_B32[acc & 31])
            acc >>= 5
            bits -= 5
    if bits:
        out.append(_PKG_B32[acc & 31])
    return "2$" + "".join(out)


def compact_manifest(path: str) -> Optional[dict]:
    """A package's ``+COMPACT_MANIFEST``; pkg packs with zstd (or xz)."""
    if shutil.which("zstd") is None:
        raise RuntimeError("zstd is not installed")
    with subprocess.Popen(["zstd", "-dcq", path], stdout=subprocess.PIPE,  # nosec B603 B607
                          stderr=subprocess.DEVNULL) as proc:  # fmt: skip
        try:
            with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
                for member in tar:
                    if member.name.lstrip("/") == "+COMPACT_MANIFEST":
                        return json.loads(tar.extractfile(member).read())
        finally:
            proc.kill()
    return None


_FIRST = ("name", "origin", "version", "comment", "maintainer", "www", "abi", "arch",
          "prefix")  # fmt: skip


def _pkg_entry(folder: str, name: str) -> Optional[dict]:
    path = os.path.join(folder, "All", name)
    manifest = compact_manifest(path)
    if not manifest:
        return None
    entry = {k: manifest[k] for k in _FIRST if k in manifest}
    entry["sum"] = pkg_sum(path)
    entry["flatsize"] = manifest.get("flatsize", 0)
    entry["path"] = entry["repopath"] = f"All/{name}"
    for key, value in manifest.items():
        if key not in entry:
            entry[key] = value
    entry["pkgsize"] = os.path.getsize(path)
    return entry


def _signed(key, name: str, catalog: bytes) -> bytes:
    signature = (
        _sign(key, hashlib.sha256(catalog).hexdigest().encode(), hashes.SHA256())
        + b"\0"
    )
    return _gzip(_tar([("signature", signature), (name, catalog)]))


META = ('version = 2;\npacking_format = "tgz";\nmanifests = "packagesite.yaml";\n'
        'data = "data";\nfilesite = "files";\nmanifests_archive = "packagesite";\n'
        'filesite_archive = "files";\n')  # fmt: skip


def build_pkg_repository(folder: str, key) -> Optional[str]:
    """Move the .pkg files in ``folder`` into ``All/`` and write the signed
    catalog beside it.  None, or why not."""
    os.makedirs(os.path.join(folder, "All"), exist_ok=True)
    for name in os.listdir(folder):
        if name.endswith(".pkg") and name not in ("packagesite.pkg", "data.pkg"):
            os.replace(os.path.join(folder, name), os.path.join(folder, "All", name))
    try:
        entries = [
            e
            for e in (
                _pkg_entry(folder, n)
                for n in sorted(os.listdir(os.path.join(folder, "All")))
            )
            if e
        ]
    except RuntimeError as error:
        return str(error)
    if not entries:
        return "no FreeBSD package could be read"
    lines = "".join(
        json.dumps(e, separators=(",", ":")) + "\n" for e in entries
    ).encode()
    data = json.dumps({"groups": [], "expired_packages": [], "packages": entries},
                      separators=(",", ":")).encode()  # fmt: skip
    with open(os.path.join(folder, "packagesite.pkg"), "wb") as out:
        out.write(_signed(key, "packagesite.yaml", lines))
    with open(os.path.join(folder, "data.pkg"), "wb") as out:
        out.write(_signed(key, "data", data))
    for name in ("meta.conf", "meta"):
        with open(os.path.join(folder, name), "w", encoding="ascii") as out:
            out.write(META)
    return None
