# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 12.7 geo-resolution path inside ``handle_heartbeat``.

Covers:
  * geo lookup is triggered + persisted when agent reports a new public_ip
  * geo lookup is NOT triggered when public_ip is unchanged + columns already populated
  * geo lookup is SKIPPED entirely when the host has the ``no_geo_track`` tag
  * geo lookup failure leaves existing columns untouched (heartbeat ack still succeeds)
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.message_handlers_core import handle_heartbeat
from backend.services.geolocation_service import GeoResult, NO_GEO_TRACK_TAG


def _stub_geo_result():
    """Build a canned GeoResult for tests that need a successful lookup."""
    return GeoResult(
        country_code="DE",
        subdivision_code="DE-BY",
        city="Munich",
        latitude=48.1374,
        longitude=11.5755,
        source="geolite2",
    )


def _patch_host_validation():
    """Stub validate_host_id so the heartbeat path doesn't reject the test host."""
    return patch(
        "backend.utils.host_validation.validate_host_id",
        new_callable=AsyncMock,
        return_value=True,
    )


class TestHeartbeatGeoResolution:
    """Phase 12.7: heartbeat handler -> geolocation_service.lookup_ip wiring."""

    @pytest.mark.asyncio
    async def test_resolves_geo_on_new_public_ip(self, session, mock_connection):
        from backend.persistence.models import Host

        host = Host(
            fqdn="geo-new.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
            status="down",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        mock_connection.host_id = host.id
        mock_connection.hostname = host.fqdn
        mock_connection.send_message = AsyncMock()

        message_data = {
            "message_id": "msg-geo-new",
            "public_ip": "203.0.113.7",
        }

        with _patch_host_validation(), patch(
            "backend.services.geolocation_service.lookup_ip",
            return_value=_stub_geo_result(),
        ) as lookup_mock:
            await handle_heartbeat(session, mock_connection, message_data)

        # geo path fired
        lookup_mock.assert_called_once_with("203.0.113.7")

        # columns persisted on the host row
        updated = session.query(Host).filter_by(id=host.id).first()
        assert updated.public_ip == "203.0.113.7"
        assert updated.geo_country_code == "DE"
        assert updated.geo_subdivision_code == "DE-BY"
        assert updated.geo_city == "Munich"
        assert updated.geo_latitude == pytest.approx(48.1374)
        assert updated.geo_longitude == pytest.approx(11.5755)

    @pytest.mark.asyncio
    async def test_skips_lookup_when_public_ip_unchanged(
        self, session, mock_connection
    ):
        from backend.persistence.models import Host

        host = Host(
            fqdn="geo-cached.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
            status="up",
            approval_status="approved",
            public_ip="203.0.113.7",
            geo_country_code="DE",
            geo_subdivision_code="DE-BY",
            geo_city="Munich",
            geo_latitude=48.1374,
            geo_longitude=11.5755,
        )
        session.add(host)
        session.commit()

        mock_connection.host_id = host.id
        mock_connection.hostname = host.fqdn
        mock_connection.send_message = AsyncMock()

        message_data = {
            "message_id": "msg-cached",
            "public_ip": "203.0.113.7",  # same as cached
        }

        with _patch_host_validation(), patch(
            "backend.services.geolocation_service.lookup_ip"
        ) as lookup_mock:
            await handle_heartbeat(session, mock_connection, message_data)

        # No call — cache hit (IP unchanged + geo columns populated)
        lookup_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_geo_track_tag_skips_lookup_entirely(
        self, session, mock_connection
    ):
        """A host carrying the ``no_geo_track`` tag must not call the
        geo service AND must not have its public_ip column populated.
        Privacy contract: tag the host, server forgets about it."""
        from datetime import datetime, timezone
        from backend.persistence.models import Host, HostTag, Tag

        host = Host(
            fqdn="geo-optout.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
            status="up",
            approval_status="approved",
        )
        tag = Tag(
            name=NO_GEO_TRACK_TAG,
            description="privacy opt-out",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add_all([host, tag])
        session.commit()
        session.add(
            HostTag(
                host_id=host.id,
                tag_id=tag.id,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        session.commit()

        mock_connection.host_id = host.id
        mock_connection.hostname = host.fqdn
        mock_connection.send_message = AsyncMock()

        message_data = {
            "message_id": "msg-optout",
            "public_ip": "203.0.113.7",
        }

        with _patch_host_validation(), patch(
            "backend.services.geolocation_service.lookup_ip"
        ) as lookup_mock:
            await handle_heartbeat(session, mock_connection, message_data)

        # Tag opt-out fires before lookup
        lookup_mock.assert_not_called()

        # Public IP is NOT persisted — operator's tag is the contract,
        # we don't record the IP just to "have it on file".
        updated = session.query(Host).filter_by(id=host.id).first()
        assert updated.public_ip is None
        assert updated.geo_country_code is None

    @pytest.mark.asyncio
    async def test_lookup_failure_leaves_columns_intact(self, session, mock_connection):
        """A None return (rate-limit, network error, internal IP, etc.)
        from lookup_ip must NOT blank out previously-resolved geo
        columns — last-known-good wins until next successful resolve."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="geo-failover.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
            status="up",
            approval_status="approved",
            public_ip="203.0.113.7",
            geo_country_code="DE",
            geo_subdivision_code="DE-BY",
            geo_city="Munich",
            geo_latitude=48.1374,
            geo_longitude=11.5755,
        )
        session.add(host)
        session.commit()

        mock_connection.host_id = host.id
        mock_connection.hostname = host.fqdn
        mock_connection.send_message = AsyncMock()

        message_data = {
            "message_id": "msg-fail",
            "public_ip": "198.51.100.42",  # changed -> triggers re-lookup
        }

        with _patch_host_validation(), patch(
            "backend.services.geolocation_service.lookup_ip",
            return_value=None,  # simulate lookup miss
        ):
            await handle_heartbeat(session, mock_connection, message_data)

        # public_ip + resolved_at advance (we DID try); geo columns
        # stay at the prior value.
        updated = session.query(Host).filter_by(id=host.id).first()
        assert updated.public_ip == "198.51.100.42"
        assert updated.geo_country_code == "DE"
        assert updated.geo_city == "Munich"
        assert updated.geo_latitude == pytest.approx(48.1374)
