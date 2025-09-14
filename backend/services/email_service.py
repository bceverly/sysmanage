"""
Email service for sending emails via SMTP.
Supports various SMTP configurations including Gmail app passwords.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional

from backend.config import config

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP."""

    def __init__(self):
        self.email_config = config.get_email_config()
        self.smtp_config = config.get_smtp_config()

    def is_enabled(self) -> bool:
        """Check if email service is enabled."""
        return config.is_email_enabled()

    def send_email(  # pylint: disable=too-many-positional-arguments
        self,
        to_addresses: List[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
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

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.is_enabled():
            logger.warning("Email service is disabled")
            return False

        if not to_addresses:
            logger.error("No recipient addresses provided")
            return False

        # Use configured values or override
        sender_address = from_address or self.email_config["from_address"]
        sender_name = from_name or self.email_config["from_name"]

        # Add subject prefix if configured
        subject_prefix = self.email_config.get("templates", {}).get(
            "subject_prefix", ""
        )
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
            smtp_host = self.smtp_config["host"]
            smtp_port = self.smtp_config["port"]
            smtp_username = self.smtp_config["username"]
            smtp_password = self.smtp_config["password"]
            use_tls = self.smtp_config["use_tls"]
            use_ssl = self.smtp_config["use_ssl"]
            timeout = self.smtp_config["timeout"]

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
                logger.info("Email sent successfully to %s", ", ".join(to_addresses))
                return True

            finally:
                server.quit()

        except Exception as e:
            logger.error("Failed to send email: %s", e)
            return False

    def send_test_email(self, to_address: str) -> bool:
        """
        Send a test email to verify SMTP configuration.

        Args:
            to_address: Email address to send test email to

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
            to_addresses=[to_address], subject=subject, body=body, html_body=html_body
        )


# Global email service instance
email_service = EmailService()
