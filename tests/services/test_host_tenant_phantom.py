# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""No "No tenant" copies of a tenant's host, and a way back for an agent that
lost its host id (found on the lab's FreeBSD storage host, 2026-11-25).

What must hold:
  * a SYSTEM_INFO that does not resolve to a tenant never creates a bootstrap
    host whose name belongs to a tenant's host -- it is refused, loudly;
  * an existing bootstrap row is still updated as before, and nothing changes
    with multi-tenancy off;
  * a registration naming a host an administrator re-enrolled (no credential,
    pending) gets the host's id back -- never a token -- so the agent can claim
    it; any other existing host still gets neither.
"""

import asyncio
from unittest.mock import MagicMock, patch

from backend.api import host_registration
from backend.api import message_handlers_core as core
from backend.persistence import models

FIND = "backend.websocket.inbound_processor._find_host_in_tenant_dbs"
MT_ON = "backend.config.config.is_multitenancy_enabled"


def _tenant_host(fqdn="freebsd.example.com"):
    host = MagicMock()
    host.id = "2c756673-77a6-4223-b1eb-13dfef838f80"
    host.fqdn = fqdn
    return host


def test_a_tenants_host_gets_no_bootstrap_copy(db_session):
    session = MagicMock()
    with patch(MT_ON, return_value=True), patch(
        FIND, return_value=(_tenant_host(), session)
    ):
        refusal = host_registration.tenant_host_refusal(
            db_session, {"hostname": "freebsd.example.com"}
        )
    assert refusal["error_type"] == "host_belongs_to_tenant"
    session.close.assert_called_once()


def test_the_system_info_is_refused_before_any_host_is_made(db_session):
    connection = MagicMock()
    with patch(MT_ON, return_value=True), \
            patch(FIND, return_value=(_tenant_host(), MagicMock())), \
            patch.object(core, "_handle_system_info_impl") as impl:  # fmt: skip
        answer = asyncio.run(
            core.handle_system_info(
                db_session, connection, {"hostname": "freebsd.example.com"}
            )
        )
    assert answer["error_type"] == "host_belongs_to_tenant"
    impl.assert_not_called()
    assert (
        db_session.query(models.Host).filter_by(fqdn="freebsd.example.com").count() == 0
    )


def test_an_existing_bootstrap_host_and_a_new_name_still_pass(db_session):
    db_session.add(
        models.Host(fqdn="old.example.com", active=True, approval_status="approved")
    )
    db_session.commit()
    with patch(MT_ON, return_value=True), patch(
        FIND, return_value=(_tenant_host(), MagicMock())
    ):
        assert (
            host_registration.tenant_host_refusal(
                db_session, {"hostname": "old.example.com"}
            )
            is None
        )
    with patch(MT_ON, return_value=True), patch(FIND, return_value=(None, None)):
        assert (
            host_registration.tenant_host_refusal(
                db_session, {"hostname": "new.example.com"}
            )
            is None
        )
    with patch(MT_ON, return_value=False):
        assert (
            host_registration.tenant_host_refusal(
                db_session, {"hostname": "freebsd.example.com"}
            )
            is None
        )


def test_a_reenrolled_host_gives_its_id_back_but_no_token():
    host = MagicMock(id="2c756673-77a6-4223-b1eb-13dfef838f80", fqdn="freebsd.example.com",
                     approval_status="pending", host_token=None, requires_host_token=False,
                     registration_nonce_hash=None, active=True)  # fmt: skip
    reply = host_registration.existing_host_reply(host, None)
    assert reply["id"] == "2c756673-77a6-4223-b1eb-13dfef838f80"
    assert "host_token" not in reply and reply["approval_status"] == "pending"


def test_any_other_existing_host_gets_neither():
    for status, token in (("approved", "tok"), ("pending", "tok"), ("approved", None)):
        host = MagicMock(id="h", fqdn="x.example.com", approval_status=status, host_token=token,
                         requires_host_token=False, registration_nonce_hash=None, active=True)  # fmt: skip
        reply = host_registration.existing_host_reply(host, None)
        assert "id" not in reply and "host_token" not in reply, (status, token)
