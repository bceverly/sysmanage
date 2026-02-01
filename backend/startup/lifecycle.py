"""
Application lifecycle management module for the SysManage server.

This module provides the FastAPI lifespan context manager that handles
startup and shutdown events including certificate generation, heartbeat
monitoring, message processing, and discovery beacon services.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.discovery.discovery_service import discovery_beacon
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.monitoring.graylog_health_monitor import graylog_health_monitor_service
from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service
from backend.security.certificate_manager import certificate_manager
from backend.utils.verbosity_logger import get_logger
from backend.websocket.message_processor import message_processor

logger = get_logger("backend.startup.lifecycle")


@asynccontextmanager
async def lifespan(_fastapi_app: FastAPI):  # NOSONAR
    """
    Application lifespan manager to handle startup and shutdown events.
    """
    logger.info("=== FASTAPI LIFESPAN STARTUP BEGIN ===")
    logger.info("lifespan function called with app: %s", type(_fastapi_app).__name__)
    logger.info("FastAPI app instance ID: %s", id(_fastapi_app))

    heartbeat_task = None
    graylog_health_task = None
    message_processor_task = None

    try:
        # Startup: Ensure server certificates are generated
        logger.info("=== CERTIFICATE GENERATION ===")
        print(
            "About to call certificate_manager.ensure_server_certificate()",
            flush=True,
        )
        logger.info("About to call certificate_manager.ensure_server_certificate()")
        certificate_manager.ensure_server_certificate()
        logger.info(
            "certificate_manager.ensure_server_certificate() completed successfully"
        )

        # Startup: Initialize Pro+ license service
        logger.info("=== LICENSE SERVICE INITIALIZATION ===")
        logger.info("About to initialize license service")
        try:
            await license_service.initialize()
            if license_service.is_pro_plus_active:
                logger.info(
                    "Pro+ license active: tier=%s", license_service.license_tier
                )
                # Load licensed modules
                logger.info("=== PRO+ MODULE LOADING ===")
                await module_loader.initialize()
                if license_service.cached_license:
                    for module_code in license_service.cached_license.modules:
                        logger.info("Loading Pro+ module: %s", module_code)
                        try:
                            await module_loader.ensure_module_available(module_code)
                        except Exception as mod_e:
                            logger.warning(
                                "Failed to load module %s: %s", module_code, mod_e
                            )
            else:
                logger.info("Running as Community Edition (no Pro+ license)")
        except Exception as lic_e:
            logger.warning("License service initialization failed: %s", lic_e)
            logger.info("Continuing as Community Edition")

        # Startup: Start the heartbeat monitor service
        logger.info("=== HEARTBEAT MONITOR STARTUP ===")
        logger.info("About to start heartbeat monitor service")
        heartbeat_task = asyncio.create_task(heartbeat_monitor_service())
        logger.info("Heartbeat monitor task created: %s", heartbeat_task)
        logger.info("Heartbeat monitor service started successfully")

        # Startup: Start the Graylog health monitor service
        logger.info("=== GRAYLOG HEALTH MONITOR STARTUP ===")
        logger.info("About to start Graylog health monitor service")
        graylog_health_task = asyncio.create_task(graylog_health_monitor_service())
        logger.info("Graylog health monitor task created: %s", graylog_health_task)
        logger.info("Graylog health monitor service started successfully")

        # Startup: Start the message processor service
        logger.info("=== MESSAGE PROCESSOR STARTUP ===")
        logger.info("About to start message processor")

        # Get current event loop and schedule the message processor to start
        loop = asyncio.get_event_loop()
        logger.info("Got event loop: %s", loop)

        # Create the task and schedule it with the event loop
        message_processor_task = loop.create_task(message_processor.start())
        logger.info("Created message processor task: %s", message_processor_task)
        logger.info("Message processor task ID: %s", id(message_processor_task))

        # Allow the event loop to process the task creation
        logger.info("Yielding control to event loop for 0.1 seconds")
        await asyncio.sleep(0.1)  # Short yield to let task start

        # Force the event loop to process any pending tasks
        logger.info("Additional yield for 0.5 seconds to let task start")
        await asyncio.sleep(0.5)  # Give it time to actually start

        # Check task status
        logger.info("Checking message processor task status")
        logger.info("Task done: %s", message_processor_task.done())
        logger.info("Task cancelled: %s", message_processor_task.cancelled())

        if message_processor_task.done():
            print(
                "WARNING - Message processor task completed during startup",
                flush=True,
            )
            logger.warning("Message processor task completed during startup")
            try:
                result = await message_processor_task
                logger.info("Task result: %s", result)
                print(f"Task result: {result}")
            except Exception as task_e:
                logger.error(
                    "Message processor startup failed: %s", task_e, exc_info=True
                )
                print(f"Task exception: {task_e}")
                raise
        else:
            logger.info("Message processor task scheduled and running successfully")

        # Startup: Start the discovery beacon service
        logger.info("=== DISCOVERY BEACON STARTUP ===")
        logger.info("About to start discovery beacon service")
        await discovery_beacon.start_beacon_service()
        logger.info("Discovery beacon service started successfully")

        logger.info("=== ALL STARTUP TASKS COMPLETED SUCCESSFULLY ===")
        logger.info("Server is ready to accept requests")

        yield

        logger.info("=== FASTAPI LIFESPAN SHUTDOWN BEGIN ===")

    except Exception as e:
        logger.error("=== EXCEPTION IN LIFESPAN STARTUP ===")
        logger.error("Exception in lifespan startup: %s", e, exc_info=True)
        logger.error("Exception type: %s", type(e).__name__)
        logger.error("Exception args: %s", e.args)
        raise

    # Shutdown: Stop the license service
    logger.info("Stopping license service")
    try:
        await license_service.shutdown()
        logger.info("License service stopped")
    except Exception as e:
        logger.error("Error stopping license service: %s", e)

    # Shutdown: Stop the discovery beacon service
    logger.info("Stopping discovery beacon service")
    try:
        await discovery_beacon.stop_beacon_service()
        logger.info("Discovery beacon service stopped")
    except Exception as e:
        logger.error("Error stopping discovery beacon: %s", e)

    # Shutdown: Stop the message processor service
    logger.info("Stopping message processor service")
    try:
        message_processor.stop()
        if message_processor_task:
            message_processor_task.cancel()
            try:
                await message_processor_task
            except asyncio.CancelledError:
                logger.info("Message processor task cancelled successfully")
                raise
        logger.info("Message processor service stopped")
    except Exception as e:
        logger.error("Error stopping message processor: %s", e)

    # Shutdown: Cancel the Graylog health monitor service
    logger.info("Stopping Graylog health monitor service")
    try:
        if graylog_health_task:
            graylog_health_task.cancel()
            try:
                await graylog_health_task
            except asyncio.CancelledError:
                logger.info("Graylog health monitor task cancelled successfully")
                raise
        logger.info("Graylog health monitor service stopped")
    except Exception as e:
        logger.error("Error stopping Graylog health monitor: %s", e)

    # Shutdown: Cancel the heartbeat monitor service
    logger.info("Stopping heartbeat monitor service")
    try:
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                logger.info("Heartbeat monitor task cancelled successfully")
                raise
        logger.info("Heartbeat monitor service stopped")
    except Exception as e:
        logger.error("Error stopping heartbeat monitor: %s", e)

    logger.info("=== FASTAPI LIFESPAN SHUTDOWN COMPLETE ===")
