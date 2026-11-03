# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Break-glass key export -- in every edition (ROADMAP 24.6 S6).

A lost key is lost backups, and the SysManage server -- with OpenBAO behind
it -- is exactly what may be gone when backups are needed most.  So an
operator exports encrypted hosts' secret keys ahead of time, SEALED to a
public key of their own (an offline key, a smartcard, a key held in escrow):
one encrypted file with every key each host has held, a manifest of which
host, repository and storage path each belongs to, and a README with the
restore procedure for when the server is down.

It lives in the open-source server because a lapsed license must never lock
anyone out of their own backups ("please don't hold someone's safety
hostage", Bryan, 2026-11-03): getting your keys out keeps working without the
Pro+ engine, which calls this module rather than keeping a second copy.
Making, rotating and turning on encryption stay Pro+.

The file is built in memory and returned; nothing is written to disk on the
server, and the secret keys leave OpenBAO only inside it.  The caller audits
who, which hosts, the recipient key and the reason; exporting needs both
Manage Backups and Restore Files.
"""

import io
import json
import os
import re
import shutil
import subprocess  # nosec B404 - fixed argv, never a shell
import tarfile
import tempfile
import types
import uuid
from datetime import datetime, timezone

from backend.i18n import _
from backend.persistence import models


class BreakGlassRefused(Exception):
    """A break-glass export cannot be made as asked; the message says why."""


class BreakGlassError(Exception):
    """The export could not be made (gpg, OpenBAO); the message says why."""


MAX_RECIPIENT_BYTES = 64 * 1024
MIN_REASON_CHARS = 10
MAX_REASON_CHARS = 500
SIGNING_FILE = "keys/signing.pub.asc"
PRIVATE_KEY_MARKER = "BEGIN PGP PRIVATE KEY BLOCK"
_GPG_SECONDS = 120
_FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")
# gpg-agent listens on Unix sockets inside the GnuPG home, and a socket path
# may be at most 107 bytes.
_SOCKET_PATH_MAX = 107
_HOME_TAIL = len("/sysmanage-backup-key-XXXXXXXX/S.gpg-agent.browser")

_README = """SysManage backup keys -- break-glass export
============================================

Made {made} by {who} for: {reason}
Sealed to OpenPGP key {recipient}.

This archive holds the SECRET keys of encrypted SysManage backups.  Anyone
who has it can read those backups.  Keep it offline, and destroy it when a
newer export replaces it.

What is inside
--------------
manifest.json   every host in this export: its repository, where that
                repository lives on the storage host, and its keys (newest
                first) with when each was made and replaced
keys/<host>/    one file per key: an armored OpenPGP secret key
                (gpg --export-secret-keys), ready for restate --decrypt-with
keys/signing.pub.asc
                when snapshot signing is on: the PUBLIC key the storage
                host signs each snapshot with, for restate --trusted-key
                (no secret; manifest.json names it under "signing")

A host's snapshots may need ANY of its keys -- a backup taken after a key
rotation still reuses data written before it -- so always give restate
every key listed for that host.

Restoring with the SysManage server down
----------------------------------------
1. On a machine with the private key this archive is sealed to:

       gpg --decrypt sysmanage-backup-keys-....tar.asc > keys.tar
       tar -xf keys.tar

2. On the storage host (or any machine that can read the host's repository,
   for example over its NFS export), with restate 2.2 or later installed.
   The repository path for each host is in manifest.json
   ("storage_repository").  List its snapshots (the keys let restate read
   each snapshot's summary; without them it lists the names only):

       sudo restate snapshots \\
           --decrypt-with keys/<host>/1-<fingerprint>.asc \\
           --decrypt-with keys/<host>/2-<fingerprint>.asc \\
           /srv/backups/restate/<repository>

3. See what a restore would bring back, without writing anything:

       sudo restate restore --plan --trusted-key keys/signing.pub.asc \\
           --decrypt-with keys/<host>/1-<fingerprint>.asc \\
           --decrypt-with keys/<host>/2-<fingerprint>.asc \\
           /srv/backups/restate/<repository>::<snapshot>

4. Restore into an empty directory (or a new machine's root with --root),
   checking every file first:

       sudo restate restore --check-first --trusted-key keys/signing.pub.asc \\
           --root /restore/<host> \\
           --decrypt-with keys/<host>/1-<fingerprint>.asc \\
           --decrypt-with keys/<host>/2-<fingerprint>.asc \\
           /srv/backups/restate/<repository>::<snapshot>

   Leave out "::<snapshot>" for the newest.  Add --include/--exclude to
   restore only some paths.

   --trusted-key checks the snapshot's signature: one signed by the
   storage host's key restores, and one signed by any other key, or
   tampered with, is refused.  A snapshot taken before signing was turned
   on is unsigned, and so is every snapshot when this export has no
   keys/signing.pub.asc (signing is off): restore those with
   --allow-unverified in place of --trusted-key.  Give --allow-unverified
   only for such a snapshot, never beside --trusted-key, or a snapshot
   whose signature was stripped would pass as one that never had one.

   Restored onto another operating system, owners and groups are matched by
   name; a group that system lacks keeps its number (Ubuntu's "adm", gid 4,
   shows as FreeBSD's "tty").  Restore onto the same OS to keep them.

5. Delete keys.tar, the keys/ directory and anything else that held a
   secret key when you are done (shred -u on Linux, rm -P on FreeBSD,
   where the disk allows it).

If restate says gpg "cannot decrypt with the secret key --decrypt-with
gives once it is imported", the machine's libgcrypt is 1.12.0 and the key
is a cv25519 one (GnuPG T8094): run restate on a machine with libgcrypt
1.12.1 or later, or import the keys into a GnuPG home first and run restate
with GNUPGHOME pointing at it.
"""


def _tmp_root(isdir=os.path.isdir, access=os.access):
    """A tmpfs for the GnuPG home when the server has one."""
    for candidate in ("/dev/shm", "/run/shm"):  # nosec B108
        if isdir(candidate) and access(candidate, os.W_OK | os.X_OK):
            return candidate
    return None


def _short_enough(root):
    """``root`` when a GnuPG home under it keeps gpg-agent's sockets within
    the limit; else /tmp."""
    base = root or tempfile.gettempdir()
    if len(os.path.abspath(base)) + _HOME_TAIL <= _SOCKET_PATH_MAX:
        return root
    return "/tmp"  # nosec B108 - mkdtemp makes a private 0700 directory there


def _gpg(gpg, home, args, run, stdin=None):
    argv = [gpg, "--homedir", home, "--batch", "--no-tty",
            "--pinentry-mode", "loopback", "--passphrase", ""] + list(args)  # fmt: skip
    done = run(argv, input=stdin, capture_output=True, timeout=_GPG_SECONDS,
               check=False)  # nosec B603  # fmt: skip
    if done.returncode != 0:
        detail = (done.stderr or b"").decode("utf-8", "replace").strip()
        raise BreakGlassError(_("gpg failed: %s") % detail[-300:])
    return (done.stdout or b"").decode("utf-8", "replace")


def _remove_home(home, run):
    """Stop the GnuPG home's gpg-agent and remove the home, whatever happened."""
    try:
        run([shutil.which("gpgconf") or "gpgconf", "--homedir", home, "--kill", "all"],
            capture_output=True, timeout=30, check=False)  # nosec B603  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        pass
    shutil.rmtree(home, ignore_errors=True)


def _gpg_binary(gpg):
    found = gpg or shutil.which("gpg")
    if not found:
        raise BreakGlassError(
            _("gpg is not installed on the SysManage server; install GnuPG")
        )
    return found


def _fingerprint(listing):
    for line in listing.splitlines():
        fields = line.split(":")
        if fields[0] == "fpr" and len(fields) > 9 and _FINGERPRINT.match(fields[9]):
            return fields[9]
    raise BreakGlassRefused(_("gpg could not read that public key"))


def inspect_recipient(public, gpg=None, run=subprocess.run, tmp_root=None):
    """``(fingerprint, user id)`` of the operator's armored public key, which
    must be exactly one usable key that can encrypt; BreakGlassRefused
    otherwise."""
    if not isinstance(public, str) or len(public.encode("utf-8")) > MAX_RECIPIENT_BYTES:
        raise BreakGlassRefused(_("Paste one armored OpenPGP public key"))
    text = public.strip()
    if "PRIVATE KEY" in text:
        raise BreakGlassRefused(
            _("That is a SECRET key; paste the PUBLIC key (gpg --armor --export)")
        )
    if not text.startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----"):
        raise BreakGlassRefused(_("Paste one armored OpenPGP public key"))
    gpg = _gpg_binary(gpg)
    root = _short_enough(tmp_root or _tmp_root())
    home = tempfile.mkdtemp(prefix="sysmanage-backup-key-", dir=root)
    try:
        os.chmod(home, 0o700)
        show = ["--with-colons", "--import-options", "show-only", "--import"]
        listing = _gpg(gpg, home, show, run, stdin=(text + "\n").encode("utf-8"))
    except BreakGlassError as failed:
        raise BreakGlassRefused(_("gpg could not read that public key")) from failed
    finally:
        _remove_home(home, run)
    return _recipient_from_listing(listing)


def _recipient_from_listing(listing):
    keys = [line.split(":") for line in listing.splitlines() if line.startswith("pub:")]
    if len(keys) != 1:
        raise BreakGlassRefused(_("Paste exactly one public key, not several"))
    fields = keys[0]
    if fields[1] in ("e", "r", "d", "i", "n"):
        raise BreakGlassRefused(_("That key is expired, revoked or not valid"))
    if len(fields) < 12 or "E" not in fields[11]:
        raise BreakGlassRefused(
            _("That key cannot encrypt (it has no usable encryption key)")
        )
    uid = ""
    for line in listing.splitlines():
        if line.startswith("uid:"):
            parts = line.split(":")
            uid = parts[9] if len(parts) > 9 else ""
            break
    return _fingerprint(listing), uid


def check_reason(reason):
    """The reason an export is made, trimmed: it goes in the audit log and
    the README, so it has to say something."""
    text = reason.strip() if isinstance(reason, str) else ""
    if not MIN_REASON_CHARS <= len(text) <= MAX_REASON_CHARS:
        raise BreakGlassRefused(
            _("Say why the keys are exported, in %(min)d to %(max)d characters")
            % {"min": MIN_REASON_CHARS, "max": MAX_REASON_CHARS}
        )
    return text


def _iso_or_none(value):
    return value.isoformat() + "Z" if value else None


def policy_key_rows(db, policy):
    """The policy's key rows not yet retired, newest first."""
    return (
        db.query(models.BackupPolicyKey)
        .filter(
            models.BackupPolicyKey.policy_id == policy.id,
            models.BackupPolicyKey.retired_at.is_(None),
        )
        .order_by(models.BackupPolicyKey.created_at.desc())
        .all()
    )


def encrypted_pairs(db, host_ids=None):
    """(host, policy) for every encrypted policy -- of ``host_ids`` when
    given -- whose host still exists, ordered by host name."""
    query = db.query(models.BackupPolicy).filter(
        models.BackupPolicy.encrypt_public_key.isnot(None)
    )
    if host_ids is not None:
        wanted = []
        for host_id in host_ids:
            try:
                wanted.append(uuid.UUID(str(host_id)))
            except ValueError:
                continue
        query = query.filter(models.BackupPolicy.host_id.in_(wanted))
    pairs = []
    for policy in query.all():
        host = db.query(models.Host).filter(models.Host.id == policy.host_id).first()
        if host is not None:
            pairs.append((host, policy))
    return sorted(pairs, key=lambda pair: pair[0].fqdn or "")


def _held_keys(db, policy, host, vault, keys):
    rows = list((keys or policy_key_rows)(db, policy))
    if not rows and policy.encrypt_key_ref:  # encrypted before key rows existed
        rows = [types.SimpleNamespace(
            fingerprint=policy.encrypt_fingerprint, subkey_id=None,
            key_ref=policy.encrypt_key_ref, created_at=policy.encrypted_at,
            replaced_at=None)]  # fmt: skip
    held = []
    for row in rows:
        stored = vault.retrieve_secret(row.key_ref)
        content = stored.get("content") if isinstance(stored, dict) else None
        if not isinstance(content, str) or PRIVATE_KEY_MARKER not in content:
            raise BreakGlassError(
                _("OpenBAO does not hold every backup key of %s; nothing was exported")
                % host.fqdn
            )
        held.append({"fingerprint": row.fingerprint, "subkey_id": row.subkey_id,
                     "created_at": _iso_or_none(row.created_at),
                     "replaced_at": _iso_or_none(row.replaced_at),
                     "secret": content})  # fmt: skip
    return held


def gather_export(db, pairs, target, vault=None, keys=None):
    """The manifest entries and secret keys for ``pairs`` of (host, policy):
    every key each policy holds and has not retired, newest first, read from
    OpenBAO.  Raises BreakGlassError if OpenBAO lacks one -- an export with a
    key missing would be found out only when it is needed."""
    if vault is None:
        from backend.services.vault_service import (  # pylint: disable=import-outside-toplevel
            VaultService,
        )

        vault = VaultService()
    storage = (
        (getattr(target, "storage_path", None) or "").rstrip("/") if target else ""
    )
    entries = []
    for host, policy in pairs:
        repository = policy.repository_dir
        entries.append({
            "host": host.fqdn, "host_id": str(host.id), "policy_id": str(policy.id),
            "repository": repository,
            "previous_repository": policy.previous_repository_dir,
            "storage_repository": f"{storage}/{repository}"
            if storage and repository else None,
            "keys": _held_keys(db, policy, host, vault, keys),
        })  # fmt: skip
    return entries


def _safe_name(text):
    return re.sub(r"[^A-Za-z0-9._-]", "_", text or "host")[:120] or "host"


def signer_of(target):
    """The target's snapshot signer as the export carries it -- its public
    key and fingerprint -- or None when signing is off."""
    public = getattr(target, "sign_public_key", None) if target else None
    if not isinstance(public, str) or "BEGIN PGP PUBLIC KEY BLOCK" not in public:
        return None
    return {"fingerprint": getattr(target, "sign_fingerprint", None), "public": public}


def build_bundle(entries, made, who, reason, recipient, signer=None):
    """The plain tar archive: README.txt, manifest.json (no secrets), one
    armored secret key per file under keys/<host>/, and, with snapshot
    signing on, the signer's PUBLIC key as keys/signing.pub.asc."""
    manifest = {"made": made, "made_by": who, "reason": reason, "sealed_to": recipient,
                "hosts": []}  # fmt: skip
    files = []
    for entry in entries:
        folder = _safe_name(entry["host"])
        listed = []
        for number, key in enumerate(entry["keys"], start=1):
            name = f"keys/{folder}/{number}-{key['fingerprint']}.asc"
            files.append((name, key["secret"].encode("utf-8")))
            listed.append(
                {k: v for k, v in key.items() if k != "secret"} | {"file": name}
            )
        manifest["hosts"].append({k: v for k, v in entry.items() if k != "keys"}
                                 | {"keys": listed})  # fmt: skip
    manifest["signing"] = None
    if signer:
        files.append((SIGNING_FILE, signer["public"].encode("utf-8")))
        manifest["signing"] = {
            "fingerprint": signer.get("fingerprint"),
            "file": SIGNING_FILE,
        }
    readme = _README.format(made=made, who=who, reason=reason, recipient=recipient)
    files[:0] = [("README.txt", readme.encode("utf-8")),
                 ("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))]  # fmt: skip
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def seal_bundle(
    bundle, public, fingerprint, gpg=None, run=subprocess.run, tmp_root=None
):
    """The bundle encrypted, armored, to the operator's key alone."""
    gpg = _gpg_binary(gpg)
    root = _short_enough(tmp_root or _tmp_root())
    home = tempfile.mkdtemp(prefix="sysmanage-backup-key-", dir=root)
    try:
        os.chmod(home, 0o700)
        _gpg(
            gpg, home, ["--import"], run, stdin=(public.strip() + "\n").encode("utf-8")
        )
        sealed = _gpg(gpg, home, ["--armor", "--trust-model", "always", "--recipient",
                                  fingerprint, "--encrypt"], run, stdin=bundle)  # fmt: skip
    finally:
        _remove_home(home, run)
    if "BEGIN PGP MESSAGE" not in sealed:
        raise BreakGlassError(_("gpg did not seal the key export"))
    return sealed


def break_glass_export(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db, pairs, target, recipient_key, reason, who, now=None,
    inspect=None, gather=None, seal=None,
):  # fmt: skip
    """``(file name, armored sealed archive, summary)`` for an export of the
    keys of ``pairs`` of (host, policy).  The caller audits and commits."""
    if not pairs:
        raise BreakGlassRefused(_("None of the chosen hosts has encrypted backups"))
    text = check_reason(reason)
    fingerprint, uid = (inspect or inspect_recipient)(recipient_key)
    entries = (gather or gather_export)(db, pairs, target)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    made = now.isoformat(timespec="seconds") + "Z"
    recipient = f"{fingerprint} ({uid})" if uid else fingerprint
    signer = signer_of(target)
    bundle = build_bundle(entries, made, who, text, recipient, signer)
    for entry in entries:
        for key in entry["keys"]:
            key["secret"] = None  # nothing below needs them; let them go
    sealed = (seal or seal_bundle)(bundle, recipient_key, fingerprint)
    bundle = None
    name = f"sysmanage-backup-keys-{now:%Y%m%dT%H%M%SZ}.tar.asc"
    summary = {
        "recipient": fingerprint,
        "hosts": [entry["host"] for entry in entries],
        "keys": sum(len(entry["keys"]) for entry in entries),
        "reason": text,
        "signing": bool(signer),
    }
    return name, sealed, summary
