"""
SysManage Pro+ Licensing Module.

This module provides license validation, feature gating, and dynamic module loading
for Pro+ features.

Components:
- public_key: Embedded ECDSA P-521 public key for license verification
- features: FeatureCode and ModuleCode enums
- validator: Local license signature validation
- license_service: Phone-home, caching, and database storage
- feature_gate: Decorators for feature and module access control
- module_loader: Download and dynamic loading of Cython modules

Note: Imports are done lazily to avoid circular import issues.
Use: from backend.licensing.license_service import license_service
"""

from backend.licensing.features import FeatureCode, ModuleCode

__all__ = [
    "FeatureCode",
    "ModuleCode",
]


def __getattr__(name):
    """Lazy import to avoid circular dependencies."""
    if name == "requires_feature":
        from backend.licensing.feature_gate import requires_feature

        return requires_feature
    elif name == "requires_module":
        from backend.licensing.feature_gate import requires_module

        return requires_module
    elif name == "license_service":
        from backend.licensing.license_service import license_service

        return license_service
    elif name == "module_loader":
        from backend.licensing.module_loader import module_loader

        return module_loader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
