# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Every route reachable without a console login, and why (Lucky 13, #7).

A route not listed here must carry an authentication dependency
(``AUTH_DEPENDENCIES``).  Adding a route here is a security decision: say
what authenticates the caller instead, or why the response is public.
"""

AUTH_DEPENDENCIES = frozenset(
    {"JWTBearer", "get_current_user", "require_authenticated_user"}
)

_SIGN_IN = "signing in: the caller has no session yet"
_AGENT = (
    "agent endpoint: authenticated by the host token / registration flow in the handler"
)
_SCIM = "SCIM: the IdP's bearer token is checked in the handler (scim._authenticate)"
_FED_STUB = (
    "federation wire protocol, unlicensed stub: answers {licensed: false}, no data, "
    "no action; the licensed engine checks the site's sync bearer token"
)
_HEALTH = "health probe for load balancers and monitoring; no data"

PUBLIC_ROUTES = {
    ("POST", "/api/v1/login"): _SIGN_IN,
    (
        "POST",
        "/api/v1/refresh",
    ): "authenticated by the refresh-token cookie in the handler",
    ("POST", "/api/auth/mfa/verify"): _SIGN_IN + " (second factor of a pending login)",
    ("POST", "/api/auth/mfa/email/request"): _SIGN_IN
    + " (second factor of a pending login)",
    ("GET", "/api/v1/server-info"): "login page needs role/version/tier before sign-in",
    (
        "GET",
        "/metrics/custom-metrics",
    ): "Prometheus scrape convention (no JWT); restrict by network -- see module docstring",
    (
        "GET",
        "/api/v1/airgap/collector/runs/{run_id}/iso-download",
    ): "short-lived download token checked in the handler",
    (
        "GET",
        "/api/v1/airgap-bundles/{bundle_id}/download-stream",
    ): "short-lived download token checked in the handler",
    (
        "GET",
        "/api/v1/federation/tls-cert",
    ): "public certificate for federation peers to pin",
    ("GET", "/api/auth/oidc/{provider_id}/start"): _SIGN_IN + " (OIDC redirect)",
    ("GET", "/api/auth/oidc/{provider_id}/callback"): _SIGN_IN
    + " (OIDC code + state verified in the handler)",
    (
        "GET",
        "/api/auth/saml/{provider_id}/metadata",
    ): "public SAML SP metadata for the IdP",
    ("GET", "/api/auth/saml/{provider_id}/start"): _SIGN_IN + " (SAML redirect)",
    ("POST", "/api/auth/saml/{provider_id}/acs"): _SIGN_IN
    + " (signed SAML assertion verified in the handler)",
    ("GET", "/api/auth/sso/providers"): "login page lists the sign-in buttons",
    ("POST", "/api/auth/login/discover"): "login page step one: an email's sign-in "
    "methods, by domain only",
    ("POST", "/api/auth/sso/session"): _SIGN_IN
    + " (one-time HttpOnly SSO hand-off cookie)",
    ("POST", "/api/scim/v2/{provider_id}/Users"): _SCIM,
    ("GET", "/api/scim/v2/{provider_id}/Users"): _SCIM,
    ("GET", "/api/scim/v2/{provider_id}/Users/{user_id}"): _SCIM,
    ("PUT", "/api/scim/v2/{provider_id}/Users/{user_id}"): _SCIM,
    ("PATCH", "/api/scim/v2/{provider_id}/Users/{user_id}"): _SCIM,
    ("DELETE", "/api/scim/v2/{provider_id}/Users/{user_id}"): _SCIM,
    ("POST", "/api/agent/auth"): _AGENT,
    ("WS", "/api/agent/connect"): _AGENT,
    ("POST", "/api/agent/installation-complete"): _AGENT,
    ("POST", "/api/agent/poll"): _AGENT,
    (
        "POST",
        "/api/host/register",
    ): "agent enrollment: creates a PENDING host an administrator must approve",
    (
        "GET",
        "/api/certificates/server-fingerprint",
    ): "public: agents pin the server certificate",
    ("GET", "/api/certificates/ca-certificate"): "public: agents trust the server's CA",
    ("POST", "/api/v1/forgot-password"): _SIGN_IN
    + " (always answers the same; rate limited)",
    ("POST", "/api/v1/reset-password"): "authenticated by the single-use reset token",
    ("GET", "/api/v1/validate-reset-token/{token}"): "checks a single-use reset token",
    (
        "GET",
        "/api/v1/invitations/validate/{token}",
    ): "checks a single-use invitation token",
    (
        "POST",
        "/api/v1/invitations/accept",
    ): "authenticated by the single-use invitation token",
    (
        "GET",
        "/api/v1/reporting/screenshots/{report_id}",
    ): "static placeholder image (escaped)",
    (
        "HEAD",
        "/api/v1/reporting/screenshots/{report_id}",
    ): "static placeholder image (escaped)",
    (
        "OPTIONS",
        "/api/v1/reporting/screenshots/{report_id}",
    ): "static placeholder image (escaped)",
    ("POST", "/api/v1/federation/sites/enrollment/{token}/complete"): _FED_STUB,
    ("POST", "/api/v1/federation/sites/{site_id}/rollups/hosts"): _FED_STUB,
    ("POST", "/api/v1/federation/sites/{site_id}/rollups/compliance"): _FED_STUB,
    ("POST", "/api/v1/federation/sites/{site_id}/rollups/vulnerabilities"): _FED_STUB,
    ("POST", "/api/v1/federation/sites/{site_id}/host-directory"): _FED_STUB,
    ("POST", "/api/v1/federation/sites/{site_id}/command-results"): _FED_STUB,
    ("POST", "/api/v1/federation/sites/{site_id}/metadata"): _FED_STUB,
    ("POST", "/api/v1/federation/sites/{site_id}/secret-lease-requests"): _FED_STUB,
    ("GET", "/"): "landing response; no data",
    ("GET", "/api/health"): _HEALTH,
    ("HEAD", "/api/health"): _HEALTH,
    ("GET", "/api/health/db"): _HEALTH,
    ("HEAD", "/api/health/db"): _HEALTH,
}
