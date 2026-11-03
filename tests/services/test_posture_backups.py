# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backups as posture fleet coverage (ROADMAP 24.6): one state per approved
host for a policy, healthy backups, a recent full-read verification and a
current break-glass export -- never "ok" without proof."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import posture_backups as pb
from backend.services import posture_evidence as pe
from tests.services.test_backup_results import _host, _setup

NOW = datetime(2026, 11, 2, 12, 0)


def _run(session, policy, host, action, status, ended):
    session.add(
        models.BackupRun(
            id=uuid.uuid4(), policy_id=policy.id, host_id=host.id, action=action,
            status=status, queued_at=ended, finished_at=ended,
        )  # fmt: skip
    )
    session.flush()


def _rows(session, hosts, can_verify=True):
    with patch.object(pb, "_verification_possible", return_value=can_verify):
        return {
            c["coverage"]: c for c in pb.coverage(session, hosts, NOW, pe._coverage)
        }


def _counts(row):
    return row["hosts_ok"], row["hosts_failing"], row["hosts_unknown"]


def test_a_host_restate_can_back_up_needs_an_enabled_policy(session):
    s = _setup(session)
    bare = _host(session, fqdn="bare.lab")
    mac = _host(session, fqdn="mac.lab")
    mac.platform = "macOS"
    session.flush()
    rows = _rows(session, [s.host, bare, mac])
    assert _counts(rows["backup_policy"]) == (1, 1, 0)  # the Mac is not counted
    s.policy.enabled = False
    assert _counts(_rows(session, [s.host, bare])["backup_policy"]) == (0, 2, 0)


def test_failed_overdue_and_not_yet_run_backups(session):
    s = _setup(session)
    assert _counts(_rows(session, [s.host])["backup_healthy"]) == (0, 0, 1)  # never
    _run(session, s.policy, s.host, "capture", "ok", NOW - timedelta(hours=3))
    assert _counts(_rows(session, [s.host])["backup_healthy"]) == (1, 0, 0)
    _run(session, s.policy, s.host, "capture", "failed", NOW - timedelta(hours=1))
    assert _counts(_rows(session, [s.host])["backup_healthy"]) == (0, 1, 0)


def test_an_overdue_backup_is_failing(session):
    s = _setup(session)
    _run(session, s.policy, s.host, "capture", "ok", NOW - timedelta(days=3))
    assert _counts(_rows(session, [s.host])["backup_healthy"]) == (0, 1, 0)


def test_verified_means_a_full_read_pass_within_30_days(session):
    s = _setup(session)
    assert _counts(_rows(session, [s.host])["backup_verified"]) == (0, 1, 0)
    _run(session, s.policy, s.host, jobs.VERIFY, "ok", NOW - timedelta(days=40))
    assert _counts(_rows(session, [s.host])["backup_verified"]) == (0, 1, 0)
    _run(session, s.policy, s.host, jobs.VERIFY, "ok", NOW - timedelta(days=2))
    assert _counts(_rows(session, [s.host])["backup_verified"]) == (1, 0, 0)


def test_without_the_backup_engine_verification_is_not_counted(session):
    """No host could ever pass: the control does not apply."""
    s = _setup(session)
    row = _rows(session, [s.host], can_verify=False)["backup_verified"]
    assert row["hosts_total"] == 0


def _audit(session, host, description, when):
    session.add(
        models.AuditLog(
            id=uuid.uuid4(), timestamp=when, action_type="UPDATE",
            entity_type="host", entity_id=str(host.id), description=description,
            result="SUCCESS",
        )  # fmt: skip
    )
    session.flush()


def test_key_escrow_needs_an_export_after_the_newest_key(session):
    s = _setup(session)
    assert _rows(session, [s.host])["backup_key_escrow"]["hosts_total"] == 0  # plain
    s.policy.encrypt_fingerprint = "A" * 40
    s.policy.encrypted_at = NOW - timedelta(days=10)
    session.flush()
    assert _counts(_rows(session, [s.host])["backup_key_escrow"]) == (0, 1, 0)
    _audit(session, s.host, pb.BREAK_GLASS_AUDIT, NOW - timedelta(days=5))
    assert _counts(_rows(session, [s.host])["backup_key_escrow"]) == (1, 0, 0)
    # A rotation after the export: the export lacks the new key.
    s.policy.encrypt_rotated_at = NOW - timedelta(days=1)
    session.flush()
    assert _counts(_rows(session, [s.host])["backup_key_escrow"]) == (0, 1, 0)


def test_some_other_audit_entry_is_not_an_export(session):
    s = _setup(session)
    s.policy.encrypt_fingerprint = "A" * 40
    s.policy.encrypted_at = NOW - timedelta(days=10)
    _audit(session, s.host, "Backup encryption key rotated", NOW - timedelta(days=1))
    assert _counts(_rows(session, [s.host])["backup_key_escrow"]) == (0, 1, 0)


def test_the_posture_gatherer_carries_the_backup_rows(session):
    """posture_evidence._fleet_coverage includes the four rows."""
    s = _setup(session)
    with patch.object(pb, "_verification_possible", return_value=True):
        rows = {c["coverage"] for c in pe._fleet_coverage(session, NOW)}
    assert set(pb.BACKUP_COVERAGE_KEYS) <= rows
    assert set(pb.BACKUP_COVERAGE_KEYS) <= set(pe.COVERAGE_KEYS)
    assert s.host is not None


def test_backup_remedies_are_guided_to_the_backups_page():
    from backend.services import posture_remedies  # noqa: PLC0415

    for remedy in ("review_backups", "verify_backups", "export_backup_keys"):
        assert posture_remedies.GUIDED[remedy] == "backups"
