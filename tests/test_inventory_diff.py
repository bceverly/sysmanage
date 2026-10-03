# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: a software inventory report writes only what changed.

Every report deleted the host's ~600 rows and inserted them all again; at
10,000 agents that rewrite was the inbound drain's largest handler cost, on a
PostgreSQL already saturated.  Real database; the statements are counted.
"""

from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import event

from backend.api.handlers.software_package_handlers import handle_software_update
from backend.persistence.models import Host, SoftwarePackage


def _host(session):
    host = Host(id=str(uuid4()), fqdn=f"{uuid4().hex[:8]}.example.com",
                active=True, approval_status="approved")  # fmt: skip
    session.add(host)
    session.commit()
    return host


def _pkg(name, version="1.0", manager="apt"):
    return {"package_name": name, "version": version, "package_manager": manager}


class _Writes:
    """Counts INSERT and DELETE statements on software_package."""

    def __init__(self, session):
        self.engine = session.get_bind()
        self.inserts = self.deletes = 0

    def _seen(self, _conn, _cursor, statement, *_args):
        text = statement.lstrip().upper()
        if text.startswith("INSERT INTO SOFTWARE_PACKAGE"):
            self.inserts += 1
        elif text.startswith("DELETE FROM SOFTWARE_PACKAGE"):
            self.deletes += 1

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._seen)
        return self

    def __exit__(self, *_):
        event.remove(self.engine, "before_cursor_execute", self._seen)


async def _report(session, host, packages):
    connection = SimpleNamespace(host_id=host.id, hostname=host.fqdn)
    with _Writes(session) as writes:
        result = await handle_software_update(
            session, connection, {"software_packages": packages}
        )
    assert result["message_type"] == "success"
    return writes


def _rows(session, host):
    return {
        (p.package_name, p.package_version): p.id
        for p in session.query(SoftwarePackage).filter_by(host_id=host.id)
    }


async def test_an_unchanged_report_writes_nothing(session):
    host = _host(session)
    packages = [_pkg(f"pkg{i}") for i in range(50)]
    await _report(session, host, packages)
    before = _rows(session, host)
    writes = await _report(session, host, packages)
    assert (writes.inserts, writes.deletes) == (0, 0)
    assert _rows(session, host) == before  # same rows, same ids


async def test_an_upgrade_replaces_only_that_package(session):
    host = _host(session)
    packages = [_pkg(f"pkg{i}") for i in range(50)]
    await _report(session, host, packages)
    before = _rows(session, host)
    packages[7] = _pkg("pkg7", "2.0")
    writes = await _report(session, host, packages)
    assert (writes.inserts, writes.deletes) == (1, 1)
    after = _rows(session, host)
    assert ("pkg7", "1.0") not in after and ("pkg7", "2.0") in after
    assert after[("pkg8", "1.0")] == before[("pkg8", "1.0")]


async def test_removed_and_added_packages(session):
    host = _host(session)
    await _report(session, host, [_pkg("a"), _pkg("b"), _pkg("c")])
    await _report(session, host, [_pkg("a"), _pkg("c"), _pkg("d")])
    assert set(_rows(session, host)) == {("a", "1.0"), ("c", "1.0"), ("d", "1.0")}


async def test_duplicate_entries_are_kept_as_reported(session):
    host = _host(session)
    await _report(session, host, [_pkg("dup"), _pkg("dup"), _pkg("dup")])

    def count():
        return session.query(SoftwarePackage).filter_by(host_id=host.id).count()

    assert count() == 3
    await _report(session, host, [_pkg("dup")])
    assert count() == 1
    await _report(session, host, [_pkg("dup"), _pkg("dup")])
    assert count() == 2


async def test_another_hosts_inventory_is_untouched(session):
    mine, theirs = _host(session), _host(session)
    await _report(session, theirs, [_pkg("shared")])
    await _report(session, mine, [_pkg("shared")])
    await _report(session, mine, [_pkg("other")])
    assert set(_rows(session, theirs)) == {("shared", "1.0")}


async def test_an_empty_report_keeps_the_inventory(session):
    """As before: an empty list is "nothing collected", not "nothing installed"."""
    host = _host(session)
    await _report(session, host, [_pkg("a")])
    await _report(session, host, [])
    assert set(_rows(session, host)) == {("a", "1.0")}


async def test_a_large_removal_is_deleted_in_chunks(session, monkeypatch):
    from backend.api.handlers import (
        inventory_diff,
    )  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(inventory_diff, "DELETE_CHUNK", 10)
    host = _host(session)
    await _report(session, host, [_pkg(f"p{i}") for i in range(35)])
    writes = await _report(session, host, [_pkg("keep")])
    assert writes.deletes == 4
    assert set(_rows(session, host)) == {("keep", "1.0")}
