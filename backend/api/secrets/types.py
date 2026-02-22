"""
Secret type definitions and metadata.

Returns the available secret types for the secrets management UI.
When the secrets_engine module is not loaded, returns an unlicensed response.
"""

from fastapi import APIRouter, Depends

from backend.auth.auth_bearer import JWTBearer
from backend.licensing.module_loader import module_loader

router = APIRouter()

# Standard secret types supported by SysManage
SECRET_TYPES = [
    {
        "value": "api_keys",
        "label": "API Keys",
        "supports_visibility": True,
        "visibility_label": "API Provider",
        "visibility_options": [
            {"value": "github", "label": "Github"},
            {"value": "salesforce", "label": "Salesforce"},
        ],
    },
    {
        "value": "database_credentials",
        "label": "Database Credentials",
        "supports_visibility": True,
        "visibility_label": "Database Engine",
        "visibility_options": [
            {"value": "mysql", "label": "mysql"},
            {"value": "oracle", "label": "Oracle"},
            {"value": "postgresql", "label": "PostgreSQL"},
            {"value": "sqlserver", "label": "Microsoft SQL Server"},
            {"value": "sqlite", "label": "sqlite3"},
        ],
    },
    {
        "value": "ssh_key",
        "label": "SSH Key",
        "supports_visibility": True,
        "visibility_label": "Key Type",
        "visibility_options": [
            {"value": "public", "label": "Public"},
            {"value": "private", "label": "Private"},
            {"value": "ca", "label": "CA"},
        ],
    },
    {
        "value": "ssl_certificate",
        "label": "SSL Certificate",
        "supports_visibility": True,
        "visibility_label": "Certificate Type",
        "visibility_options": [
            {"value": "root", "label": "Root Certificate"},
            {"value": "intermediate", "label": "Intermediate Certificate"},
            {"value": "chain", "label": "Chain Certificate"},
            {"value": "key_file", "label": "Key File"},
            {"value": "certificate", "label": "Issued Certificate"},
        ],
    },
]


@router.get("/secrets/types", dependencies=[Depends(JWTBearer())])
async def get_secret_types():
    """Get available secret types."""
    secrets_engine = module_loader.get_module("secrets_engine")
    if secrets_engine is None:
        return {"licensed": False, "types": []}
    return {"types": SECRET_TYPES}
