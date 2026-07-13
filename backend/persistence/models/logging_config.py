"""
Logging-configuration model (Phase 13.3).

Server-global logging settings stored in the database so they can be edited from
the Settings UI and pushed to agents — overriding the yaml file (DB wins).  One
row for the server itself (``scope='server'``) and one row per agent OS family
(``scope='agent'``, ``os_family`` in linux/windows/macos/bsd) holding the default
logging config for agents of that OS.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Valid scopes / OS families (validated at the API layer).
SCOPE_SERVER = "server"
SCOPE_AGENT = "agent"
OS_FAMILIES = ("linux", "windows", "macos", "bsd")

# Valid native_target values.  ``syslog`` is the LOCAL syslog daemon (OSS);
# ``syslog_remote`` forwards to a remote host:port (Phase 14.5, gated behind the
# Professional ``LOG_ROUTING`` feature).  Kept here so the API validation and the
# model stay in one place.
NATIVE_TARGETS = ("auto", "journald", "syslog", "syslog_remote", "eventlog", "none")
SYSLOG_PROTOCOLS = ("udp", "tcp")
DEFAULT_SYSLOG_PORT = 514


class LoggingSetting(Base):
    """A logging configuration row for the server or an agent OS family."""

    __tablename__ = "logging_setting"
    __table_args__ = (
        UniqueConstraint("scope", "os_family", name="uq_logging_scope_os"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scope = Column(String(20), nullable=False)  # "server" | "agent"
    os_family = Column(String(20), nullable=True)  # NULL for server; else family
    native_enabled = Column(Boolean, nullable=False, default=False)
    native_target = Column(
        String(20), nullable=False, default="auto"
    )  # auto|journald|syslog|syslog_remote|eventlog|none
    native_identifier = Column(String(255), nullable=True)
    log_level = Column(String(64), nullable=True)  # e.g. "INFO" or pipe-list
    verbosity = Column(String(20), nullable=True)  # agent: low|medium|high
    # Remote-syslog forwarding (Phase 14.5) — only meaningful when
    # native_target == 'syslog_remote'.  Professional-gated (LOG_ROUTING).
    syslog_host = Column(String(255), nullable=True)
    syslog_port = Column(Integer, nullable=True)  # default 514 when unset
    syslog_facility = Column(String(20), nullable=True)  # e.g. local0..local7, user
    syslog_protocol = Column(String(3), nullable=True)  # udp|tcp
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def to_dict(self) -> dict:
        """Serialize to the wire/UI shape."""
        return {
            "scope": self.scope,
            "os_family": self.os_family,
            "native_enabled": bool(self.native_enabled),
            "native_target": self.native_target or "auto",
            "native_identifier": self.native_identifier,
            "log_level": self.log_level,
            "verbosity": self.verbosity,
            "syslog_host": self.syslog_host,
            "syslog_port": self.syslog_port,
            "syslog_facility": self.syslog_facility,
            "syslog_protocol": self.syslog_protocol,
        }

    def __repr__(self):
        return (
            f"<LoggingSetting(scope='{self.scope}', os_family='{self.os_family}', "
            f"native_enabled={self.native_enabled}, target='{self.native_target}')>"
        )
