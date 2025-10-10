"""
Pydantic models for script management API.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, validator

from backend.i18n import _


class SavedScriptCreate(BaseModel):
    """Request model for creating a saved script."""

    name: str
    description: Optional[str] = None
    content: str
    shell_type: str
    platform: Optional[str] = None
    run_as_user: Optional[str] = None

    @validator("name")
    def validate_name(cls, value):  # pylint: disable=no-self-argument
        if not value or len(value.strip()) == 0:
            raise ValueError(_("Script name cannot be empty"))
        if len(value) > 255:
            raise ValueError(_("Script name cannot exceed 255 characters"))
        return value.strip()

    @validator("shell_type")
    def validate_shell_type(cls, value):  # pylint: disable=no-self-argument
        allowed_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]
        if value not in allowed_shells:
            raise ValueError(_("Unsupported shell type: {}").format(value))
        return value

    @validator("content")
    def validate_content(cls, value):  # pylint: disable=no-self-argument
        if not value or len(value.strip()) == 0:
            raise ValueError(_("Script content cannot be empty"))
        return value


class SavedScriptUpdate(BaseModel):
    """Request model for updating a saved script."""

    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    shell_type: Optional[str] = None
    platform: Optional[str] = None
    run_as_user: Optional[str] = None
    is_active: Optional[bool] = None

    @validator("name", pre=True)
    def validate_name(cls, value):  # pylint: disable=no-self-argument
        if value is not None and (not value or len(value.strip()) == 0):
            raise ValueError(_("Script name cannot be empty"))
        if value is not None and len(value) > 255:
            raise ValueError(_("Script name cannot exceed 255 characters"))
        return value.strip() if value else None

    @validator("shell_type")
    def validate_shell_type(cls, value):  # pylint: disable=no-self-argument
        if value is not None:
            allowed_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]
            if value not in allowed_shells:
                raise ValueError(_("Unsupported shell type: {}").format(value))
        return value

    @validator("content", pre=True)
    def validate_content(cls, value):  # pylint: disable=no-self-argument
        if value is not None and (not value or len(value.strip()) == 0):
            raise ValueError(_("Script content cannot be empty"))
        return value


class ScriptExecutionRequest(BaseModel):
    """Request model for executing a script."""

    host_id: str
    saved_script_id: Optional[str] = None
    script_name: Optional[str] = None
    script_content: Optional[str] = None
    shell_type: Optional[str] = None
    run_as_user: Optional[str] = None

    @validator("host_id", pre=True)
    def validate_host_id(cls, value):  # pylint: disable=no-self-argument
        """Convert integer host_id to string for test compatibility."""
        if isinstance(value, int):
            return str(value)
        return value

    @validator("script_content")
    def validate_script_content_or_saved_id(
        cls, value, values
    ):  # pylint: disable=no-self-argument,invalid-name
        saved_script_id = values.get("saved_script_id")
        if not saved_script_id and (not value or len(value.strip()) == 0):
            raise ValueError(
                _("Either saved_script_id or script_content must be provided")
            )
        return value

    @validator("shell_type")
    def validate_shell_type_for_adhoc(
        cls, value, values
    ):  # pylint: disable=no-self-argument
        saved_script_id = values.get("saved_script_id")
        if not saved_script_id and not value:
            raise ValueError(_("shell_type is required for ad-hoc scripts"))
        if value:
            allowed_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]
            if value not in allowed_shells:
                raise ValueError(_("Unsupported shell type: {}").format(value))
        return value


class SavedScriptResponse(BaseModel):
    """Response model for saved script data."""

    id: str
    name: str
    description: Optional[str]
    content: str
    shell_type: str
    platform: Optional[str]
    run_as_user: Optional[str]
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScriptExecutionResponse(BaseModel):
    """Response model for script execution status."""

    execution_id: str
    status: str
    message: str

    class Config:
        from_attributes = True


class ScriptExecutionLogResponse(BaseModel):
    """Response model for script execution log."""

    id: str
    host_id: str
    host_fqdn: Optional[str]
    saved_script_id: Optional[str]
    script_name: Optional[str]
    shell_type: str
    run_as_user: Optional[str]
    requested_by: str
    execution_id: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    exit_code: Optional[int]
    stdout_output: Optional[str]
    stderr_output: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScriptExecutionsResponse(BaseModel):
    """Paginated response model for script execution logs."""

    executions: List[ScriptExecutionLogResponse]
    total: int
    page: int
    pages: int
