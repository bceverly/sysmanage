"""
Tests that EmailService resolves config under the active tenant scope at send
time (Phase 13.1) — closing the gap where background/pre-auth sends used the
server scope.
"""

import os
from unittest.mock import patch

from backend.persistence import tenant_context
from backend.services.email_service import EmailService

_SMTP = {
    "host": "localhost",
    "port": 25,
    "username": None,
    "password": None,
    "use_tls": False,
    "use_ssl": False,
    "timeout": 1,
}


def _send_capturing_tenant(tenant_id=None, outer=None):
    """Send and capture which tenant was active when config was resolved."""
    captured = {}

    def fake_smtp_config():
        captured["tenant"] = tenant_context.get_active_tenant()
        return dict(_SMTP)

    with patch("backend.services.email_service.config") as mock_config, patch(
        "backend.services.email_service.smtplib.SMTP"
    ), patch.dict(os.environ, {"SYSMANAGE_DISABLE_EMAIL": ""}, clear=False):
        mock_config.is_email_enabled.return_value = True
        mock_config.get_email_config.return_value = {
            "from_address": "a@b.com",
            "from_name": "X",
            "templates": {},
        }
        mock_config.get_smtp_config.side_effect = fake_smtp_config

        def do_send():
            return EmailService().send_email(
                ["u@x.com"], "subj", "body", tenant_id=tenant_id
            )

        if outer is not None:
            with tenant_context.tenant_scope(outer):
                ok = do_send()
        else:
            ok = do_send()
    return ok, captured.get("tenant")


def test_explicit_tenant_id_scopes_resolution():
    ok, tenant = _send_capturing_tenant(tenant_id="t-9")
    assert ok is True
    assert tenant == "t-9"


def test_no_tenant_uses_request_bound_context():
    # Simulates the request middleware having bound a tenant; send_email() with
    # no explicit tenant_id must inherit it.
    ok, tenant = _send_capturing_tenant(tenant_id=None, outer="t-req")
    assert ok is True
    assert tenant == "t-req"


def test_explicit_tenant_overrides_outer():
    ok, tenant = _send_capturing_tenant(tenant_id="t-explicit", outer="t-req")
    assert ok is True
    assert tenant == "t-explicit"


def test_no_tenant_and_no_context_is_server_scope():
    ok, tenant = _send_capturing_tenant(tenant_id=None, outer=None)
    assert ok is True
    assert tenant is None
