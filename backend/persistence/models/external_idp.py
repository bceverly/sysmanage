# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
External Identity Provider models (Phase 10.5).

Three tables back the Pro+ ``external_idp_engine`` integration:

  external_idp_provider
      One row per configured IdP.  Holds the connection parameters for
      either an LDAP/AD directory or an OIDC provider; sensitive
      credentials (LDAP bind password, OIDC client secret) are
      Vault-stored and only the lease/secret id lives in the DB.

  idp_role_mapping
      Maps an external group (LDAP DN, OIDC group claim value) to a
      sysmanage SecurityRole.  Many-to-one — one external group can
      grant several roles.  ``default_for_unmapped=True`` flags a
      catch-all mapping that fires when no other mapping matched.

  external_idp_settings
      Singleton row of cross-provider defaults: local_account_fallback,
      max_failed_attempts.  Mirrors the singleton pattern used by
      MfaSettings + MirrorSettings.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

SINGLETON_IDP_SETTINGS_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")


class ExternalIdpProvider(Base):
    """One configured external Identity Provider."""

    __tablename__ = "external_idp_provider"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), unique=True, nullable=False)
    type = Column(String(20), nullable=False)  # 'ldap' | 'oidc' | 'saml'
    enabled = Column(Boolean, nullable=False, default=True)
    # Phase 13.1.E — per-tenant IdP. SOFT reference to ``registry_tenant.id``
    # (no FK: the registry is a different partition). NULL means a server-global
    # provider (the pre-13.1.E behaviour); a value scopes this provider to one
    # tenant, so a SaaS tenant brings its own Entra/Okta/OIDC directory.
    tenant_id = Column(GUID(), nullable=True)
    # Phase 13.1.E — JIT provisioning. When True, a successful SSO login for a
    # subject with no linked sysmanage account auto-creates the account + a grant
    # into this provider's tenant (gated by that tenant's email-domain allowlist).
    jit_provisioning = Column(Boolean, nullable=False, default=False)
    # Role granted to a JIT-created membership (grant role on registry).
    jit_default_role = Column(String(64), nullable=False, default="member")
    # LDAP/AD parameters.
    ldap_server_url = Column(String(500), nullable=True)  # ldaps://...
    ldap_bind_dn = Column(String(500), nullable=True)
    # Reference to the secret in Vault (or local dynamic-secrets table).
    # The plaintext password never lives in the DB.
    ldap_bind_password_secret_id = Column(String(255), nullable=True)
    ldap_user_search_base = Column(String(500), nullable=True)
    ldap_user_search_filter = Column(String(500), nullable=True)
    ldap_group_search_base = Column(String(500), nullable=True)
    ldap_group_search_filter = Column(String(500), nullable=True)
    ldap_tls_ca_bundle_path = Column(String(500), nullable=True)
    ldap_connection_timeout = Column(Integer, nullable=False, default=10)
    # OIDC parameters.
    oidc_issuer_url = Column(String(500), nullable=True)
    oidc_client_id = Column(String(255), nullable=True)
    oidc_client_secret_secret_id = Column(String(255), nullable=True)
    oidc_redirect_uri = Column(String(500), nullable=True)
    oidc_scopes = Column(String(500), nullable=False, default="openid profile email")
    oidc_discovery_url = Column(String(500), nullable=True)
    oidc_group_claim = Column(String(120), nullable=False, default="groups")
    # SAML 2.0 parameters (Phase 13.1.E).  The IdP signing certificate is PUBLIC
    # (used to VERIFY assertion signatures) so it is stored inline; the optional
    # SP private key is a secret and lives in Vault — only its secret id is here.
    saml_idp_entity_id = Column(String(500), nullable=True)
    saml_idp_sso_url = Column(String(500), nullable=True)
    saml_idp_x509_cert = Column(Text, nullable=True)
    saml_sp_entity_id = Column(String(500), nullable=True)
    saml_sp_acs_url = Column(String(500), nullable=True)
    saml_sp_x509_cert = Column(Text, nullable=True)
    saml_sp_private_key_secret_id = Column(String(255), nullable=True)
    # SAML attribute that carries the user's email (NameID is used when empty)
    # and the attribute carrying group memberships.
    saml_email_attribute = Column(String(255), nullable=True)
    saml_group_attribute = Column(String(255), nullable=False, default="groups")
    # Security: require the IdP to sign assertions (the safe default — never
    # accept an unsigned assertion).
    saml_want_assertions_signed = Column(Boolean, nullable=False, default=True)
    # SCIM 2.0 inbound provisioning (Phase 13.1.E).  When enabled, the IdP PUSHES
    # user create/update/deactivate to ``/api/scim/v2/{provider_id}/Users``,
    # authenticated by a bearer token whose value lives in Vault (only the secret
    # id is here).  Provisioned users land in this provider's tenant.
    scim_enabled = Column(Boolean, nullable=False, default=False)
    scim_bearer_token_secret_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "type": self.type,
            "enabled": self.enabled,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "jit_provisioning": self.jit_provisioning,
            "jit_default_role": self.jit_default_role,
            "ldap_server_url": self.ldap_server_url,
            "ldap_bind_dn": self.ldap_bind_dn,
            "ldap_bind_password_secret_id": self.ldap_bind_password_secret_id,
            "ldap_user_search_base": self.ldap_user_search_base,
            "ldap_user_search_filter": self.ldap_user_search_filter,
            "ldap_group_search_base": self.ldap_group_search_base,
            "ldap_group_search_filter": self.ldap_group_search_filter,
            "ldap_tls_ca_bundle_path": self.ldap_tls_ca_bundle_path,
            "ldap_connection_timeout": self.ldap_connection_timeout,
            "oidc_issuer_url": self.oidc_issuer_url,
            "oidc_client_id": self.oidc_client_id,
            "oidc_client_secret_secret_id": self.oidc_client_secret_secret_id,
            "oidc_redirect_uri": self.oidc_redirect_uri,
            "oidc_scopes": self.oidc_scopes,
            "oidc_discovery_url": self.oidc_discovery_url,
            "oidc_group_claim": self.oidc_group_claim,
            "saml_idp_entity_id": self.saml_idp_entity_id,
            "saml_idp_sso_url": self.saml_idp_sso_url,
            "saml_idp_x509_cert": self.saml_idp_x509_cert,
            "saml_sp_entity_id": self.saml_sp_entity_id,
            "saml_sp_acs_url": self.saml_sp_acs_url,
            "saml_sp_x509_cert": self.saml_sp_x509_cert,
            "saml_sp_private_key_secret_id": self.saml_sp_private_key_secret_id,
            "saml_email_attribute": self.saml_email_attribute,
            "saml_group_attribute": self.saml_group_attribute,
            "saml_want_assertions_signed": self.saml_want_assertions_signed,
            "scim_enabled": self.scim_enabled,
            "scim_bearer_token_secret_id": self.scim_bearer_token_secret_id,
        }


class IdpRoleMapping(Base):
    """Map an external group to a sysmanage SecurityRole."""

    __tablename__ = "idp_role_mapping"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    provider_id = Column(
        GUID(),
        ForeignKey("external_idp_provider.id", ondelete="CASCADE"),
        nullable=False,
    )
    # External group identifier — for LDAP this is a group DN or short
    # name; for OIDC it's the claim value (e.g. ``sysmanage-admins``).
    external_group = Column(String(500), nullable=False)
    # Role name (string match against SecurityRoles enum value).
    role_name = Column(String(120), nullable=False)
    # When True, this mapping fires for any user who didn't match a
    # more-specific external_group entry.  At most one default per
    # provider; OSS validates this at PUT time.
    default_for_unmapped = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "provider_id": str(self.provider_id),
            "external_group": self.external_group,
            "role_name": self.role_name,
            "default_for_unmapped": self.default_for_unmapped,
        }


class ExternalIdpSettings(Base):
    """Singleton row of cross-provider IdP defaults."""

    __tablename__ = "external_idp_settings"

    id = Column(GUID(), primary_key=True, default=lambda: SINGLETON_IDP_SETTINGS_ID)
    # When True, a user with a local password row can fall back to
    # password auth even if their external IdP authenticates them.
    # Useful for break-glass admin access.
    local_account_fallback = Column(Boolean, nullable=False, default=True)
    # After this many consecutive failed external auths in a row, the
    # user is locked the same way the local-auth lockout works.
    max_failed_attempts = Column(Integer, nullable=False, default=5)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    def to_dict(self) -> dict:
        return {
            "local_account_fallback": self.local_account_fallback,
            "max_failed_attempts": self.max_failed_attempts,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
