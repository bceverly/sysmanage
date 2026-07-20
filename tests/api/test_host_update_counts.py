# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Unit tests for host management API endpoints (part 2).

Split from test_host.py:
- Host update-count functionality
- Host register tenant-routing (Phase 13.1)
"""

from backend.persistence import models


class TestHostUpdateCounts:
    """Test cases for update count functionality in host API endpoints."""

    def test_get_host_with_no_updates(self, client, session, auth_headers):
        """Test getting host with no package updates."""
        # Create a test host
        host = models.Host(
            fqdn="noupdates.example.com",
            ipv4="192.168.1.101",
            ipv6="2001:db8::2",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()

        response = client.get(f"/api/v1/host/{host.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "noupdates.example.com"
        assert data["security_updates_count"] == 0
        assert data["system_updates_count"] == 0
        assert data["total_updates_count"] == 0

    def test_get_host_with_mixed_updates(self, client, session, auth_headers):
        """Test getting host with mixed security and system updates."""
        # Create a test host
        host = models.Host(
            fqdn="mixedupdates.example.com",
            ipv4="192.168.1.102",
            ipv6="2001:db8::3",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()

        # Create various package updates
        updates = [
            # Security update only
            models.PackageUpdate(
                host_id=host.id,
                package_name="security-patch-1",
                current_version="1.0.0",
                available_version="1.0.1",
                package_manager="apt",
                update_type="security",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            # System update only
            models.PackageUpdate(
                host_id=host.id,
                package_name="kernel-update",
                current_version="5.4.0",
                available_version="5.4.1",
                package_manager="apt",
                update_type="system",
                is_security_update=False,
                is_system_update=True,
                status="available",
            ),
            # Both security and system update
            models.PackageUpdate(
                host_id=host.id,
                package_name="syspatch-001_nfs",
                current_version="not installed",
                available_version="001_nfs",
                package_manager="syspatch",
                update_type="security",
                is_security_update=True,
                is_system_update=True,
                status="available",
            ),
            # Regular application update (neither security nor system)
            models.PackageUpdate(
                host_id=host.id,
                package_name="firefox",
                current_version="91.0",
                available_version="92.0",
                package_manager="apt",
                update_type="enhancement",
                is_security_update=False,
                is_system_update=False,
                status="available",
            ),
        ]

        for update in updates:
            session.add(update)
        session.commit()

        response = client.get(f"/api/v1/host/{host.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "mixedupdates.example.com"
        assert (
            data["security_updates_count"] == 2
        )  # security-patch-1 and syspatch-001_nfs
        assert data["system_updates_count"] == 2  # kernel-update and syspatch-001_nfs
        assert data["total_updates_count"] == 4  # All 4 updates

    def test_get_hosts_list_with_update_counts(self, client, session, auth_headers):
        """Test getting hosts list with update counts included."""
        # Create multiple test hosts with different update scenarios
        host1 = models.Host(
            fqdn="host1.example.com",
            ipv4="192.168.1.10",
            ipv6="2001:db8::10",
            active=True,
        )
        host1.approval_status = "approved"

        host2 = models.Host(
            fqdn="host2.example.com",
            ipv4="192.168.1.11",
            ipv6="2001:db8::11",
            active=True,
        )
        host2.approval_status = "approved"

        session.add_all([host1, host2])
        session.commit()

        # Add updates to host1 only
        host1_updates = [
            models.PackageUpdate(
                host_id=host1.id,
                package_name="security-update",
                current_version="1.0.0",
                available_version="1.0.1",
                package_manager="apt",
                update_type="security",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            models.PackageUpdate(
                host_id=host1.id,
                package_name="system-update",
                current_version="2.0.0",
                available_version="2.0.1",
                package_manager="apt",
                update_type="system",
                is_security_update=False,
                is_system_update=True,
                status="available",
            ),
        ]

        for update in host1_updates:
            session.add(update)
        session.commit()

        response = client.get("/api/v1/hosts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

        # Find host1 and host2 in response
        host1_data = next((h for h in data if h["fqdn"] == "host1.example.com"), None)
        host2_data = next((h for h in data if h["fqdn"] == "host2.example.com"), None)

        assert host1_data is not None
        assert host2_data is not None

        # Verify host1 has update counts
        assert host1_data["security_updates_count"] == 1
        assert host1_data["system_updates_count"] == 1
        assert host1_data["total_updates_count"] == 2

        # Verify host2 has zero updates
        assert host2_data["security_updates_count"] == 0
        assert host2_data["system_updates_count"] == 0
        assert host2_data["total_updates_count"] == 0

    def test_get_host_by_fqdn_with_updates(self, client, session, auth_headers):
        """Test getting host by FQDN includes update counts."""
        # Create a test host
        host = models.Host(
            fqdn="byname.example.com",
            ipv4="192.168.1.103",
            ipv6="2001:db8::4",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()

        # Add OpenBSD syspatch updates (should be both security and system)
        syspatches = [
            models.PackageUpdate(
                host_id=host.id,
                package_name="syspatch-001_nfs",
                current_version="not installed",
                available_version="001_nfs",
                package_manager="syspatch",
                update_type="security",
                is_security_update=True,
                is_system_update=True,
                requires_reboot=True,
                source="OpenBSD base system",
                repository="syspatch",
                status="available",
            ),
            models.PackageUpdate(
                host_id=host.id,
                package_name="syspatch-002_zic",
                current_version="not installed",
                available_version="002_zic",
                package_manager="syspatch",
                update_type="security",
                is_security_update=True,
                is_system_update=True,
                requires_reboot=True,
                source="OpenBSD base system",
                repository="syspatch",
                status="available",
            ),
        ]

        for patch in syspatches:
            session.add(patch)
        session.commit()

        response = client.get(f"/api/v1/host/by_fqdn/{host.fqdn}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "byname.example.com"
        assert (
            data["security_updates_count"] == 2
        )  # Both syspatches are security updates
        assert data["system_updates_count"] == 2  # Both syspatches are system updates
        assert data["total_updates_count"] == 2  # 2 total updates

    def test_update_count_calculation_edge_cases(self, client, session, auth_headers):
        """Test edge cases in update count calculation."""
        # Create a test host
        host = models.Host(
            fqdn="edgecase.example.com",
            ipv4="192.168.1.104",
            ipv6="2001:db8::5",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()

        # Create updates with edge case scenarios
        edge_cases = [
            # Update that is neither security nor system (application update)
            models.PackageUpdate(
                host_id=host.id,
                package_name="app-update",
                current_version="1.0.0",
                available_version="1.1.0",
                package_manager="snap",
                update_type="enhancement",
                is_security_update=False,
                is_system_update=False,
                status="available",
            ),
            # Update with null/None current version (common for new installs)
            models.PackageUpdate(
                host_id=host.id,
                package_name="new-package",
                current_version=None,
                available_version="1.0.0",
                package_manager="apt",
                update_type="security",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            # Update in different status (should still be counted)
            models.PackageUpdate(
                host_id=host.id,
                package_name="status-test",
                current_version="1.0.0",
                available_version="1.0.1",
                package_manager="apt",
                update_type="system",
                is_security_update=False,
                is_system_update=True,
                status="pending",  # Different status
            ),
        ]

        for update in edge_cases:
            session.add(update)
        session.commit()

        response = client.get(f"/api/v1/host/{host.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["security_updates_count"] == 1  # Only new-package
        assert data["system_updates_count"] == 1  # Only status-test
        assert data["total_updates_count"] == 3  # All three updates

    def test_multiple_hosts_isolated_update_counts(self, client, session, auth_headers):
        """Test that update counts are properly isolated between hosts."""
        # Create multiple hosts
        hosts = []
        for i in range(3):
            host = models.Host(
                fqdn=f"isolated{i+1}.example.com",
                ipv4=f"192.168.1.{110+i}",
                ipv6=f"2001:db8::{110+i}",
                active=True,
            )
            host.approval_status = "approved"
            hosts.append(host)
            session.add(host)
        session.commit()

        # Add different numbers of updates to each host
        # Host 1: 2 security, 1 system, 4 total
        host1_updates = [
            models.PackageUpdate(
                host_id=hosts[0].id,
                package_name="sec1",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                update_type="security",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            models.PackageUpdate(
                host_id=hosts[0].id,
                package_name="sec2",
                current_version="2.0",
                available_version="2.1",
                package_manager="apt",
                update_type="security",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            models.PackageUpdate(
                host_id=hosts[0].id,
                package_name="sys1",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                update_type="system",
                is_security_update=False,
                is_system_update=True,
                status="available",
            ),
            models.PackageUpdate(
                host_id=hosts[0].id,
                package_name="app1",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                update_type="enhancement",
                is_security_update=False,
                is_system_update=False,
                status="available",
            ),
        ]

        # Host 2: 1 security, 2 system, 3 total (with overlap)
        host2_updates = [
            models.PackageUpdate(
                host_id=hosts[1].id,
                package_name="both1",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                update_type="security",
                is_security_update=True,
                is_system_update=True,
                status="available",
            ),
            models.PackageUpdate(
                host_id=hosts[1].id,
                package_name="sys2",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                update_type="system",
                is_security_update=False,
                is_system_update=True,
                status="available",
            ),
            models.PackageUpdate(
                host_id=hosts[1].id,
                package_name="app2",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                update_type="enhancement",
                is_security_update=False,
                is_system_update=False,
                status="available",
            ),
        ]

        # Host 3: No updates (should have zero counts)

        all_updates = host1_updates + host2_updates
        for update in all_updates:
            session.add(update)
        session.commit()

        # Test individual host endpoints
        expected_counts_list = [
            (2, 1, 4),  # Host 1: 2 security, 1 system, 4 total
            (1, 2, 3),  # Host 2: 1 security, 2 system, 3 total
            (0, 0, 0),  # Host 3: 0 security, 0 system, 0 total
        ]

        for host, expected_counts in zip(hosts, expected_counts_list):
            response = client.get(f"/api/v1/host/{host.id}", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["security_updates_count"] == expected_counts[0]
            assert data["system_updates_count"] == expected_counts[1]
            assert data["total_updates_count"] == expected_counts[2]

        # Test hosts list endpoint
        response = client.get("/api/v1/hosts", headers=auth_headers)
        assert response.status_code == 200
        hosts_data = response.json()
        assert len(hosts_data) == 3

        # Verify each host has correct isolated counts
        for host_data in hosts_data:
            if host_data["fqdn"] == "isolated1.example.com":
                assert host_data["security_updates_count"] == 2
                assert host_data["system_updates_count"] == 1
                assert host_data["total_updates_count"] == 4
            elif host_data["fqdn"] == "isolated2.example.com":
                assert host_data["security_updates_count"] == 1
                assert host_data["system_updates_count"] == 2
                assert host_data["total_updates_count"] == 3
            elif host_data["fqdn"] == "isolated3.example.com":
                assert host_data["security_updates_count"] == 0
                assert host_data["system_updates_count"] == 0
                assert host_data["total_updates_count"] == 0


class TestHostRegisterTenantRouting:
    """Phase 13.1 #2: ``/host/register`` must create the host row in the
    ENROLLING tenant's database (resolved from the enrollment token), not the
    bootstrap DB, so the per-tenant queue processor can find it.  The test
    harness runs a single in-memory engine, so we spy the routing seam: a
    resolved tenant must drive host creation through
    ``resolve_engine(PARTITION_TENANT, tenant_id)`` and record the host→tenant
    binding."""

    def test_register_routes_host_creation_to_tenant_engine(
        self, client, session, monkeypatch
    ):
        from backend.persistence import db as db_module
        from backend.persistence import partitions

        resolve_calls = []
        bind_calls = []

        def spy_resolve_engine(partition, tenant_id=None):
            resolve_calls.append((partition, tenant_id))
            # Single-engine harness: the test DB doubles as the tenant DB.
            return db_module.get_engine()

        # A valid token resolves to a tenant (the licensed engine's job).
        monkeypatch.setattr(
            "backend.api.host._resolve_enrollment_tenant",
            lambda token: "tenant-abc" if token else None,
        )
        monkeypatch.setattr(partitions, "resolve_engine", spy_resolve_engine)
        monkeypatch.setattr(
            "backend.services.host_tenant_index.bind_host_to_tenant",
            lambda host_id, tenant_id: bind_calls.append((str(host_id), tenant_id))
            or True,
        )

        resp = client.post(
            "/api/host/register",
            json={
                "active": True,
                "fqdn": "tenant-host.example.com",
                "hostname": "tenant-host",
                "ipv4": "10.0.0.5",
                "enrollment_token": "sme_fake_token",
            },
        )

        assert resp.status_code == 200
        # Core routing decision: host creation bound to the TENANT engine for
        # the token's tenant.
        assert (partitions.PARTITION_TENANT, "tenant-abc") in resolve_calls
        # And the host→tenant binding was recorded for the created host.
        assert len(bind_calls) == 1
        assert bind_calls[0][1] == "tenant-abc"
        created = (
            session.query(models.Host)
            .filter(models.Host.fqdn == "tenant-host.example.com")
            .first()
        )
        assert created is not None
        assert str(created.id) == bind_calls[0][0]

    def test_register_without_token_stays_server_scoped(
        self, client, session, monkeypatch
    ):
        """Inert path: no enrollment token → no tenant binding is recorded and
        the host is created server-scoped (unchanged single-tenant behaviour)."""
        bind_calls = []
        monkeypatch.setattr(
            "backend.services.host_tenant_index.bind_host_to_tenant",
            lambda host_id, tenant_id: bind_calls.append((host_id, tenant_id)) or True,
        )

        resp = client.post(
            "/api/host/register",
            json={
                "active": True,
                "fqdn": "server-host.example.com",
                "hostname": "server-host",
                "ipv4": "10.0.0.6",
            },
        )

        assert resp.status_code == 200
        assert bind_calls == []
        assert (
            session.query(models.Host)
            .filter(models.Host.fqdn == "server-host.example.com")
            .first()
            is not None
        )
