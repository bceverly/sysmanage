# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Shared fakes for the repository-mirroring API tests.

Not named ``test_*`` so pytest doesn't collect it.  Lives here rather than in
``conftest.py`` because these are plain constructors, not fixtures -- the tests
build several differently-shaped sessions per test and fixtures would only add
indirection.  Split out when the mirroring API tests crossed the repo's
1000-line-per-file gate.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

API = "backend.api.repository_mirroring"
HOST_UUID = uuid.uuid4()
MIRROR_UUID = uuid.uuid4()

# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, rows, session=None):
        self._rows = rows
        self._session = session

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self.added = []
        self.deleted = []
        self.commits = 0
        self.flushes = 0
        self.rolled_back = False
        self.closed = False

    def query(self, model):
        return _FakeQuery(self._by_model.get(model.__name__, []), self)

    def add(self, row):
        self.added.append(row)
        if getattr(row, "id", None) is None:
            row.id = uuid.uuid4()

    def delete(self, row):
        self.deleted.append(row)

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def refresh(self, _row):
        pass

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def __contains__(self, _row):
        return True

    # get_session_local() returns a factory; the fake is its own factory so a
    # single object serves both ``Depends(get_tenant_db)`` and ``with
    # session_local() as session`` call sites.
    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _mirror(**overrides):
    row = SimpleNamespace(
        id=MIRROR_UUID,
        name="ubuntu-noble",
        package_manager="apt",
        host_id=HOST_UUID,
        suite="noble",
        components="main",
        upstream_url="http://archive.ubuntu.invalid/ubuntu",
        architectures="amd64",
        signing_key_url=None,
        bandwidth_cap_kbps=0,
        repoid=None,
        repo_alias=None,
        release=None,
        gpgkey_url=None,
        known_version_id=None,
        last_sync_status="SUCCESS",
        to_dict=lambda: {"id": str(MIRROR_UUID), "name": "ubuntu-noble"},
    )
    for action in ("last_sync", "last_snapshot", "last_restore"):
        for suffix in ("_at", "_status", "_error", "_message_id"):
            setattr(row, f"{action}{suffix}", None)
    row.last_sync_status = overrides.pop("last_sync_status", "SUCCESS")
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _known_version(**overrides):
    kv = SimpleNamespace(
        id=uuid.uuid4(),
        platform="apt",
        version_key="noble",
        os_family="ubuntu",
        label="Ubuntu 24.04",
        match_regex="noble|24\\.04",
        default_suite="noble",
        default_repoid=None,
        default_repo_alias=None,
        default_release=None,
    )
    for key, value in overrides.items():
        setattr(kv, key, value)
    return kv


def _engine():
    engine = MagicMock()
    engine.MirrorConfigError = ValueError
    for name in (
        "build_apt_apply_default_mirror_plan",
        "build_dnf_apply_default_mirror_plan",
        "build_zypper_apply_default_mirror_plan",
        "build_pkg_apply_default_mirror_plan",
        "build_apt_revert_default_mirror_plan",
        "build_dnf_revert_default_mirror_plan",
        "build_zypper_revert_default_mirror_plan",
        "build_pkg_revert_default_mirror_plan",
    ):
        getattr(engine, name).return_value = {"commands": [{"argv": [name]}]}
    engine.build_apt_mirror_sync_plan.return_value = {"commands": []}
    engine.build_mirror_snapshot_plan.return_value = {"commands": []}
    engine.build_mirror_restore_plan.return_value = {"commands": []}
    return engine


def _licensed(engine=None):
    return patch(f"{API}._check_mirror_module", return_value=engine or _engine())


def _dispatching(msg_id="msg-1"):
    return patch(f"{API}._dispatch_plan", return_value=msg_id)


def _settings(mirror_root_path="/srv/mirror"):
    return patch(
        f"{API}._get_settings",
        return_value=SimpleNamespace(
            mirror_root_path=mirror_root_path,
            to_dict=lambda: {"mirror_root_path": mirror_root_path},
        ),
    )
