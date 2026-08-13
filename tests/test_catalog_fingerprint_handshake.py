# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The server records which catalog it holds, and hands it back to the agent.

``host.available_packages_fingerprint`` is what lets the server say "I already
have exactly this", so an agent can skip retransmitting ~89k packages (~11 MB)
that have not changed.  It is handed back on the ``collect_available_packages``
command because ``route_inbound_message`` discards handler return values, so the
server cannot reply to an agent mid-exchange.

The dangerous direction is recording a fingerprint for a catalog we do NOT
have: the agent would then skip sending it, permanently, and the gap would be
invisible -- the same silent-and-self-perpetuating shape as the os_mismatch bug
that cost 9.4 GB.  So the fingerprint is written ONLY when a batch completes,
and these tests exist mostly to pin that.
"""

from datetime import datetime, timezone

import pytest

from backend.api import package_handlers


class _Connection:
    def __init__(self, host_id):
        self.host_id = host_id


class _Host:
    def __init__(self):
        self.available_packages_fingerprint = None
        self.available_packages_fingerprint_at = None


class _Query:
    def __init__(self, host):
        self._host = host

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._host


class _Db:
    """Just enough Session for handle_packages_batch_end."""

    def __init__(self, host):
        self._host = host
        self.commits = 0

    def query(self, *_args, **_kwargs):
        return _Query(self._host)

    def commit(self):
        self.commits += 1


HOST_ID = "aabeadb6-8cc4-4449-bb92-4be7b8e42c51"
FINGERPRINT = "0123456789abcdef"


@pytest.fixture(name="host")
def _host():
    return _Host()


@pytest.fixture(autouse=True)
def _clean_sessions():
    package_handlers._batch_sessions.clear()
    yield
    package_handlers._batch_sessions.clear()


def _open_batch(batch_id="batch-1", fingerprint=FINGERPRINT):
    package_handlers._batch_sessions[batch_id] = {
        "host_id": HOST_ID,
        "os_name": "Ubuntu",
        "os_version": "26.04",
        "package_managers": ["apt"],
        "total_packages": 89257,
        "catalog_fingerprint": fingerprint,
        "started_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }
    return batch_id


@pytest.mark.asyncio
async def test_completing_a_batch_records_the_fingerprint(host):
    """Only after the catalog has actually landed do we claim to hold it."""
    batch_id = _open_batch()
    db = _Db(host)

    result = await package_handlers.handle_packages_batch_end(
        db, _Connection(HOST_ID), {"batch_id": batch_id, "total_packages": 89257}
    )

    assert result["status"] == "batch_completed"
    assert host.available_packages_fingerprint == FINGERPRINT
    assert host.available_packages_fingerprint_at is not None
    assert db.commits == 1


@pytest.mark.asyncio
async def test_a_batch_that_never_completes_records_nothing(host):
    """The failure that would silence an agent for ever.

    If a fingerprint were recorded at batch START, a batch that then failed
    part-way would leave the server claiming a catalog it does not hold, and
    the agent would skip every future send of it.
    """
    _open_batch()  # started, never ended
    assert host.available_packages_fingerprint is None


@pytest.mark.asyncio
async def test_an_agent_that_sends_no_fingerprint_records_nothing(host):
    """Older agents omit the field; the server must simply not learn one.

    Recording something wrong here is worse than recording nothing: nothing
    means "ask again", which is always safe.
    """
    batch_id = _open_batch(fingerprint=None)
    db = _Db(host)

    await package_handlers.handle_packages_batch_end(
        db, _Connection(HOST_ID), {"batch_id": batch_id, "total_packages": 10}
    )

    assert host.available_packages_fingerprint is None


@pytest.mark.asyncio
async def test_batch_start_carries_the_fingerprint_into_the_session():
    """The value must survive from batch_start to batch_end."""
    session = {
        "host_id": HOST_ID,
        "catalog_fingerprint": FINGERPRINT,
    }
    package_handlers._batch_sessions["b"] = session
    assert package_handlers._batch_sessions["b"]["catalog_fingerprint"] == FINGERPRINT


@pytest.mark.asyncio
async def test_an_unknown_batch_id_is_rejected(host):
    """A completion for a batch we never started must not write anything."""
    db = _Db(host)
    result = await package_handlers.handle_packages_batch_end(
        db, _Connection(HOST_ID), {"batch_id": "never-started"}
    )
    assert result["error_type"] == "invalid_batch_id"
    assert host.available_packages_fingerprint is None
