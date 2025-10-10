"""
Secret type definitions and metadata.
"""

from fastapi import APIRouter, Depends

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _

router = APIRouter()


@router.get("/secrets/types", dependencies=[Depends(JWTBearer())])
async def get_secret_types():
    """Get available secret types."""
    return {
        "types": [
            {
                "value": "api_keys",
                "label": _("secrets.type.api_keys", "API Keys"),
                "supports_visibility": True,
                "visibility_label": _("secrets.apiProvider", "API Provider"),
                "visibility_options": [
                    {
                        "value": "github",
                        "label": _("secrets.api_provider.github", "Github"),
                    },
                    {
                        "value": "salesforce",
                        "label": _("secrets.api_provider.salesforce", "Salesforce"),
                    },
                ],
            },
            {
                "value": "database_credentials",
                "label": _("secrets.type.database_credentials", "Database Credentials"),
                "supports_visibility": True,
                "visibility_label": _("secrets.databaseEngine", "Database Engine"),
                "visibility_options": [
                    {
                        "value": "mysql",
                        "label": _("secrets.database_engine.mysql", "mysql"),
                    },
                    {
                        "value": "oracle",
                        "label": _("secrets.database_engine.oracle", "Oracle"),
                    },
                    {
                        "value": "postgresql",
                        "label": _("secrets.database_engine.postgresql", "PostgreSQL"),
                    },
                    {
                        "value": "sqlserver",
                        "label": _(
                            "secrets.database_engine.sqlserver", "Microsoft SQL Server"
                        ),
                    },
                    {
                        "value": "sqlite",
                        "label": _("secrets.database_engine.sqlite", "sqlite3"),
                    },
                ],
            },
            {
                "value": "ssh_key",
                "label": _("secrets.type.ssh_key", "SSH Key"),
                "supports_visibility": True,
                "visibility_label": _("secrets.keyType", "Key Type"),
                "visibility_options": [
                    {
                        "value": "public",
                        "label": _("secrets.key_type.public", "Public"),
                    },
                    {
                        "value": "private",
                        "label": _("secrets.key_type.private", "Private"),
                    },
                    {
                        "value": "ca",
                        "label": _("secrets.key_type.ca", "CA"),
                    },
                ],
            },
            {
                "value": "ssl_certificate",
                "label": _("secrets.type.ssl_certificate", "SSL Certificate"),
                "supports_visibility": True,
                "visibility_label": _("secrets.certificateType", "Certificate Type"),
                "visibility_options": [
                    {
                        "value": "root",
                        "label": _("secrets.certificate_type.root", "Root Certificate"),
                    },
                    {
                        "value": "intermediate",
                        "label": _(
                            "secrets.certificate_type.intermediate",
                            "Intermediate Certificate",
                        ),
                    },
                    {
                        "value": "chain",
                        "label": _(
                            "secrets.certificate_type.chain", "Chain Certificate"
                        ),
                    },
                    {
                        "value": "key_file",
                        "label": _("secrets.certificate_type.key_file", "Key File"),
                    },
                    {
                        "value": "certificate",
                        "label": _(
                            "secrets.certificate_type.certificate", "Issued Certificate"
                        ),
                    },
                ],
            },
        ]
    }
