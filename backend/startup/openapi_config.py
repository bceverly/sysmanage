"""
OpenAPI metadata — Phase 13.2 (API Completeness).

Centralises the FastAPI/OpenAPI document metadata (title, version, description,
and tag groups) so ``backend.main`` stays focused on wiring.  The description
documents the cross-cutting API conventions — versioning, authentication, and
rate limiting — that aren't visible from any single endpoint.
"""


def get_api_version() -> str:
    """Product version for the OpenAPI document.

    Mirrors ``server_info``: read the build-generated ``backend.__version__``
    and fall back to the current series if it's absent (dev checkouts).
    """
    try:
        from backend import __version__  # type: ignore  # noqa: PLC0415

        return str(__version__)
    except Exception:  # noqa: BLE001 - dev checkout without a generated version
        return "3.0.0"


API_DESCRIPTION = """
The SysManage management API.

**Versioning.** The unversioned `/api/...` surface is the canonical **v1** API.
`/api/v1/...` is an exact alias for it, so automation can pin a version while
existing clients keep using `/api/...` unchanged. `/api/v2/...` is reserved for
a future, deliberately-introduced breaking version and is not yet served.

**Authentication.** Most endpoints require a bearer credential in the
`Authorization: Bearer <credential>` header. Two credential types are accepted:

* a **JWT** issued by `POST /api/login` (short-lived, refreshable), and
* an **API key** (prefix `smk_`) created under `/api/api-keys`, for automation.
  An API key authenticates as its owning user and inherits that user's
  permissions.

**Rate limiting.** An optional per-client request limiter can be enabled by the
operator; when a client exceeds the configured budget the API responds `429`
with a `Retry-After` header. Agent comms, the health check, and WebSockets are
never limited.
""".strip()


# Tag descriptions for the major endpoint groups.  Routers tagged with names not
# listed here still appear in the document; these just add prose where it helps.
OPENAPI_TAGS = [
    {"name": "authentication", "description": "Login, token refresh, and logout."},
    {
        "name": "api-keys",
        "description": (
            "Manage long-lived API keys for programmatic/automation access. "
            "The plaintext key is shown only once, at creation."
        ),
    },
    {"name": "agent", "description": "Agent authentication and WebSocket connect."},
    {"name": "hosts", "description": "Host registration, inventory, and lifecycle."},
    {"name": "fleet", "description": "Fleet-wide status and operations."},
    {"name": "users", "description": "User account management."},
    {"name": "security", "description": "Security policy and role assignment."},
    {"name": "certificates", "description": "Client/server certificate operations."},
    {"name": "password-reset", "description": "Self-service password recovery."},
    {"name": "packages", "description": "Package inventory, search, and install."},
    {"name": "updates", "description": "Available updates and patching."},
    {"name": "secrets", "description": "Secret storage (OpenBAO-backed)."},
    {"name": "audit-log", "description": "Audit trail query and export."},
    {"name": "reports", "description": "Report generation and templates."},
    {
        "name": "pro-plus",
        "description": "Endpoints provided by licensed Professional+ engines.",
    },
]


def get_openapi_kwargs() -> dict:
    """Return the ``FastAPI(...)`` metadata kwargs for the app constructor."""
    return {
        "title": "SysManage API",
        "version": get_api_version(),
        "description": API_DESCRIPTION,
        "openapi_tags": OPENAPI_TAGS,
        "contact": {"name": "SysManage", "url": "https://sysmanage.org"},
        "license_info": {"name": "AGPL-3.0"},
    }
