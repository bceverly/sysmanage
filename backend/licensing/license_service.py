"""
License service for Pro+ license management.

Handles:
- Loading license from configuration
- Phone-home to license server for validation
- Caching validated license in database
- Background task for periodic re-validation
- Offline grace period management
- Module update checking
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp
from sqlalchemy.orm import Session, sessionmaker

from backend.config.config import get_config
from backend.licensing.features import FeatureCode, ModuleCode
from backend.licensing.module_loader import module_loader
from backend.licensing.public_key import fetch_public_key, get_public_key_pem
from backend.licensing.validator import (
    LicensePayload,
    ValidationResult,
    hash_license_key,
    validate_license,
)
from backend.persistence import db as db_module
from backend.persistence.models import ProPlusLicense, ProPlusLicenseValidationLog
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.licensing.license_service")

# Default phone-home interval in hours
DEFAULT_PHONE_HOME_INTERVAL = 24

# Default module update check interval in hours
DEFAULT_MODULE_UPDATE_INTERVAL = 6

# Default modules path
DEFAULT_MODULES_PATH = "/var/lib/sysmanage/modules"


class LicenseService:
    """
    Service for managing Pro+ license validation and caching.
    """

    def __init__(self):
        self._cached_license: Optional[LicensePayload] = None
        self._license_key_hash: Optional[str] = None
        self._phone_home_task: Optional[asyncio.Task] = None
        self._module_update_task: Optional[asyncio.Task] = None
        self._initialized = False

    @property
    def cached_license(self) -> Optional[LicensePayload]:
        """Get the currently cached license payload."""
        return self._cached_license

    @property
    def is_pro_plus_active(self) -> bool:
        """Check if Pro+ is currently active."""
        return self._cached_license is not None

    @property
    def license_tier(self) -> Optional[str]:
        """Get the current license tier."""
        if self._cached_license:
            return self._cached_license.tier.value
        return None

    def _get_license_config(self) -> dict:
        """Get license configuration from config file."""
        config = get_config()
        return config.get("license", {})

    def _get_phone_home_url(self) -> Optional[str]:
        """Get the phone-home URL from config."""
        license_config = self._get_license_config()
        return license_config.get("phone_home_url")

    def _get_phone_home_interval(self) -> int:
        """Get the phone-home interval in hours."""
        license_config = self._get_license_config()
        return license_config.get(
            "phone_home_interval_hours", DEFAULT_PHONE_HOME_INTERVAL
        )

    def _get_modules_path(self) -> str:
        """Get the path for storing downloaded modules."""
        license_config = self._get_license_config()
        return license_config.get("modules_path", DEFAULT_MODULES_PATH)

    def _get_module_update_interval(self) -> int:
        """Get the module update check interval in hours."""
        license_config = self._get_license_config()
        return license_config.get(
            "module_update_interval_hours", DEFAULT_MODULE_UPDATE_INTERVAL
        )

    async def initialize(self) -> None:
        """
        Initialize the license service.

        This loads the license from config, validates it locally,
        and starts the phone-home background task.
        """
        if self._initialized:
            logger.debug("License service already initialized")
            return

        logger.info("Initializing license service")

        # Get license key from config
        license_config = self._get_license_config()
        license_key = license_config.get("key")

        if not license_key:
            logger.info("No license key configured - running as Community Edition")
            self._initialized = True
            return

        # Fetch public key from license server
        logger.info("Fetching public key from license server")
        public_key_pem = await get_public_key_pem()
        if not public_key_pem:
            logger.warning("Failed to fetch public key - cannot validate license")
            self._log_validation("local", "failure", "No public key available")
            self._initialized = True
            return

        # Validate the license locally
        result = validate_license(license_key, public_key_pem)
        if not result.valid:
            logger.warning("License validation failed: %s", result.error)
            self._log_validation("local", "failure", result.error)
            self._initialized = True
            return

        # Store the validated license
        self._cached_license = result.payload
        self._license_key_hash = hash_license_key(license_key)

        # Log any warnings
        if result.warning:
            logger.warning("License warning: %s", result.warning)

        # Save to database
        self._save_license_to_db()

        # Log successful validation
        self._log_validation("local", "success")

        logger.info(
            "Pro+ license activated: tier=%s, license_id=%s, expires=%s",
            result.payload.tier.value,
            result.payload.license_id,
            result.payload.expires_at.isoformat(),
        )

        # Check for module updates on startup
        await module_loader.check_and_update_on_startup()

        # Start phone-home background task
        if self._get_phone_home_url():
            self._phone_home_task = asyncio.create_task(self._phone_home_loop())

        # Start module update check background task
        if self._get_phone_home_url():
            self._module_update_task = asyncio.create_task(self._module_update_loop())

        self._initialized = True

    async def shutdown(self) -> None:
        """Shutdown the license service and cancel background tasks."""
        tasks_to_cancel = []
        if self._phone_home_task:
            self._phone_home_task.cancel()
            tasks_to_cancel.append(self._phone_home_task)
        if self._module_update_task:
            self._module_update_task.cancel()
            tasks_to_cancel.append(self._module_update_task)

        if tasks_to_cancel:
            # Use gather with return_exceptions to handle CancelledError without
            # swallowing unexpected cancellations of shutdown() itself
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        logger.info("License service shut down")

    def _save_license_to_db(self) -> None:
        """Save validated license to database."""
        if not self._cached_license:
            return

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                # Check if license already exists
                existing = (
                    session.query(ProPlusLicense)
                    .filter(
                        ProPlusLicense.license_id == self._cached_license.license_id
                    )
                    .first()
                )

                now = datetime.now(timezone.utc).replace(tzinfo=None)

                if existing:
                    # Update existing license
                    existing.license_key_hash = self._license_key_hash
                    existing.tier = self._cached_license.tier.value
                    existing.features = self._cached_license.features
                    existing.modules = self._cached_license.modules
                    existing.expires_at = self._cached_license.expires_at.replace(
                        tzinfo=None
                    )
                    existing.offline_days = self._cached_license.offline_days
                    existing.is_active = True
                    existing.updated_at = now
                else:
                    # Create new license record
                    new_license = ProPlusLicense(
                        license_key_hash=self._license_key_hash,
                        license_id=self._cached_license.license_id,
                        tier=self._cached_license.tier.value,
                        features=self._cached_license.features,
                        modules=self._cached_license.modules,
                        expires_at=self._cached_license.expires_at.replace(tzinfo=None),
                        offline_days=self._cached_license.offline_days,
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(new_license)

                session.commit()
                logger.debug("License saved to database")
            except Exception as e:
                logger.error("Failed to save license to database: %s", e)
                session.rollback()

    def _log_validation(
        self,
        validation_type: str,
        result: str,
        error_message: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Log a validation attempt to the database."""
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                log_entry = ProPlusLicenseValidationLog(
                    license_id=(
                        self._cached_license.license_id
                        if self._cached_license
                        else None
                    ),
                    validation_type=validation_type,
                    result=result,
                    error_message=error_message,
                    details=details,
                    validated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                session.add(log_entry)
                session.commit()
            except Exception as e:
                logger.error("Failed to log validation: %s", e)
                session.rollback()

    async def _phone_home_loop(self) -> None:
        """Background task for periodic phone-home validation."""
        interval_hours = self._get_phone_home_interval()
        interval_seconds = interval_hours * 3600

        # Initial delay before first phone-home (5 minutes)
        await asyncio.sleep(300)

        while True:
            try:
                await self._phone_home()
            except Exception as e:
                logger.error("Phone-home error: %s", e)

            await asyncio.sleep(interval_seconds)

    async def _module_update_loop(self) -> None:
        """Background task for periodic module update checks."""
        interval_hours = self._get_module_update_interval()
        interval_seconds = interval_hours * 3600

        # Initial delay before first check (30 minutes, since startup already checked)
        await asyncio.sleep(1800)

        while True:
            try:
                logger.debug("Running periodic module update check")
                await module_loader.check_and_update_on_startup()
            except Exception as e:
                logger.error("Module update check error: %s", e)

            await asyncio.sleep(interval_seconds)

    async def _phone_home(self) -> bool:
        """
        Phone home to license server for validation.

        Returns:
            True if validation succeeded, False otherwise
        """
        if not self._cached_license:
            return False

        phone_home_url = self._get_phone_home_url()
        if not phone_home_url:
            logger.debug("No phone-home URL configured")
            return True

        try:
            check_url = f"{phone_home_url.rstrip('/')}/v1/check"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    check_url,
                    json={
                        "license_id": self._cached_license.license_id,
                        "license_hash": self._license_key_hash,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("valid"):
                            self._update_phone_home_timestamp()
                            self._log_validation("phone_home", "success")
                            logger.info("Phone-home validation successful")
                            return True
                        else:
                            # License revoked
                            revocation_reason = data.get("reason", "Unknown")
                            logger.warning("License revoked: %s", revocation_reason)
                            self._log_validation(
                                "phone_home",
                                "failure",
                                f"License revoked: {revocation_reason}",
                            )
                            self._deactivate_license()
                            return False
                    else:
                        logger.warning("Phone-home returned status %d", response.status)
                        self._log_validation(
                            "phone_home",
                            "error",
                            f"HTTP status {response.status}",
                        )
                        return self._check_offline_grace()

        except aiohttp.ClientError as e:
            logger.warning("Phone-home network error: %s", e)
            self._log_validation("phone_home", "error", str(e))
            return self._check_offline_grace()
        except Exception as e:
            logger.error("Phone-home unexpected error: %s", e)
            self._log_validation("phone_home", "error", str(e))
            return self._check_offline_grace()

    def _update_phone_home_timestamp(self) -> None:
        """Update the last phone-home timestamp in database."""
        if not self._cached_license:
            return

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                license_record = (
                    session.query(ProPlusLicense)
                    .filter(
                        ProPlusLicense.license_id == self._cached_license.license_id
                    )
                    .first()
                )
                if license_record:
                    license_record.last_phone_home_at = datetime.now(
                        timezone.utc
                    ).replace(tzinfo=None)
                    session.commit()
            except Exception as e:
                logger.error("Failed to update phone-home timestamp: %s", e)
                session.rollback()

    def _check_offline_grace(self) -> bool:
        """
        Check if we're within the offline grace period.

        Returns:
            True if still within grace period, False otherwise
        """
        if not self._cached_license:
            return False

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                license_record = (
                    session.query(ProPlusLicense)
                    .filter(
                        ProPlusLicense.license_id == self._cached_license.license_id
                    )
                    .first()
                )
                if not license_record or not license_record.last_phone_home_at:
                    # Never successfully phoned home - allow initial grace period
                    return True

                offline_days = license_record.offline_days
                grace_deadline = license_record.last_phone_home_at + timedelta(
                    days=offline_days
                )
                now = datetime.now(timezone.utc).replace(tzinfo=None)

                if now <= grace_deadline:
                    days_remaining = (grace_deadline - now).days
                    logger.info(
                        "Operating in offline mode (%d days remaining)", days_remaining
                    )
                    return True
                else:
                    logger.warning("Offline grace period expired")
                    return False

            except Exception as e:
                logger.error("Error checking offline grace: %s", e)
                return True  # Fail open during errors

    def _deactivate_license(self) -> None:
        """Deactivate the current license."""
        if not self._cached_license:
            return

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                license_record = (
                    session.query(ProPlusLicense)
                    .filter(
                        ProPlusLicense.license_id == self._cached_license.license_id
                    )
                    .first()
                )
                if license_record:
                    license_record.is_active = False
                    license_record.updated_at = datetime.now(timezone.utc).replace(
                        tzinfo=None
                    )
                    session.commit()
            except Exception as e:
                logger.error("Failed to deactivate license: %s", e)
                session.rollback()

        self._cached_license = None
        logger.warning("License deactivated")

    def has_feature(self, feature: FeatureCode) -> bool:
        """
        Check if the current license includes a feature.

        Args:
            feature: The feature to check for

        Returns:
            True if the feature is enabled
        """
        if not self._cached_license:
            return False
        return feature.value in self._cached_license.features

    def has_module(self, module: ModuleCode) -> bool:
        """
        Check if the current license includes a module.

        Args:
            module: The module to check for

        Returns:
            True if the module is available
        """
        if not self._cached_license:
            return False
        return module.value in self._cached_license.modules

    def get_license_info(self) -> Optional[dict]:
        """
        Get information about the current license.

        Returns:
            Dictionary with license info, or None if no license
        """
        if not self._cached_license:
            return None

        return {
            "license_id": self._cached_license.license_id,
            "tier": self._cached_license.tier.value,
            "features": self._cached_license.features,
            "modules": self._cached_license.modules,
            "expires_at": self._cached_license.expires_at.isoformat(),
            "customer_name": self._cached_license.customer_name,
            "parent_hosts": self._cached_license.parent_hosts,
            "child_hosts": self._cached_license.child_hosts,
        }

    async def install_license(self, license_key: str) -> ValidationResult:
        """
        Install a new license key.

        Args:
            license_key: The license key to install

        Returns:
            ValidationResult with success/failure details
        """
        # Fetch public key from license server
        public_key_pem = await get_public_key_pem()
        if not public_key_pem:
            return ValidationResult(
                valid=False, error="Failed to fetch public key from license server"
            )

        result = validate_license(license_key, public_key_pem)
        if not result.valid:
            self._log_validation("install", "failure", result.error)
            return result

        # Store the validated license
        self._cached_license = result.payload
        self._license_key_hash = hash_license_key(license_key)

        # Save to database
        self._save_license_to_db()

        # Log successful installation
        self._log_validation("install", "success")

        logger.info(
            "License installed: tier=%s, license_id=%s",
            result.payload.tier.value,
            result.payload.license_id,
        )

        # Restart phone-home task if needed
        if self._phone_home_task:
            self._phone_home_task.cancel()
        if self._get_phone_home_url():
            self._phone_home_task = asyncio.create_task(self._phone_home_loop())

        return result


# Global license service instance
license_service = LicenseService()
