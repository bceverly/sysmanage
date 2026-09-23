# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Inventory resolution and the engine boundary (Phase 20.1).

Two things are worth pinning here and neither is serialization.

The first is that an inventory RESOLVES rather than stores. A tag that gains a
host must gain a target, and the failure mode if it does not is silent: the
job succeeds, having simply missed machines.

The second is what happens when the licensed module is absent. Every fallback
in this module points the same way -- do LESS, never more -- because the
alternative to a bounded release is the unbounded burst fleet jobs exist to
replace, and a server that loses its license mid-job must stop dispatching
rather than quietly revert to it.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from backend.services import config_mgmt_fleet as fleet

INV = uuid.UUID("55555555-5555-4555-8555-555555555555")
H1 = uuid.UUID("11111111-1111-4111-8111-111111111111")
H2 = uuid.UUID("22222222-2222-4222-8222-222222222222")


class _Engine:
    """Stands in for the Pro+ module, answering only what is asked of it."""

    def __init__(self, selectors=None):
        self._selectors = selectors or {
            "all_hosts": False,
            "host_ids": [],
            "tag_ids": [],
            "site_ids": [],
        }

    def inventory_selectors(self, _inventory, _members):
        return self._selectors

    def clamp_concurrency(self, value):
        return 20 if value is None else int(value)

    def clamp_timeout(self, value):
        return value

    def next_batch_size(self, concurrency, in_flight, pending):
        return max(0, min(pending, concurrency - in_flight))

    def job_status_after(self, *_a, **_k):
        return "running"

    def job_is_terminal(self, status):
        return status in ("completed", "failed", "canceled")


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def filter(self, *a, **_k):
        self.filters.extend(a)
        return self

    def join(self, *_a, **_k):
        return self

    def subquery(self):
        return SimpleNamespace(c=SimpleNamespace(host_id=None))

    def all(self):
        return list(self.rows)

    def count(self):
        return len(self.rows)


class _Session:
    """Records the filters a resolution builds, without executing SQL."""

    def __init__(self, hosts=None, members=None):
        self.hosts = hosts or []
        self.members = members or []
        self.queries = []

    def query(self, entity, *_rest):
        name = getattr(entity, "__name__", str(entity))
        rows = {
            "Host": self.hosts,
            "ConfigInventoryMember": self.members,
            "ConfigJobTarget": [],
        }.get(name, [])
        query = _Query(rows)
        self.queries.append((name, query))
        return query


def host(host_id=H1, fqdn="a.invalid"):
    return SimpleNamespace(id=host_id, fqdn=fqdn, active=True, site_id=None)


def inventory(all_hosts=False, name="web tier"):
    return SimpleNamespace(
        id=INV,
        name=name,
        description=None,
        all_hosts=all_hosts,
        created_by="op",
        updated_by="op",
        created_at=None,
        updated_at=None,
    )


class TestResolutionWithoutTheEngine:
    def test_an_unlicensed_server_resolves_to_no_hosts(self):
        # Fail closed. Resolving to "everything" without the module that owns
        # the selection rules would dispatch at a fleet nobody selected.
        with patch.object(fleet.shim, "engine_module", lambda: None):
            assert fleet.resolve_hosts(_Session(hosts=[host()]), inventory()) == []

    def test_batch_size_is_zero_without_the_engine(self):
        # A server that loses its license mid-job must STOP releasing, not
        # fall back to the unbounded behavior jobs exist to replace.
        with patch.object(fleet.shim, "engine_module", lambda: None):
            assert fleet.next_batch_size(50, 0, 4000) == 0

    def test_concurrency_falls_back_to_one_not_to_the_default(self):
        # If we are guessing, guess in the direction that cannot flood a queue.
        with patch.object(fleet.shim, "engine_module", lambda: None):
            assert fleet.clamp_concurrency(500) == 1

    def test_terminal_states_are_still_recognised_without_the_engine(self):
        # Answering "not terminal" would have the runner re-walk finished jobs
        # forever.
        with patch.object(fleet.shim, "engine_module", lambda: None):
            assert fleet.job_is_terminal("completed")
            assert not fleet.job_is_terminal("running")

    def test_validation_refuses_rather_than_passes_when_unlicensed(self):
        with patch.object(fleet.shim, "engine_module", lambda: None):
            assert fleet.validate_inventory("x", True, 0) is not None
            assert fleet.validate_job_template("x", "p", "i") is not None
            assert fleet.validate_inventory_member("h", None, None) is not None


class TestResolution:
    def test_all_hosts_returns_every_active_host(self):
        engine = _Engine(
            {"all_hosts": True, "host_ids": [], "tag_ids": [], "site_ids": []}
        )
        session = _Session(hosts=[host(H1), host(H2, "b.invalid")])
        with patch.object(fleet.shim, "engine_module", lambda: engine):
            assert len(fleet.resolve_hosts(session, inventory(True))) == 2

    def test_an_inventory_selecting_nothing_returns_nothing(self):
        # Not "everything". An empty selector set is an inventory somebody has
        # not finished building, and the safe reading is zero.
        engine = _Engine()
        session = _Session(hosts=[host()])
        with patch.object(fleet.shim, "engine_module", lambda: engine):
            assert fleet.resolve_hosts(session, inventory()) == []

    def test_only_active_hosts_are_ever_selected(self):
        # Queuing for an inactive host buries the work in a queue that may
        # never drain while the operator sees it as dispatched.
        engine = _Engine(
            {"all_hosts": True, "host_ids": [], "tag_ids": [], "site_ids": []}
        )
        session = _Session(hosts=[host()])
        with patch.object(fleet.shim, "engine_module", lambda: engine):
            fleet.resolve_hosts(session, inventory(True))
        host_queries = [q for name, q in session.queries if name == "Host"]
        # The active filter is applied before any selector narrowing, so even
        # an all-hosts inventory never reaches a decommissioned machine.
        assert host_queries and host_queries[0].filters

    def test_the_host_count_is_derived_from_a_live_resolution(self):
        # Never a cached column: the number changes whenever a host is tagged,
        # retired or added, and a stale "targets 412 hosts" on a launch screen
        # is wrong in the way people only notice afterwards.
        engine = _Engine(
            {"all_hosts": True, "host_ids": [], "tag_ids": [], "site_ids": []}
        )
        session = _Session(hosts=[host(H1), host(H2)])
        with patch.object(fleet.shim, "engine_module", lambda: engine):
            assert fleet.inventory_host_count(session, inventory(True)) == 2


class TestSerialisation:
    def test_timestamps_come_back_marked_utc(self):
        # Rows are naive-UTC; a naive value renders as LOCAL time in a browser,
        # so a job that finished ten minutes ago can appear to finish later.
        from datetime import datetime, timezone

        row = inventory()
        row.created_at = datetime(2026, 8, 30, 9, 0, 0)
        out = fleet.inventory_to_dict(row)
        assert out["created_at"].tzinfo is timezone.utc

    def test_outstanding_is_derived_not_stored(self):
        # It is the only counter computable exactly from the others, and a
        # fifth column to keep in step during dispatch is a fifth to get wrong.
        job = SimpleNamespace(
            id=uuid.uuid4(),
            template_id=None,
            template_name=None,
            profile_id=None,
            profile_name="p",
            inventory_name="i",
            status="running",
            check_mode=False,
            concurrency=20,
            total_targets=100,
            succeeded_count=30,
            failed_count=5,
            skipped_count=5,
            requested_by="op",
            detail=None,
            created_at=None,
            started_at=None,
            finished_at=None,
        )
        assert fleet.job_to_dict(job)["outstanding_count"] == 60

    def test_outstanding_never_goes_negative(self):
        # Defensive: a counter that over-counts (a result arriving twice) must
        # show zero remaining, not a negative that renders as a bug.
        job = SimpleNamespace(
            id=uuid.uuid4(),
            template_id=None,
            template_name=None,
            profile_id=None,
            profile_name="p",
            inventory_name="i",
            status="completed",
            check_mode=False,
            concurrency=20,
            total_targets=1,
            succeeded_count=2,
            failed_count=0,
            skipped_count=0,
            requested_by=None,
            detail=None,
            created_at=None,
            started_at=None,
            finished_at=None,
        )
        assert fleet.job_to_dict(job)["outstanding_count"] == 0

    def test_a_target_whose_host_was_deleted_still_names_it(self):
        # host_id softens to NULL on delete; the fqdn is shadowed beside it so
        # the job's history stays readable.
        target = SimpleNamespace(
            id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            host_id=None,
            host_fqdn="retired.invalid",
            status="succeeded",
            command_id="c",
            run_id=None,
            detail=None,
            queued_at=None,
            finished_at=None,
        )
        out = fleet.target_to_dict(target)
        assert out["host_id"] is None
        assert out["host_fqdn"] == "retired.invalid"
