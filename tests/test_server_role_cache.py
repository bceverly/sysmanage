# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: the server role is read for every inbound agent message, so it
is cached briefly -- and a change through set_server_role takes effect at once."""

from unittest.mock import MagicMock, patch

from backend.services import server_config_service as svc


def _session_with_role(role):
    row = MagicMock(air_gap_role=role)
    session = MagicMock()
    session.__enter__.return_value.query.return_value.first.return_value = row
    return MagicMock(return_value=session)


def test_the_role_is_read_once_within_the_ttl():
    svc.clear_server_role_cache()
    factory = _session_with_role("repository")
    with patch.object(svc.db, "get_session_local", return_value=factory):
        assert svc.get_server_role() == "repository"
        assert svc.get_server_role() == "repository"
    assert factory.call_count == 1
    svc.clear_server_role_cache()


def test_a_failed_read_is_not_cached():
    svc.clear_server_role_cache()
    with patch.object(svc.db, "get_session_local", side_effect=RuntimeError("down")):
        assert svc.get_server_role() == svc.DEFAULT_SERVER_ROLE
    factory = _session_with_role("repository")
    with patch.object(svc.db, "get_session_local", return_value=factory):
        assert svc.get_server_role() == "repository"
    svc.clear_server_role_cache()
