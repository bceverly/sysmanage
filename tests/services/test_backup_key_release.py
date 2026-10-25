# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Releasing a run's decryption keys to its host (Pro+ backup_engine, S4):
only the host's own pending keyed run, once, within the window, from the
engine -- and over HTTPS, never through the queue."""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest

from backend.api import agent_backup_key as endpoint
from backend.services import backup_jobs as jobs
from backend.services import backup_key_release as release
from tests.services.test_backup_encryption import _encrypt
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)

SECRET = "-----BEGIN PGP PRIVATE KEY BLOCK-----\nsec\n"


class _Engine:
    def __init__(self, fail=None):
        self.fail, self.asked = fail, []

    def secret_keys(self, policy):
        self.asked.append(policy.id)
        if self.fail:
            raise self.fail
        return [SECRET]


def _keyed_run(session, s, **params):
    _encrypt(session, s)
    run = jobs.queue_restore(
        session, s.policy, s.host, "20261025T130000Z", ["/etc/hosts"], False,
        allow_unverified=True, actor="admin", needs_key=True,
    )  # fmt: skip
    for key, value in params.items():
        setattr(run, key, value)
    session.commit()
    return run


@pytest.fixture
def loaded(monkeypatch):
    found = {"backup_engine": _Engine()}
    monkeypatch.setattr(release.module_loader, "get_module", found.get)
    return found


def test_a_hosts_own_pending_run_gets_its_keys_once(session, sent, loaded):
    s = _setup(session)
    run = _keyed_run(session, s)
    assert release.release(session, str(s.host.id), str(run.id)) == [SECRET]
    assert run.key_released_at is not None
    with pytest.raises(release.KeyRefused) as again:
        release.release(session, str(s.host.id), str(run.id))
    assert again.value.status == 409


def test_another_host_learns_nothing(session, sent, loaded):
    s = _setup(session)
    run = _keyed_run(session, s)
    for host_id, run_id in ((str(s.nas.id), str(run.id)), (str(s.host.id), "nope")):
        with pytest.raises(release.KeyRefused) as refused:
            release.release(session, host_id, run_id)
        assert refused.value.status == 404
    assert loaded["backup_engine"].asked == []


@pytest.mark.parametrize(
    "change",
    [{"status": "ok"}, {"queued_at": "old"}, {"parameters": json.dumps({"x": 1})},
     {"action": "capture"}],
)  # fmt: skip
def test_only_a_fresh_keyed_run_gets_a_key(session, sent, loaded, change):
    s = _setup(session)
    run = _keyed_run(session, s)
    if change.get("queued_at") == "old":
        change = {
            "queued_at": jobs.now() - release.RELEASE_WINDOW - timedelta(minutes=1)
        }
    for key, value in change.items():
        setattr(run, key, value)
    session.commit()
    with pytest.raises(release.KeyRefused) as refused:
        release.release(session, str(s.host.id), str(run.id))
    assert refused.value.status == 409
    assert run.key_released_at is None


def test_without_the_engine_no_key(session, sent, monkeypatch):
    s = _setup(session)
    run = _keyed_run(session, s)
    monkeypatch.setattr(release.module_loader, "get_module", lambda code: None)
    with pytest.raises(release.KeyRefused) as refused:
        release.release(session, str(s.host.id), str(run.id))
    assert refused.value.status == 402


def test_an_openbao_failure_is_a_503_and_releases_nothing(session, sent, monkeypatch):
    s = _setup(session)
    run = _keyed_run(session, s)
    failing = _Engine(fail=RuntimeError("OpenBAO is sealed"))
    monkeypatch.setattr(
        release.module_loader, "get_module", {"backup_engine": failing}.get
    )
    with pytest.raises(release.KeyRefused) as refused:
        release.release(session, str(s.host.id), str(run.id))
    assert refused.value.status == 503 and run.key_released_at is None


@pytest.mark.asyncio
async def test_the_endpoint_answers_with_no_store_and_audits(session, sent, loaded):
    s = _setup(session)
    run = _keyed_run(session, s)
    body = endpoint.KeyRequest(host_id=str(s.host.id), run_id=str(run.id))
    with patch.object(endpoint, "_authenticated_host_id", return_value=str(s.host.id)), \
            patch.object(endpoint, "_verify_host"), \
            patch.object(endpoint, "_host_session", return_value=session), \
            patch.object(endpoint.AuditService, "log") as audit:  # fmt: skip
        answer = await endpoint.agent_backup_key(None, body, "Bearer t", "h", session)
    assert json.loads(answer.body) == {"keys": [SECRET]}
    assert answer.headers["cache-control"] == "no-store"
    assert audit.call_args.kwargs["details"] == {"run_id": str(run.id)}
    assert SECRET not in json.dumps(audit.call_args.kwargs, default=str)
