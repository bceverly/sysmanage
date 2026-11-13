# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy token rotation (25.5 exit criteria, 2026-11-13): a host's
next token is granted on the storage host beside the current one, and the
host is told it may switch only once the storage host has acknowledged that
grant -- so it never uses a token the proxy would refuse."""

# pylint: disable=redefined-outer-name,unused-argument

from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_results as results
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    sent,
)
from tests.test_backup_proxy_cert import _on_proxy

OLD, NEW = "a" * 64, "b" * 64


def _ack(session, run):
    run.status = "ok"
    results._acknowledge(session, run)  # pylint: disable=protected-access
    session.commit()


def _hashes(sent):
    return sent[-1][2]["target"]["proxy"]["grants"][0]["token_sha256"]


def test_a_next_token_is_granted_and_released_only_once_the_storage_host_has_it(
    session, sent
):
    s = _on_proxy(session)
    s.policy.proxy_token_sha256, s.policy.proxy_token_sha256_old = OLD, None
    session.commit()

    # The host reports a next token: granted beside the current one.
    assert proxy.store_tokens(s.policy, {"proxy_tokens": {"current": OLD, "next": NEW}})
    s.policy.config_version += 1
    session.commit()
    version = s.policy.config_version
    storage = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert set(_hashes(sent)) == {OLD, NEW}
    host = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    # The storage host has not acknowledged it yet: nothing granted to switch to.
    assert NEW not in sent[-1][2]["target"]["proxy"]["granted"]

    _ack(session, host)
    assert s.policy.config_version == version  # waits for the storage host
    _ack(session, storage)
    # Both sides current and the grant holds NEW: the host is told again.
    assert s.policy.config_version == version + 1
    jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    assert NEW in sent[-1][2]["target"]["proxy"]["granted"]

    # The host switches; the old hash stays until it reports the new again.
    assert proxy.store_tokens(s.policy, {"proxy_tokens": {"current": NEW}})
    assert (s.policy.proxy_token_sha256, s.policy.proxy_token_sha256_old,
            s.policy.proxy_token_sha256_next) == (NEW, OLD, None)  # fmt: skip
    assert proxy.store_tokens(s.policy, {"proxy_tokens": {"current": NEW}})
    assert (s.policy.proxy_token_sha256_old, s.policy.proxy_token_sha256_next) == (
        None,
        None,
    )


def test_no_granted_key_unless_a_rotation_is_under_way(session, sent):
    """An agent too old to rotate refuses a proxy block with keys it does
    not know, and never reports a next token."""
    s = _on_proxy(session)
    s.policy.proxy_token_sha256 = OLD
    session.commit()
    jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    assert "granted" not in sent[-1][2]["target"]["proxy"]


def test_a_next_token_equal_to_the_current_or_malformed_is_ignored(session):
    s = _on_proxy(session)
    proxy.store_tokens(s.policy, {"proxy_tokens": {"current": OLD, "next": OLD}})
    assert s.policy.proxy_token_sha256_next is None
    proxy.store_tokens(s.policy, {"proxy_tokens": {"current": OLD, "next": "nothex"}})
    assert s.policy.proxy_token_sha256_next is None
