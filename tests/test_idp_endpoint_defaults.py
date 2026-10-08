# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A provider's SysManage-side addresses are filled in when left blank: they
contain its own id, which an admin creating it cannot know yet."""

import uuid
from unittest.mock import patch

from backend.api import external_idp, sso_session
from backend.persistence import models

CONSOLE = "https://sm.example.com"


def _fill(**fields):
    row = models.ExternalIdpProvider(name="p", enabled=True, **fields)
    with patch.object(sso_session, "_console_url", return_value=CONSOLE):
        external_idp._fill_endpoint_defaults(row)  # pylint: disable=protected-access
    return row


def test_an_oidc_provider_gets_its_redirect_uri():
    row = _fill(type="oidc")
    assert row.id is not None
    assert row.oidc_redirect_uri == f"{CONSOLE}/api/auth/oidc/{row.id}/callback"


def test_a_saml_provider_gets_its_acs_url_and_entity_id():
    row = _fill(type="saml")
    assert row.saml_sp_acs_url == f"{CONSOLE}/api/auth/saml/{row.id}/acs"
    assert row.saml_sp_entity_id == f"{CONSOLE}/api/auth/saml/{row.id}/metadata"


def test_a_typed_value_is_never_replaced():
    row = _fill(type="oidc", oidc_redirect_uri="https://elsewhere/cb")
    assert row.oidc_redirect_uri == "https://elsewhere/cb"


def test_an_existing_id_is_kept():
    pid = uuid.uuid4()
    row = _fill(type="oidc", id=pid)
    assert row.id == pid and str(pid) in row.oidc_redirect_uri


def test_ldap_needs_none_of_them():
    row = _fill(type="ldap")
    assert row.oidc_redirect_uri is None and row.saml_sp_acs_url is None
