# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The off-site copy's break-glass export -- in every edition (ROADMAP 27.3).

The off-site copy is the last resort, for the day the site -- and with it
this server and OpenBAO -- is gone.  A key that only lived in OpenBAO would
make it worthless then.  So an operator exports, ahead of time, everything a
restore needs without SysManage, SEALED to a public key of their own (the
same as the backup keys' break-glass export, ``backup_breakglass``): the
bucket, region and prefix, the credentials, every key the copy has held, the
manifest of what is in the bucket, and a README with the procedure.

It lives in the open-source server: getting your data back must never depend
on a license.  The caller audits who, which copy and why.
"""

import base64
import io
import json
import tarfile
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import backup_breakglass as breakglass
from backend.services import backup_offsite as offsite
from backend.services import backup_offsite_runs as runs
from backend.services import backup_offsite_secrets as secrets

_README = """SysManage off-site cloud copy -- break-glass export
=================================================

Made {made} by {who}.  Reason: {reason}
Sealed to: {recipient}

This archive holds what a restore from the off-site copy needs with the
SysManage server gone: copy.json (the bucket, region, endpoint and prefix),
credentials.json (the AWS access key), keys/<key id>.key (each AES-256 key,
base64) and streams.json (every stream in the bucket, its parts and SHA-256s).
Keep it as safely as the data itself: with it, anyone can read the copy.

Every object in the bucket is encrypted with AES-256-GCM.  Its first 68
bytes are the header: "SMOC", version 1, flags, log2 of the chunk size, 0,
the key id (8 bytes), the stream id (16), the part index (4, big-endian) and
a salt (32).  The object's key is HKDF-SHA256(the key, salt, info
"sysmanage-offsite-v1" + the 8 key-id bytes).  Chunk i's nonce is 7 zero
bytes, i (4 bytes, big-endian) and 1 on the last chunk only, 0 before; the
header is each chunk's associated data.  smoc_decrypt.py here decrypts one
object (Python 3 and its "cryptography" package).  The SysManage agent's
offsite_cloud/restore.py does all of this (and the thaw); on a storage host
with a new agent, a restore from the SysManage Backups page uses this data.

By hand:
  1. Thaw every part of the chain you need (a full, then its incrementals in
     order, from streams.json):
       aws s3api restore-object --bucket B --key K \\
         --restore-request Days=7,GlacierJobParameters={{Tier=Bulk}}
     Deep Archive takes up to 48 hours (Bulk) or 12 (Standard).
  2. Download each part, check its SHA-256 against streams.json, decrypt it
     (python3 smoc_decrypt.py keys/<key id>.key <part>) and write the parts,
     in order, to: zfs receive -u <pool>/<new dataset> -- the full first,
     then each incremental.
  3. The dataset holds the restate repository as it was: restore from it.
"""


# Standard library + the "cryptography" package; reads one object, writes
# its plaintext.  Kept in step with the agent's offsite_cloud/crypto.py.
_DECRYPT = """#!/usr/bin/env python3
# Decrypt one object of a SysManage off-site copy:
#   python3 smoc_decrypt.py keys/<key id>.key <part file> >> stream
# Parts in order, the full's then each incremental's, make the zfs stream.
import hashlib, hmac, struct, sys, uuid
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import base64

HEADER = struct.Struct(">4sBBBB8s16sI32s")


def main(key_file, part_file):
    key = base64.b64decode(open(key_file).read().strip(), validate=True)
    data = open(part_file, "rb").read()
    raw = data[:HEADER.size]
    magic, version, _f, log2, _z, kid, _stream, _part, salt = HEADER.unpack(raw)
    if magic != b"SMOC" or version != 1:
        sys.exit("not a SysManage off-site object")
    if hmac.new(key, b"sysmanage-offsite-key-id", hashlib.sha256).digest()[:8] != kid:
        sys.exit("this object needs the key " + kid.hex())
    subkey = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt,
                  info=b"sysmanage-offsite-v1" + kid).derive(key)
    aead, size, offset, index = AESGCM(subkey), (1 << log2) + 16, HEADER.size, 0
    out = sys.stdout.buffer
    while True:
        chunk = data[offset:offset + size]
        offset += size
        last = offset >= len(data)
        nonce = bytes(7) + struct.pack(">I", index) + (b"\\1" if last else b"\\0")
        out.write(aead.decrypt(nonce, chunk, raw))
        if last:
            return
        index += 1


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
"""


def gather(db: Session, copy: models.BackupOffsiteCopy, vault=None) -> Dict[str, Any]:
    """Everything the archive holds, read from OpenBAO.  Raises if a key or
    the credentials cannot be read: an export missing one would be found out
    only when it is needed."""
    keys = (
        db.query(models.BackupOffsiteKey)
        .filter(models.BackupOffsiteKey.copy_id == copy.id)
        .order_by(models.BackupOffsiteKey.created_at).all()
    )  # fmt: skip
    if not keys:
        raise breakglass.BreakGlassRefused(_("This off-site copy has no key yet"))
    try:
        held = [(row, secrets.read_key(row.key_ref, row.key_id, vault)) for row in keys]
        credentials = secrets.read_credentials(copy.credentials_ref, vault)
    except secrets.SecretRefused as error:
        raise breakglass.BreakGlassError(str(error)) from error
    return {
        "copy": {"id": str(copy.id), "bucket": copy.bucket, "region": copy.region,
                 "endpoint": copy.endpoint, "prefix": copy.prefix,
                 "storage_class": copy.storage_class},
        "credentials": credentials,
        "keys": [{"key_id": row.key_id, "created_at": row.created_at.isoformat(),
                  "retired_at": row.retired_at.isoformat() if row.retired_at else None,
                  "secret": text} for row, text in held],
        "streams": [runs._stream_dict(r)  # pylint: disable=protected-access
                    for r in offsite.streams(db, copy.id, live_only=False)],
    }  # fmt: skip


def build_bundle(
    found: Dict[str, Any], made: str, who: str, reason: str, recipient: str
) -> bytes:
    files = [
        ("README.txt", _README.format(made=made, who=who, reason=reason,
                                      recipient=recipient).encode("utf-8")),
        ("copy.json", json.dumps(found["copy"], indent=2).encode("utf-8")),
        ("credentials.json", json.dumps(found["credentials"], indent=2).encode("utf-8")),
        ("streams.json", json.dumps(found["streams"], indent=2).encode("utf-8")),
        ("smoc_decrypt.py", _DECRYPT.encode("utf-8")),
    ]  # fmt: skip
    for key in found["keys"]:
        base64.b64decode(key["secret"], validate=True)  # never write a damaged key
        files.append(
            (f"keys/{key['key_id']}.key", (key["secret"] + "\n").encode("ascii"))
        )
    files.append(("keys/index.json", json.dumps(
        [{k: v for k, v in key.items() if k != "secret"} for key in found["keys"]], indent=2
    ).encode("utf-8")))  # fmt: skip
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def export(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session, copy_id: Any, recipient_key: str, reason: str, who: str,
    now=None, inspect=None, seal=None, vault=None,
) -> Tuple[str, str, Dict[str, Any]]:  # fmt: skip
    """``(file name, armored sealed archive, summary)``."""
    copy = offsite.get_copy(db, copy_id)
    text = breakglass.check_reason(reason)
    fingerprint, uid = (inspect or breakglass.inspect_recipient)(recipient_key)
    found = gather(db, copy, vault)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    made = now.isoformat(timespec="seconds") + "Z"
    recipient = f"{fingerprint} ({uid})" if uid else fingerprint
    bundle = build_bundle(found, made, who, text, recipient)
    summary = {"recipient": fingerprint, "copy_id": str(copy.id), "bucket": copy.bucket,
               "keys": [k["key_id"] for k in found["keys"]],
               "streams": len(found["streams"]), "reason": text}  # fmt: skip
    for key in found["keys"]:
        key["secret"] = None
    found["credentials"] = None
    sealed = (seal or breakglass.seal_bundle)(bundle, recipient_key, fingerprint)
    return f"sysmanage-offsite-keys-{now:%Y%m%dT%H%M%SZ}.tar.asc", sealed, summary
