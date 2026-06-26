"""
Multi-tier federation integration tests (Phase 12 exit-gate).

Unit tests cover each federation service in isolation; these exercise the
WHOLE round-trip across the coordinator/site boundary using the REAL OSS
service layer on TWO separate databases (one coordinator, one site) with a
simulated wire transport.  They cover the three things the ROADMAP calls
out — **sync, dispatch, and offline resilience** — plus the 12.5 secret-lease
path, end to end.

This deliberately stops short of spawning two OS processes + the Pro+ Cython
engines + HTTP: the engines' tick workers are thin wrappers that call exactly
the services exercised here, and a real two-process harness is flaky and
license-gated.  The transport helpers below mirror what the site engine's
``_drain_once`` / the controller engine's push worker do on the wire.

Marked ``@pytest.mark.integration`` so the integration-tests workflow runs them.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring,redefined-outer-name

import json

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.services import federation_coordinator_service as coord_svc
from backend.services import federation_dispatch_service as dispatch_svc
from backend.services import federation_inbox_service as inbox_svc
from backend.services import federation_rollup_service as rollup_svc
from backend.services import federation_secret_lease_service as lease_svc
from backend.services import federation_secret_request_service as secret_req_svc
from backend.services import federation_site_service as site_svc
from tests.federation_crypto import enroll_site
from backend.services import federation_sync_queue_service as sync_svc

pytestmark = pytest.mark.integration


def _fresh_db():
    """An isolated in-memory DB with the full schema (one per tier)."""
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


# ---------------------------------------------------------------------
# The two-tier harness
# ---------------------------------------------------------------------


class FederationCluster:
    """A coordinator DB + a site DB joined by simulated transport.

    ``coord`` / ``site`` are live sessions.  ``transport_upstream`` /
    ``transport_downstream`` move payloads exactly as the wire protocol would,
    so a test asserts on real persisted state on both sides.
    """

    def __init__(self):
        self.coord = _fresh_db()
        self.site = _fresh_db()
        self.site_id = None  # coordinator-assigned, set at enroll()

    def enroll(self, name="alpha", url="https://alpha.example.com"):
        # Coordinator side: register + complete enrollment.
        registered, _sync, _outbound = enroll_site(self.coord, name=name, url=url)
        self.coord.commit()
        self.site_id = registered.id
        # Site side: point at the coordinator + record the assigned id.
        coord_svc.start_enrollment(
            self.site,
            coordinator_url=url,
            coordinator_tls_cert_pem="coord-cert",
        )
        coord_svc.mark_enrolled(
            self.site, site_id=self.site_id, site_tls_cert_pem="site-cert"
        )
        self.site.commit()
        return self.site_id

    # ----- site -> coordinator (the outbound drain) ---------------------

    def transport_upstream(self, *, fail=False):
        """Drain the site's sync queue into the coordinator's ingest services.

        ``fail=True`` simulates the coordinator being unreachable: nothing is
        delivered, every entry is marked failed, and the site records a failed
        sync attempt (so connection-health degrades) — exactly the offline
        path.  Returns the number of payloads delivered.
        """
        batch = sync_svc.peek_batch(self.site, limit=100)
        if fail:
            for entry in batch:
                sync_svc.mark_failed(self.site, entry.id, error="coordinator down")
            coord_svc.record_sync_attempt(self.site, success=False, error="down")
            self.site.commit()
            return 0
        delivered = 0
        for entry in batch:
            payload = json.loads(entry.payload_json)
            self._ingest(entry.payload_type, payload)
            sync_svc.mark_sent(self.site, entry.id)
            delivered += 1
        coord_svc.record_sync_attempt(self.site, success=True)
        self.coord.commit()
        self.site.commit()
        return delivered

    def _ingest(self, payload_type, p):
        if payload_type == "host_rollup":
            rollup_svc.record_host_rollup_snapshot(
                self.coord,
                site_id=self.site_id,
                host_count=int(p["host_count"]),
                active_count=int(p["active_count"]),
                os_breakdown=p.get("os_breakdown"),
            )
        elif payload_type == "compliance_rollup":
            rollup_svc.record_compliance_rollup_snapshot(
                self.coord,
                site_id=self.site_id,
                baseline=p["baseline"],
                score_percent=p.get("score_percent"),
                hosts_in_scope=int(p.get("hosts_in_scope", 0)),
                hosts_compliant=int(p.get("hosts_compliant", 0)),
                hosts_noncompliant=int(p.get("hosts_noncompliant", 0)),
            )
        elif payload_type == "vulnerability_rollup":
            rollup_svc.record_vulnerability_rollup_snapshot(
                self.coord,
                site_id=self.site_id,
                critical_count=int(p.get("critical_count", 0)),
                high_count=int(p.get("high_count", 0)),
            )
        elif payload_type == "site_metadata":
            site_svc.apply_site_metadata(self.coord, self.site_id, p)
            site_svc.record_sync(
                self.coord, self.site_id, success=True, host_count=p.get("host_count")
            )
        elif payload_type == "command_result":
            # Settle the coordinator's dispatched command from the site's result.
            target = dispatch_svc.STATUS_COMPLETED
            if p.get("status") == "failed":
                target = dispatch_svc.STATUS_FAILED
            dispatch_svc.update_command_status(
                self.coord,
                p["command_id"],
                new_status=dispatch_svc.STATUS_IN_PROGRESS,
            )
            dispatch_svc.update_command_status(
                self.coord, p["command_id"], new_status=target
            )
        elif payload_type == "secret_lease_request":
            lease_svc.record_requested_lease(
                self.coord,
                site_id=self.site_id,
                host_id=p["host_id"],
                secret_name=p["secret_name"],
                backend_role=p["backend_role"],
                kind=p["kind"],
                ttl_seconds=p.get("ttl_seconds"),
                correlation_key=p["correlation_key"],
            )
        else:  # pragma: no cover - guard
            raise AssertionError(f"unhandled payload_type {payload_type!r}")

    # ----- coordinator -> site (the push worker) ------------------------

    def push_command(self, command):
        """Mirror the coordinator push: deliver a dispatched command into the
        site's received-commands inbox."""
        inbox_svc.receive_command(
            self.site,
            command_id=command.id,
            command_type=command.command_type,
            parameters=json.loads(command.parameters_json or "{}"),
        )
        self.site.commit()


@pytest.fixture
def cluster():
    c = FederationCluster()
    c.enroll()
    yield c
    # Close the sessions AND dispose their engines — otherwise each cluster's
    # two in-memory sqlite connections are gc'd unclosed (ResourceWarning).
    for sess in (c.coord, c.site):
        bind = sess.get_bind()
        sess.close()
        bind.dispose()


# ---------------------------------------------------------------------
# Sync round-trip
# ---------------------------------------------------------------------


class TestSyncRoundTrip:
    def test_host_rollup_and_metadata_reach_the_coordinator(self, cluster):
        # Site produces a host rollup + a metadata report onto its queue.
        sync_svc.enqueue(
            cluster.site,
            payload_type="host_rollup",
            payload={
                "host_count": 12,
                "active_count": 9,
                "os_breakdown": {"Linux": 12},
            },
            dedup_key="host_rollup",
        )
        sync_svc.enqueue(
            cluster.site,
            payload_type="site_metadata",
            payload={
                "sysmanage_version": "2.4.0.0",
                "host_count": 12,
                "connection_state": "online",
                "capabilities": ["federation_site_engine"],
            },
            dedup_key="site_metadata:self",
        )
        cluster.site.commit()

        delivered = cluster.transport_upstream()
        assert delivered == 2

        # Coordinator now reflects the site's data.
        host, _compliance, _vuln = rollup_svc.get_dashboard_rollup(
            cluster.coord, cluster.site_id
        )
        assert host is not None and host.host_count == 12 and host.active_count == 9
        site_row = site_svc.get_site(cluster.coord, cluster.site_id)
        assert site_row.sysmanage_version == "2.4.0.0"
        assert site_row.last_sync_at is not None
        # The site recorded the success against its uplink.
        assert (
            coord_svc.connection_health(cluster.site)["state"] == coord_svc.CONN_ONLINE
        )

    def test_compliance_and_vuln_rollups_round_trip(self, cluster):
        sync_svc.enqueue(
            cluster.site,
            payload_type="compliance_rollup",
            payload={
                "baseline": "CIS",
                "score_percent": 64.0,
                "hosts_in_scope": 10,
                "hosts_compliant": 6,
                "hosts_noncompliant": 4,
            },
            dedup_key="compliance:CIS",
        )
        sync_svc.enqueue(
            cluster.site,
            payload_type="vulnerability_rollup",
            payload={"critical_count": 3, "high_count": 7},
            dedup_key="vuln",
        )
        cluster.site.commit()
        cluster.transport_upstream()

        report = rollup_svc.get_cross_site_report(cluster.coord, [cluster.site_id])
        row = report["sites"][0]
        assert row["worst_compliance"]["baseline"] == "CIS"
        assert row["critical_count"] == 3
        assert report["totals"]["critical_count"] == 3


# ---------------------------------------------------------------------
# Command dispatch round-trip
# ---------------------------------------------------------------------


class TestDispatchRoundTrip:
    def test_command_dispatch_settles_from_site_result(self, cluster):
        # Coordinator dispatches a command at the site.
        cmd = dispatch_svc.dispatch_command(
            cluster.coord,
            command_type="reboot",
            target_site_id=cluster.site_id,
            dispatched_by="admin",
        )
        cluster.coord.commit()
        assert cmd.status == dispatch_svc.STATUS_QUEUED_AT_SITE

        # Push it down to the site inbox.
        cluster.push_command(cmd)
        queued = inbox_svc.list_queued_commands(cluster.site)
        assert len(queued) == 1

        # Site executes + reports the result, enqueuing it upstream.
        inbox_svc.update_command_status(
            cluster.site, cmd.id, new_status=inbox_svc.CMD_STATUS_IN_PROGRESS
        )
        inbox_svc.update_command_status(
            cluster.site,
            cmd.id,
            new_status=inbox_svc.CMD_STATUS_COMPLETED,
            result={"ok": True},
        )
        sync_svc.enqueue(
            cluster.site,
            payload_type="command_result",
            payload={"command_id": str(cmd.id), "status": "completed"},
            dedup_key=f"cmd_result:{cmd.id}",
        )
        cluster.site.commit()

        # Result flows back; coordinator settles the dispatched command.
        cluster.transport_upstream()
        settled = dispatch_svc.get_command(cluster.coord, cmd.id)
        assert settled.status == dispatch_svc.STATUS_COMPLETED


# ---------------------------------------------------------------------
# Offline resilience + dedup-on-replay
# ---------------------------------------------------------------------


class TestOfflineResilience:
    def test_outage_then_replay_delivers_exactly_once(self, cluster):
        sync_svc.enqueue(
            cluster.site,
            payload_type="host_rollup",
            payload={"host_count": 5, "active_count": 5},
            dedup_key="host_rollup",
        )
        cluster.site.commit()

        # Coordinator unreachable: nothing delivered, uplink degrades, the
        # entry stays queued for replay.
        assert cluster.transport_upstream(fail=True) == 0
        assert sync_svc.queue_depth(cluster.site) == 1
        assert (
            coord_svc.connection_health(cluster.site)["state"] != coord_svc.CONN_ONLINE
        )

        # While offline the host count flaps; the SAME dedup_key replaces the
        # pending row rather than stacking a second one.
        sync_svc.enqueue(
            cluster.site,
            payload_type="host_rollup",
            payload={"host_count": 6, "active_count": 6},
            dedup_key="host_rollup",
        )
        cluster.site.commit()
        assert sync_svc.queue_depth(cluster.site) == 1  # still one, not two

        # Coordinator returns: exactly one rollup lands (the latest value),
        # the queue drains, and the uplink recovers to online.
        assert cluster.transport_upstream() == 1
        assert sync_svc.queue_depth(cluster.site) == 0
        host, _c, _v = rollup_svc.get_dashboard_rollup(cluster.coord, cluster.site_id)
        assert host.host_count == 6  # the replayed-latest value, exactly once
        assert (
            coord_svc.connection_health(cluster.site)["state"] == coord_svc.CONN_ONLINE
        )


# ---------------------------------------------------------------------
# Federation-aware secret leases (12.5)
# ---------------------------------------------------------------------


class TestSecretLeaseRoundTrip:
    def test_lease_request_reaches_coordinator_and_is_reconcilable(self, cluster):
        # Site requests a credential for one of its hosts (queued, not direct).
        key = secret_req_svc.enqueue_lease_request(
            cluster.site,
            host_id="host-1",
            secret_name="db-readonly",
            backend_role="readonly",
            kind="database",
            ttl_seconds=3600,
        )
        cluster.site.commit()

        cluster.transport_upstream()

        # Coordinator now has a pending lease the reconcile loop would issue.
        pending = lease_svc.list_pending(cluster.coord)
        assert len(pending) == 1
        assert pending[0].correlation_key == key
        assert pending[0].host_id == "host-1"

        # Issue it (master Vault) + echo the result back to the site inbox.
        lease_svc.mark_issued(
            cluster.coord, pending[0].id, vault_lease_id="vault/abc", ttl_seconds=3600
        )
        cluster.coord.commit()
        secret_req_svc.record_received_lease(
            cluster.site,
            correlation_key=key,
            host_id="host-1",
            secret_name="db-readonly",
            status="issued",
        )
        cluster.site.commit()

        undelivered = secret_req_svc.list_undelivered(cluster.site)
        assert len(undelivered) == 1 and undelivered[0].status == "issued"
