# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.7: the dashboard's host counts come from one aggregate query
(``/hosts/summary``), and the host list counts updates in the database."""

from backend.api.host_counts import update_counts_by_host
from backend.persistence import models


def _host(session, fqdn, approval="approved", status="up", reboot=False):
    host = models.Host(fqdn=fqdn, ipv4="10.0.0.1", active=True)
    host.approval_status = approval
    host.status = status
    host.reboot_required = reboot
    session.add(host)
    session.commit()
    return host


def _update(session, host, name, update_type):
    session.add(
        models.PackageUpdate(
            host_id=host.id,
            package_name=name,
            current_version="1.0",
            available_version="1.1",
            package_manager="apt",
            update_type=update_type,
            status="available",
        )
    )
    session.commit()


class TestHostsSummary:
    def test_counts(self, client, session, auth_headers):
        _host(session, "up1.example.com")
        _host(session, "up2.example.com", reboot=True)
        _host(session, "down.example.com", status="down", reboot=True)
        # Not approved: counted in the total only.
        _host(session, "pending.example.com", approval="pending", reboot=True)

        response = client.get("/api/v1/hosts/summary", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {
            "total": 4,
            "approved": 3,
            "approved_up": 2,
            "approved_down": 1,
            "reboot_required": 2,
            "package_manager_repair": 0,
            "reboot_unsafe": 0,
            "repair_hosts": [],
        }

    def test_hosts_needing_a_repair_are_counted_and_named(
        self, client, session, auth_headers
    ):
        """2026-11-19: a half-configured kernel showed only as a chip in the
        Hosts grid; the dashboard and Updates page now name such hosts --
        not safe to reboot first -- without loading the host list."""
        broken = _host(session, "a-broken.example.com")
        broken.package_manager_needs_repair = True
        broken.package_manager_repairable = True
        broken.package_manager_repair_reason = "dpkg was interrupted"
        unsafe = _host(session, "z-unsafe.example.com")
        unsafe.package_manager_needs_repair = True
        unsafe.reboot_unsafe = True
        unsafe.reboot_unsafe_reason = "Not safe to reboot: linux-image-x"
        pending = _host(session, "pending.example.com", approval="pending")
        pending.package_manager_needs_repair = True
        _host(session, "fine.example.com")
        session.commit()

        data = client.get("/api/v1/hosts/summary", headers=auth_headers).json()

        assert data["package_manager_repair"] == 2
        assert data["reboot_unsafe"] == 1
        assert [h["fqdn"] for h in data["repair_hosts"]] == [
            "z-unsafe.example.com",
            "a-broken.example.com",
        ]
        assert data["repair_hosts"][0]["reboot_unsafe_reason"].startswith(
            "Not safe to reboot"
        )

    def test_empty(self, client, auth_headers):
        response = client.get("/api/v1/hosts/summary", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_requires_authentication(self, client):
        assert client.get("/api/v1/hosts/summary").status_code in (401, 403)


class TestUpdateCountsByHost:
    def test_grouped_counts_for_every_host(self, session):
        one = _host(session, "one.example.com")
        two = _host(session, "two.example.com")
        _host(session, "none.example.com")
        for i, kind in enumerate(["security", "security", "system", "enhancement"]):
            _update(session, one, f"one-{i}", kind)
        _update(session, two, "two-0", "system")

        counts = update_counts_by_host(session)

        assert counts[one.id] == (2, 1, 4)
        assert counts[two.id] == (0, 1, 1)
        assert len(counts) == 2  # a host without updates has no row

    def test_limited_to_the_hosts_asked_for(self, session):
        one = _host(session, "a.example.com")
        two = _host(session, "b.example.com")
        _update(session, one, "a-0", "security")
        _update(session, two, "b-0", "security")

        assert set(update_counts_by_host(session, [one.id])) == {one.id}
