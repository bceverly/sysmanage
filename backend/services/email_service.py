# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Email service for sending emails via SMTP.
Supports various SMTP configurations including Gmail app passwords.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from backend.config import config
from backend.persistence.tenant_context import tenant_scope
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP.

    Configuration (SMTP server + sender) is resolved **lazily at send time**,
    never snapshotted at construction.  This matters for per-tenant email
    (Phase 13.1): the active tenant — bound from the request JWT, or passed
    explicitly via ``send_email(tenant_id=...)`` for background/pre-auth sends
    — governs which tenant's email config is used.  Snapshotting in
    ``__init__`` (especially for the module-level singleton, built at import
    time) would freeze the server scope forever.
    """

    def __init__(self):
        # No config snapshot here — see class docstring.
        pass

    def is_enabled(self) -> bool:
        """Check if email service is enabled.

        Respects SYSMANAGE_DISABLE_EMAIL env var to allow disabling
        email during e2e/integration tests without changing config.
        """
        if os.environ.get("SYSMANAGE_DISABLE_EMAIL"):
            return False
        return config.is_email_enabled()

    def send_email(  # pylint: disable=too-many-positional-arguments
        self,
        to_addresses: List[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """
        Send an email via SMTP.

        Args:
            to_addresses: List of recipient email addresses
            subject: Email subject
            body: Plain text email body
            html_body: Optional HTML email body
            from_address: Optional sender address (defaults to config)
            from_name: Optional sender name (defaults to config)
            tenant_id: Optional tenant whose email config to use (Phase 13.1).
                Pass this for background/pre-auth sends that run outside a
                request (where no tenant is bound from the JWT).  ``None`` uses
                the request-bound active tenant if any, else the server scope —
                the single-tenant default.

        Returns:
            True if email was sent successfully, False otherwise
        """
        # Bind the explicit tenant (no-op when None) so config resolves to the
        # right scope even outside a request — closing the gap where background
        # sends would silently use the server scope.
        with tenant_scope(tenant_id):
            return self._send_email_in_scope(
                to_addresses, subject, body, html_body, from_address, from_name
            )

    def _send_email_in_scope(  # pylint: disable=too-many-positional-arguments
        self,
        to_addresses: List[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> bool:
        """Resolve config under the current tenant scope and send."""
        if not self.is_enabled():
            logger.warning("Email service is disabled")
            return False

        if not to_addresses:
            logger.error("No recipient addresses provided")
            return False

        # Resolve config lazily under the active tenant scope (never snapshot).
        email_config = config.get_email_config()
        smtp_config = config.get_smtp_config()

        # Use configured values or override
        sender_address = from_address or email_config["from_address"]
        sender_name = from_name or email_config["from_name"]

        # Add subject prefix if configured
        subject_prefix = email_config.get("templates", {}).get("subject_prefix", "")
        if subject_prefix and not subject.startswith(subject_prefix):
            subject = f"{subject_prefix} {subject}"

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender_address}>"
            msg["To"] = ", ".join(to_addresses)

            # Add plain text part
            text_part = MIMEText(body, "plain")
            msg.attach(text_part)

            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, "html")
                msg.attach(html_part)

            # Connect to SMTP server and send
            smtp_host = smtp_config["host"]
            smtp_port = smtp_config["port"]
            smtp_username = smtp_config["username"]
            smtp_password = smtp_config["password"]
            use_tls = smtp_config["use_tls"]
            use_ssl = smtp_config["use_ssl"]
            timeout = smtp_config["timeout"]

            # Create SMTP connection
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=timeout)

            try:
                if use_tls and not use_ssl:
                    server.starttls()

                if smtp_username and smtp_password:
                    server.login(smtp_username, smtp_password)

                # Send the email
                server.send_message(msg, sender_address, to_addresses)
                logger.info(
                    "Email sent successfully to %s",
                    sanitize_log(", ".join(to_addresses)),
                )
                return True

            finally:
                server.quit()

        except Exception as e:
            logger.exception("Failed to send email: %s", e)
            return False

    def send_test_email(self, to_address: str, tenant_id: Optional[str] = None) -> bool:
        """
        Send a test email to verify SMTP configuration.

        Args:
            to_address: Email address to send test email to
            tenant_id: Optional tenant whose email config to test (Phase 13.1).

        Returns:
            True if test email was sent successfully, False otherwise
        """
        subject = "Test Email"
        body = """This is a test email from SysManage.

If you received this email, your SMTP configuration is working correctly.

--
SysManage System"""

        html_body = """<html>
<body>
<p>This is a test email from <strong>SysManage</strong>.</p>

<p>If you received this email, your SMTP configuration is working correctly.</p>

<hr>
<p><em>SysManage System</em></p>
</body>
</html>"""

        return self.send_email(
            to_addresses=[to_address],
            subject=subject,
            body=body,
            html_body=html_body,
            tenant_id=tenant_id,
        )


# Global email service instance
email_service = EmailService()
