# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Per-site backup targets through federation (ROADMAP 27.3).

The controller defines a fleet-wide backup tag policy once; each site makes
it one of its own tag policies, resolving the target there (by name, then
location, else its default).  Each site reports its targets -- names, use
and health, never paths -- in its backup status."""

# pylint: disable=redefined-outer-name,unused-argument

import json
import uuid
from datetime import datetime

import pytest

from backend.api import backups_tag_policies as tag_api
from backend.persistence import models
from backend.services import backup_tag_policies as tag_policies
from backend.services import federation_backup_policy_apply as fed_backup
from backend.services import federation_inbox_service as inbox_svc
from backend.services import federation_policy_apply_service as apply_svc
from backend.services import federation_rollup_service as rollup_svc
from backend.services import federation_site_backup_rollup as site_backup
from tests.services.test_backup_results import _setup
from tests.services.test_federation_backup_rollup import (  # noqa: F401
    _body,
    site,
)
from tests.test_backups_api import MANAGER, _status
from tests.test_backups_targets import _second

NOW = datetime(2026, 11, 20, 3, 0)


@pytest.fixture
def backup_engine(monkeypatch):
    monkeypatch.setattr(tag_policies, "engine_loaded", lambda: True)


def _definition(**over):
    definition = {
        "name": "Web servers",
        "tag": "web",
        "priority": 50,
        "settings": {"interval_hours": 12, "keep_last": 20},
    }
    definition.update(over)
    return definition


def _apply(session, definition, version=1, policy_id=None):
    inbox_svc.receive_policy(
        session,
        policy_id=policy_id or uuid.uuid4(),
        policy_type=fed_backup.POLICY_TYPE,
        name=definition.get("name") or "x",
        definition=definition,
        version=version,
    )
    session.commit()
    return apply_svc.apply_pending_policies(session)


def _row(session, name="Web servers"):
    return (
        session.query(models.BackupTagPolicy)
        .filter(models.BackupTagPolicy.name == name)
        .first()
    )


# --- the site applies the controller's policy ------------------------------


def test_a_pushed_policy_becomes_the_sites_own_tag_policy(session, backup_engine):
    _setup(session)
    assert _apply(session, _definition()) == {"applied": 1, "failed": 0}
    row = _row(session)
    assert row.managed_by == "federation" and row.priority == 50
    assert json.loads(row.settings)["interval_hours"] == 12
    assert row.target_id is None  # the site's default
    tag = session.get(models.Tag, row.tag_id)
    assert tag.name == "web"  # made, so hosts can be tagged


def test_the_target_resolves_at_each_site_by_name_then_location(session, backup_engine):
    _setup(session)
    second, _nas = _second(session, location="DC2")
    _apply(session, _definition(target={"name": "OFFSITE"}))
    assert _row(session).target_id == second.id
    _apply(session, _definition(name="b", target={"name": "nope", "location": "dc2"}))
    assert _row(session, "b").target_id == second.id
    _apply(session, _definition(name="c", target={"name": "nowhere"}))
    assert _row(session, "c").target_id is None  # falls back to the default


def test_a_newer_version_replaces_it(session, backup_engine):
    _setup(session)
    pid = uuid.uuid4()
    _apply(session, _definition(), policy_id=pid)
    _apply(session, _definition(enabled=False, priority=7), version=2, policy_id=pid)
    row = _row(session)
    assert row.enabled is False and row.priority == 7
    assert session.query(models.BackupTagPolicy).count() == 1


def test_a_sites_own_tag_policy_is_never_overwritten(session, backup_engine):
    _setup(session)
    session.add(
        models.BackupTagPolicy(
            id=uuid.uuid4(), name="Web servers", tag_id=uuid.uuid4(), priority=1,
            enabled=True, settings="{}", created_at=NOW, updated_at=NOW,
        )  # fmt: skip
    )
    session.commit()
    assert _apply(session, _definition()) == {"applied": 0, "failed": 1}
    assert _row(session).managed_by is None


@pytest.mark.parametrize(
    "over",
    [
        {"name": ""},
        {"tag": None},
        {"settings": "daily"},
        {"settings": {"interval_hours": 0}},
        {"priority": "high"},
    ],
)
def test_a_bad_definition_is_recorded_not_applied(session, backup_engine, over):
    _setup(session)
    assert _apply(session, _definition(**over))["failed"] == 1
    assert session.query(models.BackupTagPolicy).count() == 0


def test_without_the_backup_engine_the_site_refuses_and_retries(session):
    _setup(session)
    assert _apply(session, _definition()) == {"applied": 0, "failed": 1}
    received = session.query(models.FederationReceivedPolicy).one()
    assert received.applied is False and "Professional+" in received.apply_error


@pytest.mark.asyncio
async def test_a_pushed_policy_is_changed_only_at_the_controller(
    session, backup_engine, monkeypatch
):
    monkeypatch.setattr(tag_api.tag_policies, "engine_loaded", lambda: True)
    _setup(session)
    _apply(session, _definition())
    row = _row(session)
    body = tag_api.TagPolicyBody(name="x", tag_id=str(row.tag_id))
    assert (
        await _status(
            lambda: tag_api.update_tag_policy(str(row.id), body, session, MANAGER)
        )
        == 409
    )
    assert (
        await _status(lambda: tag_api.delete_tag_policy(str(row.id), session, MANAGER))
        == 409
    )


# --- each site reports its targets ------------------------------------------


def test_the_site_reports_its_targets_without_paths(session):
    s = _setup(session)
    second, _nas = _second(session, location="DC2")
    s.target.is_default = True
    session.commit()
    body = site_backup.collect_backup_rollup(session)
    names = [(t["name"], t["location"], t["is_default"]) for t in body["targets"]]
    assert names == [("nas", None, True), ("offsite", "DC2", False)]
    assert body["targets"][0]["hosts"] == 1
    text = json.dumps(body["targets"])
    assert "/srv" not in text and "/mnt" not in text and str(second.id) not in text


def test_the_controller_keeps_a_sites_targets(session, site):
    targets = [
        {"name": "nas", "location": "Office", "is_default": True, "hosts": 3,
         "problem": False, "used_percent": 41.5, "storage_path": "/srv/x"},
        "junk",
    ]  # fmt: skip
    rollup_svc.record_backup_rollup_snapshot(
        session, site_id=site.id, body=_body(targets=targets)
    )
    session.commit()
    view = rollup_svc.backup_rollup_dict(
        rollup_svc.get_latest_backup_rollup(session, site.id)
    )
    assert view["targets"] == [
        {"name": "nas", "location": "Office", "is_default": True, "hosts": 3,
         "problem": False, "used_percent": 41.5},
    ]  # fmt: skip


def test_an_older_site_without_targets_still_records(session, site):
    rollup_svc.record_backup_rollup_snapshot(session, site_id=site.id, body=_body())
    session.commit()
    view = rollup_svc.backup_rollup_dict(
        rollup_svc.get_latest_backup_rollup(session, site.id)
    )
    assert view["targets"] is None
    with pytest.raises(ValueError):
        rollup_svc.record_backup_rollup_snapshot(
            session, site_id=site.id, body=_body(targets="nas")
        )
