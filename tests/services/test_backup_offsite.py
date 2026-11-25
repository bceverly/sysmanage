# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The off-site cloud copy, S3 Glacier Deep Archive (ROADMAP 27.3).

What must hold:
  * setting the copy up and running it needs Professional+; restoring,
    checking, turning it off and exporting its keys do not ("never hold
    safety hostage") -- and a lapse freezes the copy, it never removes it;
  * the credentials and the key live in OpenBAO only: never in the
    database, a command or a run's parameters; the storage host gets them
    once per run, its own run, within the hour;
  * an upload follows the engine's plan (bases, retention), and its result
    is what a restore is planned from -- a full and its incrementals, all
    under one key, never a broken chain;
  * the key export carries every key and the credentials, sealed.
"""

# pylint: disable=redefined-outer-name,protected-access
import base64
import io
import json
import tarfile
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.persistence import models
from backend.services import backup_offsite as offsite
from backend.services import backup_offsite_export as export
from backend.services import backup_offsite_runs as runs
from backend.services import backup_offsite_secrets as secrets
from backend.services import maintenance_command_classes as windows
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)
from tests.services.test_cloud_backup import _Vault

SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # nosec B105  # a test value
NOW = datetime(2026, 11, 25, 3, 0)


class FakeEngine(SimpleNamespace):
    """The Pro+ engine's off-site functions, as the real one answers them."""

    @staticmethod
    def offsite_defaults():
        return {"full_every_days": 30, "run_hour_utc": 2, "keep_monthly": 6, "keep_yearly": 7,
                "exclude": [], "include": [], "bandwidth": {"rules": [], "default_kbps": 0},
                "part_mib": 256}  # fmt: skip

    def offsite_settings(self, raw):
        if raw is not None and not isinstance(raw, dict):
            raise ValueError("bad")
        merged = self.offsite_defaults()
        merged.update({k: v for k, v in (raw or {}).items() if k in merged})
        return merged

    @staticmethod
    def offsite_retention(settings, storage_class):
        return {"incremental": 180, "monthly": 210, "yearly": 2585, "minimum": 180}

    @staticmethod
    def offsite_next_run(settings, after):
        moment = after.replace(
            hour=settings["run_hour_utc"], minute=0, second=0, microsecond=0
        )
        return moment if moment > after else moment + timedelta(days=1)

    @staticmethod
    def offsite_plan(settings, storage_class, key_id, datasets, yearly_done, now):
        bases = {n: s["last_snapshot"] for n, s in datasets.items()
                 if s.get("key_id") == key_id and s.get("last_full_at")
                 and now - s["last_full_at"] < timedelta(days=settings["full_every_days"])}  # fmt: skip
        cls = "monthly" if yearly_done else "yearly"
        return {"bases": bases, "full_class": cls,
                "retention": {"full_days": 210 if yearly_done else 2585,
                              "incremental_days": 180}}  # fmt: skip

    @staticmethod
    def offsite_lifecycle(prefix, days):
        return {"Rules": [{"ID": f"d{d}"} for d in days]}

    @staticmethod
    def offsite_iam_policy(bucket, prefix):
        return {"Statement": [{"Resource": f"arn:aws:s3:::{bucket}/{prefix}/*"}]}

    @staticmethod
    def offsite_cost(settings, storage_class, size):
        return {"monthly_usd": round(size / 1e9 * 0.00099, 2)}


@pytest.fixture
def vault(monkeypatch):
    fake = _Vault()
    monkeypatch.setattr(secrets, "_vault", lambda vault=None: vault or fake)
    return fake


@pytest.fixture
def licensed(monkeypatch):
    monkeypatch.setattr(offsite, "engine", FakeEngine)
    monkeypatch.setattr(offsite, "airgapped", lambda: False)


@pytest.fixture
def lapsed(monkeypatch):
    monkeypatch.setattr(offsite, "engine", lambda: None)
    monkeypatch.setattr(offsite, "airgapped", lambda: False)


def _copy(session, s, **over):
    data = {"target_id": str(s.target.id), "bucket": "acme-offsite", "region": "us-east-2",
            "prefix": "nas", "access_key": "AKIAIOSFODNN7EXAMPLE", "secret_key": SECRET}  # fmt: skip
    data.update(over)
    copy = offsite.create(session, data, "ops@example.com")
    session.commit()
    return copy


def _stream(copy_id, dataset, snapshot, base=None, kind="full", key_id="k", days=210,
            when=NOW):  # fmt: skip
    return {"stream_id": str(uuid.uuid4()), "dataset": dataset, "snapshot": snapshot,
            "base_snapshot": base, "kind": kind, "key_id": key_id, "retention_days": days,
            "storage_class": "DEEP_ARCHIVE", "created_at": when.isoformat(),
            "finished_at": (when + timedelta(minutes=5)).isoformat(), "stream_bytes": 100,
            "manifest_key": f"nas/m{days}/{copy_id}/{snapshot}/x",
            "parts": [{"index": 0, "key": f"nas/d{days}/x/000000", "bytes": 4 * 10**9,
                       "sha256": "a" * 64}]}  # fmt: skip


# --- setting it up --------------------------------------------------------------------------


def test_setting_up_needs_professional_plus(session, vault, lapsed):
    s = _setup(session)
    with pytest.raises(offsite.OffsiteRefused) as refused:
        _copy(session, s)
    assert refused.value.status == 402 and refused.value.code == "license"


def test_the_secrets_live_in_openbao_only(session, vault, licensed):
    s = _setup(session)
    copy = _copy(session, s)
    key = session.query(models.BackupOffsiteKey).filter_by(copy_id=copy.id).one()
    assert copy.credentials_ref in vault.store and key.key_ref in vault.store
    assert json.loads(vault.store[copy.credentials_ref])["secret_key"] == SECRET
    raw = base64.b64decode(vault.store[key.key_ref])
    assert len(raw) == 32 and secrets.key_id(raw) == key.key_id
    for table in ("backup_offsite_copy", "backup_offsite_key"):
        rows = session.execute(models.Base.metadata.tables[table].select()).fetchall()
        assert SECRET not in repr(rows) and vault.store[key.key_ref] not in repr(rows)
    assert copy.access_key_hint == "MPLE"
    assert copy.next_run_at == datetime.combine(
        offsite.now().date(), datetime.min.time()
    ).replace(hour=2) + (timedelta(days=1) if offsite.now().hour >= 2 else timedelta())


@pytest.mark.parametrize(
    "over,code",
    [({"bucket": "Bad_Bucket"}, "invalid_bucket"), ({"prefix": "../up"}, "invalid_prefix"),
     ({"endpoint": "ftp://x"}, "invalid_endpoint"), ({"secret_key": ""}, "invalid_credentials"),
     ({"storage_class": "ONEZONE"}, "invalid_storage_class")],
)  # fmt: skip
def test_bad_settings_are_refused(session, vault, licensed, over, code):
    s = _setup(session)
    with pytest.raises(offsite.OffsiteRefused) as refused:
        _copy(session, s, **over)
    assert refused.value.code == code


def test_an_air_gapped_site_has_no_offsite_copy(session, vault, licensed, monkeypatch):
    monkeypatch.setattr(offsite, "airgapped", lambda: True)
    with pytest.raises(offsite.OffsiteRefused) as refused:
        _copy(session, _setup(session))
    assert refused.value.code == "airgapped"


def test_after_a_lapse_it_can_be_turned_off_but_not_changed(
    session, vault, licensed, monkeypatch
):
    copy = _copy(session, _setup(session))
    monkeypatch.setattr(offsite, "engine", lambda: None)
    offsite.update(session, copy.id, {"enabled": False}, "ops")
    assert copy.enabled is False
    with pytest.raises(offsite.OffsiteRefused) as refused:
        offsite.update(session, copy.id, {"enabled": True}, "ops")
    assert refused.value.status == 402


def test_new_credentials_replace_the_old_in_openbao(session, vault, licensed):
    copy = _copy(session, _setup(session))
    old = copy.credentials_ref
    offsite.update(session, copy.id, {"access_key": "AKIANEWKEY0000000000", "secret_key": "n"},
                   "ops")  # fmt: skip
    assert copy.credentials_ref != old and old in vault.deleted
    assert copy.access_key_hint == "0000"


# --- running it ---------------------------------------------------------------------------


def test_an_upload_follows_the_plan_and_carries_no_secret(
    session, vault, licensed, sent
):
    s = _setup(session)
    copy = _copy(session, s)
    run = runs.queue_upload(session, copy.id, "ops")
    host, command, params = sent[-1]
    assert host == str(s.nas.id) and command == "offsite_cloud_run"
    assert (
        params["action"] == "upload"
        and params["storage_path"] == "/srv/backups/restate"
    )
    assert params["retention"] == {"full_days": 2585, "incremental_days": 180}
    assert params["bases"] == {} and params["part_bytes"] == 256 << 20
    assert SECRET not in json.dumps(params) and "AKIA" not in json.dumps(params)
    assert run.key_id == secrets.current_key(session, copy.id).key_id
    with pytest.raises(offsite.OffsiteRefused) as refused:
        runs.queue_upload(session, copy.id, "ops")
    assert refused.value.code == "busy"


def test_the_secrets_are_released_once_to_the_runs_own_host(
    session, vault, licensed, sent
):
    s = _setup(session)
    copy = _copy(session, s)
    run = runs.queue_upload(session, copy.id, "ops")
    with pytest.raises(secrets.SecretRefused):
        secrets.release(session, str(s.host.id), run.id)  # not the storage host
    got = secrets.release(session, str(s.nas.id), run.id)
    assert got["secret_key"] == SECRET and len(base64.b64decode(got["key"])) == 32
    with pytest.raises(secrets.SecretRefused, match="already"):
        secrets.release(session, str(s.nas.id), run.id)


def test_a_late_run_gets_no_secrets(session, vault, licensed, sent):
    s = _setup(session)
    run = runs.queue_upload(session, _copy(session, s).id, "ops")
    with pytest.raises(secrets.SecretRefused, match="too old"):
        secrets.release(
            session, str(s.nas.id), run.id, now=run.queued_at + timedelta(hours=2)
        )


def _uploaded(session, s, copy, streams, status="ok"):
    run = runs.queue_upload(session, copy.id, "ops")
    runs.record_result(session, str(s.nas.id), {"run_id": str(run.id), "status": status,
                                                "streams": streams, "bytes_uploaded": 5,
                                                "snapshot": streams[0]["snapshot"]})  # fmt: skip
    session.commit()
    return run


def test_results_become_the_record_and_the_next_plan(session, vault, licensed, sent):
    s = _setup(session)
    copy = _copy(session, s)
    kid = secrets.current_key(session, copy.id).key_id
    snap = "sysmanage-offsite-20261125T020000Z"
    run = _uploaded(session, s, copy, [_stream(copy.id, "tank/b", snap, key_id=kid,
                                               when=offsite.now())])  # fmt: skip
    assert (
        run.status == "ok" and copy.last_ok_at is not None and copy.last_error is None
    )
    view = offsite.view(session, copy)
    assert (
        view["datasets"][0]["dataset"] == "tank/b" and view["bytes_stored"] == 4 * 10**9
    )
    runs.queue_upload(session, copy.id, "ops")
    assert sent[-1][2]["bases"] == {"tank/b": snap}


def test_a_restore_point_is_its_full_and_incrementals_in_order(
    session, vault, licensed, sent
):
    s = _setup(session)
    copy = _copy(session, s)
    one, two, three = (f"sysmanage-offsite-2026112{d}T020000Z" for d in (3, 4, 5))
    _uploaded(session, s, copy, [
        _stream(copy.id, "tank/b", one, when=offsite.now() - timedelta(days=2)),
        _stream(copy.id, "tank/b", two, one, "incremental", when=offsite.now() - timedelta(days=1)),
        _stream(copy.id, "tank/b", three, two, "incremental", when=offsite.now()),
    ])  # fmt: skip
    links = runs.chain(session, copy.id, "tank/b", three)
    assert [(l["kind"], l["snapshot"]) for l in links] == [
        ("full", one),
        ("incremental", two),
        ("incremental", three),
    ]
    points = runs.restore_points(session, copy.id)
    assert [p["snapshot"] for p in points] == [three, two, one]
    cost = runs.estimate(links, "Bulk")
    assert cost["bytes"] == 12 * 10**9 and cost["thaw_hours"] == 48
    assert cost["usd_thaw"] == 0.03 and cost["usd_transfer"] == 1.08


def test_a_broken_chain_is_never_offered(session, vault, licensed, sent):
    s = _setup(session)
    copy = _copy(session, s)
    _uploaded(session, s, copy, [_stream(copy.id, "tank/b", "sysmanage-offsite-20261125T020000Z",
                                         "sysmanage-offsite-20261101T020000Z", "incremental",
                                         when=offsite.now())])  # fmt: skip
    assert runs.restore_points(session, copy.id) == []
    with pytest.raises(offsite.OffsiteRefused) as refused:
        runs.chain(session, copy.id, "tank/b", "sysmanage-offsite-20261125T020000Z")
    assert refused.value.code == "broken_chain"


def test_a_restore_works_after_a_lapse_with_the_chains_own_key(session, vault, licensed, sent,
                                                                monkeypatch):  # fmt: skip
    s = _setup(session)
    copy = _copy(session, s)
    old = secrets.current_key(session, copy.id).key_id
    snap = "sysmanage-offsite-20261125T020000Z"
    _uploaded(session, s, copy, [_stream(copy.id, "tank/b", snap, key_id=old,
                                         when=offsite.now())])  # fmt: skip
    new = offsite.rotate_key(session, copy.id, "ops")
    assert new != old
    monkeypatch.setattr(offsite, "engine", lambda: None)  # the license lapses
    run = runs.queue_restore(
        session, copy.id, "tank/b", snap, "tank/restored", "Bulk", "ops"
    )
    params = sent[-1][2]
    assert params["action"] == "restore" and params["target_dataset"] == "tank/restored"
    assert [p["snapshot"] for p in params["streams"]] == [snap]
    got = secrets.release(session, str(s.nas.id), run.id)
    assert secrets.key_id(base64.b64decode(got["key"])) == old


def test_the_scheduler_starts_due_copies_and_a_lapse_freezes_them(session, vault, licensed, sent,
                                                                  monkeypatch):  # fmt: skip
    s = _setup(session)
    copy = _copy(session, s)
    copy.next_run_at = offsite.now() - timedelta(minutes=1)
    assert runs.tick(session)["started"] == 1
    assert copy.next_run_at > offsite.now()
    monkeypatch.setattr(offsite, "engine", lambda: None)
    copy.next_run_at = offsite.now() - timedelta(minutes=1)
    assert runs.tick(session) == {"started": 0, "skipped": 0}


def test_a_message_for_another_hosts_run_is_ignored(session, vault, licensed, sent):
    s = _setup(session)
    run = runs.queue_upload(session, _copy(session, s).id, "ops")
    runs.record_result(session, str(s.host.id), {"run_id": str(run.id), "status": "ok"})
    assert run.status == "queued"


def test_a_failed_check_or_upload_says_why_on_the_copy(session, vault, licensed, sent):
    s = _setup(session)
    copy = _copy(session, s)
    run = runs.queue_check(session, copy.id, "ops")
    runs.record_result(session, str(s.nas.id), {"run_id": str(run.id), "status": "failed",
                                                "errors": ["S3 403 AccessDenied"]})  # fmt: skip
    assert "AccessDenied" in copy.last_error
    run = runs.queue_check(session, copy.id, "ops")
    runs.record_result(session, str(s.nas.id), {"run_id": str(run.id), "status": "ok",
                                                "object_lock": True})  # fmt: skip
    assert copy.lock_verified is True and copy.last_error is None


def test_only_the_check_skips_maintenance_windows():
    def envelope(action):
        return json.dumps({"data": {"command_type": "offsite_cloud_run",
                                    "parameters": {"action": action}}})  # fmt: skip

    assert windows.is_window_gated("command", envelope("check")) is False
    assert windows.is_window_gated("command", envelope("upload")) is True
    assert windows.is_window_gated("command", envelope("restore")) is True


# --- the key export --------------------------------------------------------------------------


def test_the_export_carries_every_key_and_the_credentials(
    session, vault, licensed, monkeypatch
):
    s = _setup(session)
    copy = _copy(session, s)
    offsite.rotate_key(session, copy.id, "ops")
    monkeypatch.setattr(offsite, "engine", lambda: None)  # works after a lapse
    sealed = {}

    def seal(bundle, recipient, fingerprint):
        sealed["bundle"] = bundle
        return "-----BEGIN PGP MESSAGE-----"

    name, armored, summary = export.export(
        session, copy.id, "PUBLIC KEY", "the site may flood this week", "ops",
        inspect=lambda key: ("A" * 40, "ops"), seal=seal,
    )  # fmt: skip
    assert name.startswith("sysmanage-offsite-keys-") and armored.startswith(
        "-----BEGIN"
    )
    assert len(summary["keys"]) == 2
    with tarfile.open(fileobj=io.BytesIO(sealed["bundle"])) as archive:
        names = archive.getnames()
        creds = json.loads(archive.extractfile("credentials.json").read())
    assert {"README.txt", "copy.json", "credentials.json", "streams.json",
            "keys/index.json"} <= set(names)  # fmt: skip
    assert sum(1 for n in names if n.endswith(".key")) == 2
    assert creds["secret_key"] == SECRET


def test_a_long_upload_is_not_an_error_and_a_silent_one_ends(
    session, vault, licensed, sent
):
    s = _setup(session)
    copy = _copy(session, s)
    run = runs.queue_upload(session, copy.id, "ops")
    runs.record_progress(session, str(s.nas.id), {"run_id": str(run.id), "part": 3})
    copy.next_run_at = offsite.now() - timedelta(minutes=1)
    assert runs.tick(session) == {"started": 0, "skipped": 1}
    assert copy.last_error is None and run.status == "running"
    later = offsite.now() + timedelta(hours=25)
    assert runs.fail_silent(session, later) == 1
    assert run.status == "failed" and "said nothing" in copy.last_error


def _smoc(key: bytes, data: bytes, chunk_log2: int = 12) -> bytes:
    """One object in the agent's format (offsite_cloud/crypto.py), built
    from the README's description, to prove the export's script."""
    # pylint: disable=import-outside-toplevel
    import hashlib
    import hmac
    import os
    import struct

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    kid = hmac.new(key, b"sysmanage-offsite-key-id", hashlib.sha256).digest()[:8]
    salt = os.urandom(32)
    raw = struct.pack(">4sBBBB8s16sI32s", b"SMOC", 1, 0, chunk_log2, 0, kid,
                      uuid.uuid4().bytes, 0, salt)  # fmt: skip
    sub = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt,
               info=b"sysmanage-offsite-v1" + kid).derive(key)  # fmt: skip
    size = 1 << chunk_log2
    chunks = [data[i : i + size] for i in range(0, len(data), size)] or [b""]
    out = [raw]
    for index, chunk in enumerate(chunks):
        last = index == len(chunks) - 1
        nonce = bytes(7) + struct.pack(">I", index) + (b"\1" if last else b"\0")
        out.append(AESGCM(sub).encrypt(nonce, chunk, raw))
    return b"".join(out)


def test_the_exports_script_decrypts_an_object_without_sysmanage(tmp_path):
    # pylint: disable=import-outside-toplevel
    import os
    import subprocess  # nosec B404 - runs the export's own script
    import sys

    key = os.urandom(32)
    data = os.urandom(10000)
    (tmp_path / "k.key").write_text(base64.b64encode(key).decode() + "\n")
    (tmp_path / "part").write_bytes(_smoc(key, data))
    (tmp_path / "smoc_decrypt.py").write_text(export._DECRYPT)
    done = subprocess.run(  # nosec B603 - fixed argv
        [sys.executable, str(tmp_path / "smoc_decrypt.py"), str(tmp_path / "k.key"),
         str(tmp_path / "part")], capture_output=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    assert done.stdout == data
    (tmp_path / "part").write_bytes(_smoc(key, data)[:-1])
    cut = subprocess.run(  # nosec B603 - fixed argv
        [sys.executable, str(tmp_path / "smoc_decrypt.py"), str(tmp_path / "k.key"),
         str(tmp_path / "part")], capture_output=True, check=False,
    )  # fmt: skip
    assert cut.returncode != 0
