# Security Roles Usage Guide

## Overview

The security roles system provides fine-grained permission control for SysManage users. This document explains how to use the role checking functionality in your code.

## Components

### 1. SecurityRoles Enum (`backend/security/roles.py`)

An enumeration of all 35 security roles in the system, organized by category:

- **Host Management**: `APPROVE_HOST_REGISTRATION`, `DELETE_HOST`, `VIEW_HOST_DETAILS`, etc.
- **Package Management**: `ADD_PACKAGE`, `APPLY_SOFTWARE_UPDATE`, `APPLY_HOST_OS_UPGRADE`
- **Secrets Management**: `ADD_SECRET`, `DELETE_SECRET`, `EDIT_SECRET`, etc.
- **User Management**: `ADD_USER`, `EDIT_USER`, `LOCK_USER`, `UNLOCK_USER`, `DELETE_USER`
- **Script Management**: `ADD_SCRIPT`, `DELETE_SCRIPT`, `RUN_SCRIPT`, `DELETE_SCRIPT_EXECUTION`
- **Report Management**: `VIEW_REPORT`, `GENERATE_PDF_REPORT`
- **Integration Management**: `DELETE_QUEUE_MESSAGE`, `ENABLE_GRAFANA_INTEGRATION`
- **Ubuntu Pro Management**: `ATTACH_UBUNTU_PRO`, `DETACH_UBUNTU_PRO`, `CHANGE_UBUNTU_PRO_MASTER_KEY`

### 2. User Model Methods (`backend/persistence/models/core.py`)

The User model has been enhanced with role-checking methods:

- `load_role_cache(db_session)` - Load roles into cache (call at login)
- `has_role(role)` - Check if user has a specific role
- `has_any_role(roles)` - Check if user has any of the specified roles
- `has_all_roles(roles)` - Check if user has all of the specified roles
- `get_roles()` - Get all roles the user has

### 3. Utility Functions (`backend/security/roles.py`)

- `load_user_roles(db, user_id)` - Load roles from database into cache
- `check_user_has_role(db, user_id, role)` - Direct database query for role check

## Usage Examples

### At Login Time

Load the user's roles into cache when they authenticate:

```python
from backend.persistence.models import User
from backend.persistence.db import get_db

# After authenticating the user
db = next(get_db())
user = db.query(User).filter(User.userid == email).first()

# Load role cache
user.load_role_cache(db)
```

### Checking Single Role

```python
from backend.security.roles import SecurityRoles

# Check if user can delete hosts
if user.has_role(SecurityRoles.DELETE_HOST):
    # User has permission to delete hosts
    delete_host(host_id)
else:
    raise HTTPException(status_code=403, detail="Permission denied")
```

### Checking Multiple Roles (ANY)

```python
from backend.security.roles import SecurityRoles

# Check if user can do any host service operations
if user.has_any_role([
    SecurityRoles.START_HOST_SERVICE,
    SecurityRoles.STOP_HOST_SERVICE,
    SecurityRoles.RESTART_HOST_SERVICE
]):
    # User can manage host services
    manage_service(service_name, action)
```

### Checking Multiple Roles (ALL)

```python
from backend.security.roles import SecurityRoles

# Check if user has all required roles for a complex operation
if user.has_all_roles([
    SecurityRoles.DEPLOY_SSH_KEY,
    SecurityRoles.DEPLOY_CERTIFICATE
]):
    # User can deploy both SSH keys and certificates
    deploy_credentials(host_id)
```

### Getting All User Roles

```python
# Get all roles the user has
user_roles = user.get_roles()
for role in user_roles:
    print(f"User has role: {role.value}")
```

### In FastAPI Endpoints

```python
from fastapi import APIRouter, Depends, HTTPException
from backend.auth.auth_bearer import get_current_user
from backend.security.roles import SecurityRoles
from backend.persistence.db import get_db
from backend.persistence.models import User

router = APIRouter()

@router.delete("/api/host/{host_id}")
async def delete_host(
    host_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get the user object
    user = db.query(User).filter(User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Load role cache if not already loaded
    if user._role_cache is None:
        user.load_role_cache(db)

    # Check permission
    if not user.has_role(SecurityRoles.DELETE_HOST):
        raise HTTPException(status_code=403, detail="Permission denied: DELETE_HOST role required")

    # Proceed with deletion
    # ... delete host logic ...
```

## Important Notes

1. **Admin Bypass**: Users with `is_admin=True` automatically pass all role checks
2. **Cache Loading**: `load_role_cache()` must be called before role checking methods work
3. **Performance**: Role cache is stored in memory - no database queries during permission checks
4. **Thread Safety**: Role cache is not shared between requests - load it per request if needed

## Best Practices

1. Load the role cache once at login/authentication time
2. Use the `has_role()` method for most permission checks
3. Use `has_any_role()` when user needs one of several permissions
4. Use `has_all_roles()` when user needs multiple specific permissions
5. Always check permissions before executing sensitive operations
6. Return 403 Forbidden when permission is denied

## Migration from is_admin

If you're migrating from a simple `is_admin` check:

**Before:**
```python
if not user.is_admin:
    raise HTTPException(status_code=403, detail="Admin required")
```

**After:**
```python
if not user.has_role(SecurityRoles.DELETE_HOST):
    raise HTTPException(status_code=403, detail="Permission denied")
```

Note: Admin users still bypass all checks, so existing admin functionality is preserved.
