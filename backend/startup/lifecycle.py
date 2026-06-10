"""
Application lifecycle management module for the SysManage server.

This module provides the FastAPI lifespan context manager that handles
startup and shutdown events including certificate generation, heartbeat
monitoring, message processing, and discovery beacon services.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.proplus_routes import mount_proplus_routes
from backend.discovery.discovery_service import discovery_beacon
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.monitoring.graylog_health_monitor import graylog_health_monitor_service
from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service
from backend.persistence.db import get_db
from backend.security.certificate_manager import certificate_manager
from backend.services.email_service import email_service
from backend.utils.verbosity_logger import get_logger
from backend.websocket.message_processor import message_processor

logger = get_logger("backend.startup.lifecycle")

# Strong references to fire-and-forget background tasks.  ``asyncio`` only
# keeps a WEAK reference to a task, so a task whose handle isn't retained
# can be garbage-collected mid-flight; the done-callback discards it once
# it finishes.  (Tasks held in lifespan locals are kept alive by the
# suspended frame; the ones started here use this set instead.)
_BACKGROUND_TASKS: set = set()


def _track_background_task(task) -> None:
    """Retain a strong ref to ``task`` until it completes (GC-safe)."""
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


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
    alerting_task = None
    reporting_task = None
    audit_retention_task = None
    secrets_rotation_task = None
    cve_refresh_task = None
    automation_sched_task = None
    fleet_sched_task = None

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
                module_loader.initialize()
                if license_service.cached_license:
                    failed_modules = []
                    for module_code in license_service.cached_license.modules:
                        logger.info("Loading Pro+ module: %s", module_code)
                        try:
                            ok = await module_loader.ensure_module_available(
                                module_code
                            )
                            if ok is False:
                                failed_modules.append(module_code)
                        except Exception as mod_e:
                            logger.warning(
                                "Failed to load module %s: %s", module_code, mod_e
                            )
                            failed_modules.append(module_code)
                    # Surface licensed-but-unavailable engines as ONE loud
                    # summary instead of leaving the operator to find the
                    # individual 404 lines.  Most common cause: the license
                    # server has no build of the engine for this host's
                    # Python version (see module_loader's "ENGINE UNAVAILABLE"
                    # log).  Anything gated on these engines stays disabled.
                    if failed_modules:
                        logger.error(
                            "Pro+ ENGINES LICENSED BUT UNAVAILABLE (%d): %s — these "
                            "did not load (typically: no build for this platform/"
                            "Python on the license server); their features and any "
                            "orchestrators/ticks gated on them are DISABLED.",
                            len(failed_modules),
                            ", ".join(failed_modules),
                        )
                # Mount Pro+ routes now that modules are loaded
                logger.info("=== MOUNTING PRO+ MODULE ROUTES ===")
                proplus_results = mount_proplus_routes(_fastapi_app)
                if any(proplus_results.values()):
                    logger.info("Pro+ module routes mounted: %s", proplus_results)
                else:
                    logger.warning(
                        "No Pro+ module routes were mounted despite modules being loaded"
                    )

                # Start alerting background task if module is available
                alerting_engine = module_loader.get_module("alerting_engine")
                if alerting_engine:
                    alerting_info = alerting_engine.get_module_info()
                    if alerting_info.get("provides_background_task", False):
                        logger.info("=== ALERTING ENGINE BACKGROUND TASK STARTUP ===")
                        try:
                            alerting_task = asyncio.create_task(
                                alerting_engine.start_alert_evaluator(
                                    db_maker=get_db,
                                    email_service=email_service,
                                    logger=logger,
                                )
                            )
                            logger.info("Alerting engine background task started")
                        except Exception as alert_e:
                            logger.warning(
                                "Failed to start alerting background task: %s",
                                alert_e,
                            )

                # Start reporting engine background task if module is available
                reporting_engine = module_loader.get_module("reporting_engine")
                if reporting_engine:
                    reporting_info = reporting_engine.get_module_info()
                    if reporting_info.get("provides_background_task", False):
                        logger.info("=== REPORTING ENGINE BACKGROUND TASK STARTUP ===")
                        try:
                            from backend.persistence import models

                            reporting_task = asyncio.create_task(
                                reporting_engine.start_report_scheduler(
                                    db_maker=get_db,
                                    models=models,
                                    logger=logger,
                                    email_service=email_service,
                                )
                            )
                            logger.info("Reporting engine background task started")
                        except Exception as rep_e:
                            logger.warning(
                                "Failed to start reporting background task: %s",
                                rep_e,
                            )

                # Start audit engine background task if module is available
                audit_engine = module_loader.get_module("audit_engine")
                if audit_engine:
                    audit_info = audit_engine.get_module_info()
                    if audit_info.get("provides_background_task", False):
                        logger.info("=== AUDIT ENGINE BACKGROUND TASK STARTUP ===")
                        try:
                            from backend.persistence import models

                            audit_retention_task = asyncio.create_task(
                                audit_engine.start_retention_scheduler(
                                    db_maker=get_db,
                                    models=models,
                                    logger=logger,
                                )
                            )
                            logger.info(
                                "Audit engine retention background task started"
                            )
                        except Exception as aud_e:
                            logger.warning(
                                "Failed to start audit retention "
                                "background task: %s",
                                aud_e,
                            )

                # Start secrets engine rotation scheduler if module is available
                secrets_engine = module_loader.get_module("secrets_engine")
                if secrets_engine:
                    secrets_info = secrets_engine.get_module_info()
                    if secrets_info.get("provides_background_task", False):
                        logger.info("=== SECRETS ENGINE BACKGROUND TASK STARTUP ===")
                        try:
                            from backend.persistence import models

                            secrets_rotation_task = asyncio.create_task(
                                secrets_engine.start_rotation_scheduler(
                                    db_maker=get_db,
                                    models=models,
                                    logger=logger,
                                )
                            )
                            logger.info(
                                "Secrets engine rotation background task started"
                            )
                        except Exception as sec_e:
                            logger.warning(
                                "Failed to start secrets rotation "
                                "background task: %s",
                                sec_e,
                            )

                # Start automation_engine schedule dispatcher (Phase 5)
                automation_engine = module_loader.get_module("automation_engine")
                if automation_engine:
                    auto_info = automation_engine.get_module_info()
                    if auto_info.get("provides_background_task", False):
                        logger.info(
                            "=== AUTOMATION ENGINE SCHEDULE DISPATCHER STARTUP ==="
                        )
                        try:
                            from backend.services.proplus_dispatch import (
                                queue_automation_execution,
                            )

                            automation_sched_task = asyncio.create_task(
                                automation_engine.start_schedule_dispatcher(
                                    dispatch_fn=queue_automation_execution,
                                    logger=logger,
                                )
                            )
                            logger.info("Automation engine schedule dispatcher started")
                        except Exception as auto_e:
                            logger.warning(
                                "Failed to start automation schedule dispatcher: %s",
                                auto_e,
                            )

                # Start fleet_engine schedule dispatcher (Phase 5)
                fleet_engine = module_loader.get_module("fleet_engine")
                if fleet_engine:
                    fleet_info = fleet_engine.get_module_info()
                    if fleet_info.get("provides_background_task", False):
                        logger.info("=== FLEET ENGINE SCHEDULE DISPATCHER STARTUP ===")
                        try:
                            from backend.services.proplus_dispatch import (
                                build_host_provider,
                                queue_fleet_bulk_op,
                            )

                            fleet_sched_task = asyncio.create_task(
                                fleet_engine.start_schedule_dispatcher(
                                    dispatch_fn=queue_fleet_bulk_op,
                                    host_provider=build_host_provider(get_db),
                                    logger=logger,
                                )
                            )
                            logger.info("Fleet engine schedule dispatcher started")
                        except Exception as fleet_e:
                            logger.warning(
                                "Failed to start fleet schedule dispatcher: %s",
                                fleet_e,
                            )

                # The federation role (Settings → Server Role) gates which
                # worker runs: a coordinator runs the push worker, a site
                # runs the sync worker, and a server with role 'none' runs
                # neither even when an engine is licensed/loaded.  Read once.
                try:
                    from backend.config import (  # pylint: disable=import-outside-toplevel
                        config as _fed_config,
                    )

                    _federation_role = _fed_config.get_federation_role()
                except Exception:  # pylint: disable=broad-exception-caught
                    _federation_role = "none"

                # Start federation_controller_engine outbound push
                # worker (Phase 12.10 Slice 3).  Walks pending policy
                # assignments + queued dispatched commands and posts
                # them to subordinate sites' ``/site/policies`` and
                # ``/site/commands`` endpoints using each site's
                # ``coordinator_outbound_bearer_token``.  Idles on any
                # tick where no work is pending.  Only runs when this server's
                # federation role is 'coordinator'.
                federation_controller_engine = module_loader.get_module(
                    "federation_controller_engine"
                )
                if federation_controller_engine and _federation_role == "coordinator":
                    fed_ctl_info = federation_controller_engine.get_module_info()
                    if fed_ctl_info.get("provides_background_task", False):
                        logger.info(
                            "=== FEDERATION CONTROLLER ENGINE PUSH WORKER STARTUP ==="
                        )
                        try:
                            _track_background_task(
                                asyncio.create_task(
                                    federation_controller_engine.start_federation_push_worker(
                                        db_maker=get_db,
                                        logger=logger,
                                    )
                                )
                            )
                            logger.info(
                                "Federation controller engine push worker started"
                            )
                        except Exception as fed_ctl_e:
                            logger.warning(
                                "Failed to start federation push worker: %s",
                                fed_ctl_e,
                            )

                # Start federation_site_engine outbound sync worker
                # (Phase 12.10 Slice 2).  Drains
                # ``federation_sync_queue`` to the coordinator's
                # ingest endpoints on the interval configured in the
                # singleton ``federation_coordinator`` row.  Only
                # makes outbound HTTP calls when the row is in
                # ``enrolled`` state with a bearer token; idles
                # otherwise.  Only runs when this server's federation role
                # is 'site'.
                federation_site_engine = module_loader.get_module(
                    "federation_site_engine"
                )
                if federation_site_engine and _federation_role == "site":
                    fed_site_info = federation_site_engine.get_module_info()
                    if fed_site_info.get("provides_background_task", False):
                        logger.info(
                            "=== FEDERATION SITE ENGINE SYNC WORKER STARTUP ==="
                        )
                        try:
                            _track_background_task(
                                asyncio.create_task(
                                    federation_site_engine.start_federation_sync_worker(
                                        db_maker=get_db,
                                        logger=logger,
                                    )
                                )
                            )
                            logger.info("Federation site engine sync worker started")
                        except Exception as fed_e:
                            logger.warning(
                                "Failed to start federation sync worker: %s",
                                fed_e,
                            )

                # Start air-gap collection schedule tick service if the
                # collector engine is loaded.  The /tick endpoint and
                # DB model are always available (OSS-side), but the
                # background tick driver only runs when the engine
                # whose plans the tick produces is actually present —
                # otherwise scheduled runs would queue forever with no
                # consumer.
                collector_engine_for_tick = module_loader.get_module(
                    "airgap_collector_engine"
                )
                if collector_engine_for_tick is not None:
                    logger.info("=== AIRGAP SCHEDULE TICK STARTUP ===")
                    try:
                        from backend.services.airgap_schedule_tick import (
                            airgap_schedule_tick_service,
                        )

                        airgap_tick_task = asyncio.create_task(
                            airgap_schedule_tick_service()
                        )
                        logger.info(
                            "Air-gap schedule tick task started: %s",
                            airgap_tick_task,
                        )
                    except Exception as tick_e:
                        logger.warning(
                            "Failed to start air-gap schedule tick task: %s",
                            tick_e,
                        )

                    # And the run-lifecycle orchestrator.  The
                    # schedule-tick above CREATES QUEUED runs but
                    # nothing else advances them — the run-tick is
                    # what actually walks a run through MIRRORING ->
                    # STAGING_COMPLETE -> BUILDING_ISO -> ISO_BUILT ->
                    # COMPLETE.  Same gate (collector engine present);
                    # same blast-radius treatment if it fails to start.
                    logger.info("=== AIRGAP RUN ORCHESTRATOR STARTUP ===")
                    try:
                        from backend.services.airgap_run_tick import (
                            airgap_run_tick_service,
                        )

                        airgap_run_task = asyncio.create_task(airgap_run_tick_service())
                        logger.info(
                            "Air-gap run orchestrator started: %s",
                            airgap_run_task,
                        )
                    except Exception as run_e:
                        logger.warning(
                            "Failed to start air-gap run orchestrator: %s",
                            run_e,
                        )

                # Repository-side ingestion orchestrator.  Gated on the
                # repository engine (the other half of the air gap):
                # walks an AirgapIngestionRun through mount -> keyring
                # verify -> copy -> COMPLETE.  Without it, a transferred
                # ISO POSTed to /ingest queues forever with no consumer —
                # the exact gap the collector run-tick above closed for
                # the collector side.
                repository_engine_for_tick = module_loader.get_module(
                    "airgap_repository_engine"
                )
                if repository_engine_for_tick is not None:
                    logger.info("=== AIRGAP INGEST ORCHESTRATOR STARTUP ===")
                    try:
                        from backend.services.airgap_ingest_tick import (
                            airgap_ingest_tick_service,
                        )

                        airgap_ingest_task = asyncio.create_task(
                            airgap_ingest_tick_service()
                        )
                        logger.info(
                            "Air-gap ingest orchestrator started: %s",
                            airgap_ingest_task,
                        )
                    except Exception as ingest_e:
                        logger.warning(
                            "Failed to start air-gap ingest orchestrator: %s",
                            ingest_e,
                        )

                # Start vuln_engine CVE refresh scheduler and staleness check
                vuln_engine = module_loader.get_module("vuln_engine")
                if vuln_engine:
                    vuln_info = vuln_engine.get_module_info()
                    if vuln_info.get("provides_cve_refresh", False):
                        logger.info("=== VULN ENGINE BACKGROUND TASK STARTUP ===")
                        try:
                            from backend.vulnerability.cve_refresh_service import (
                                cve_refresh_service,
                            )

                            cve_refresh_service.start_scheduler()
                            logger.info("CVE refresh scheduler started")

                            cve_refresh_task = asyncio.create_task(
                                cve_refresh_service.check_and_refresh_if_overdue(
                                    db_maker=get_db,
                                )
                            )
                            logger.info("CVE refresh staleness check task started")
                        except Exception as vuln_e:
                            logger.warning(
                                "Failed to start CVE refresh background task: %s",
                                vuln_e,
                            )
            else:
                logger.info("Running as Community Edition (no Pro+ license)")
        except Exception as lic_e:
            logger.warning("License service initialization failed: %s", lic_e)
            logger.info("Continuing as Community Edition")

        # Always ensure Pro+ stub routes are mounted for plugin API compatibility.
        # When Pro+ is active, mount_proplus_routes was already called above and
        # only adds stubs for modules that failed to load. When running as
        # Community Edition, this mounts stubs for ALL Pro+ endpoints so
        # plugin pages show "license required" instead of 422/404 errors.
        if not license_service.is_pro_plus_active:
            logger.info("=== MOUNTING PRO+ STUB ROUTES FOR COMMUNITY EDITION ===")
            mount_proplus_routes(_fastapi_app)

        # Startup: Start the heartbeat monitor service
        logger.info("=== HEARTBEAT MONITOR STARTUP ===")
        logger.info("About to start heartbeat monitor service")
        heartbeat_task = asyncio.create_task(heartbeat_monitor_service())
        logger.info("Heartbeat monitor task created: %s", heartbeat_task)
        logger.info("Heartbeat monitor service started successfully")

        # Phase 12.7: Start the GeoLite2 weekly-refresh background task.
        # Self-skipping when geo_lookup is disabled or no MaxMind license
        # key is configured — operators who don't want geo-IP just leave
        # the config defaults and the task sleeps forever without doing
        # any work.  See backend/services/geolocation_service.py for
        # the refresh + ipapi.co fallback logic.
        try:
            logger.info("=== GEOLITE2 REFRESH STARTUP ===")
            from backend.services.geolocation_service import (  # noqa: PLC0415
                geolite_refresh_service,
            )

            geolite_refresh_task = asyncio.create_task(geolite_refresh_service())
            logger.info("GeoLite2 refresh task created: %s", geolite_refresh_task)
        except Exception as geo_exc:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to start GeoLite2 refresh task: %s", geo_exc)

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
                logger.exception(
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
        logger.exception("=== EXCEPTION IN LIFESPAN STARTUP ===")
        logger.exception("Exception in lifespan startup: %s", e, exc_info=True)
        logger.exception("Exception type: %s", type(e).__name__)
        logger.exception("Exception args: %s", e.args)
        raise

    # Shutdown: Stop the license service
    logger.info("Stopping license service")
    try:
        await license_service.shutdown()
        logger.info("License service stopped")
    except Exception as e:
        logger.exception("Error stopping license service: %s", e)

    # Shutdown: Stop the discovery beacon service
    logger.info("Stopping discovery beacon service")
    try:
        await discovery_beacon.stop_beacon_service()
        logger.info("Discovery beacon service stopped")
    except Exception as e:
        logger.exception("Error stopping discovery beacon: %s", e)

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
        logger.exception("Error stopping message processor: %s", e)

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
        logger.exception("Error stopping Graylog health monitor: %s", e)

    # Shutdown: Cancel the alerting engine background task
    if alerting_task:
        logger.info("Stopping alerting engine background task")
        try:
            alerting_task.cancel()
            try:
                await alerting_task
            except asyncio.CancelledError:
                logger.info("Alerting engine task cancelled successfully")
                raise
            logger.info("Alerting engine background task stopped")
        except Exception as e:
            logger.exception("Error stopping alerting engine task: %s", e)

    # Shutdown: Cancel the reporting engine background task
    if reporting_task:
        logger.info("Stopping reporting engine background task")
        try:
            reporting_task.cancel()
            try:
                await reporting_task
            except asyncio.CancelledError:
                logger.info("Reporting engine task cancelled successfully")
                raise
            logger.info("Reporting engine background task stopped")
        except Exception as e:
            logger.exception("Error stopping reporting engine task: %s", e)

    # Shutdown: Cancel the audit engine retention background task
    if audit_retention_task:
        logger.info("Stopping audit engine retention background task")
        try:
            audit_retention_task.cancel()
            try:
                await audit_retention_task
            except asyncio.CancelledError:
                logger.info("Audit engine retention task cancelled successfully")
                raise
            logger.info("Audit engine retention background task stopped")
        except Exception as e:
            logger.exception("Error stopping audit engine retention task: %s", e)

    # Shutdown: Cancel the secrets engine rotation background task
    if secrets_rotation_task:
        logger.info("Stopping secrets engine rotation background task")
        try:
            secrets_rotation_task.cancel()
            try:
                await secrets_rotation_task
            except asyncio.CancelledError:
                logger.info("Secrets engine rotation task cancelled successfully")
                raise
            logger.info("Secrets engine rotation background task stopped")
        except Exception as e:
            logger.exception(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                "Error stopping secrets engine rotation task (%s)", type(e).__name__
            )

    # Shutdown: Cancel the CVE refresh background task
    if cve_refresh_task:
        logger.info("Stopping CVE refresh background task")
        try:
            cve_refresh_task.cancel()
            try:
                await cve_refresh_task
            except asyncio.CancelledError:
                logger.info("CVE refresh task cancelled successfully")
                raise
            logger.info("CVE refresh background task stopped")
        except Exception as e:
            logger.exception("Error stopping CVE refresh task: %s", e)

    # Shutdown: Cancel the automation engine schedule dispatcher (Phase 5)
    if automation_sched_task:
        logger.info("Stopping automation engine schedule dispatcher")
        try:
            automation_sched_task.cancel()
            try:
                await automation_sched_task
            except asyncio.CancelledError:
                logger.info("Automation schedule dispatcher cancelled successfully")
                raise
        except Exception as e:
            logger.exception("Error stopping automation schedule dispatcher: %s", e)

    # Shutdown: Cancel the fleet engine schedule dispatcher (Phase 5)
    if fleet_sched_task:
        logger.info("Stopping fleet engine schedule dispatcher")
        try:
            fleet_sched_task.cancel()
            try:
                await fleet_sched_task
            except asyncio.CancelledError:
                logger.info("Fleet schedule dispatcher cancelled successfully")
                raise
        except Exception as e:
            logger.exception("Error stopping fleet schedule dispatcher: %s", e)

    # Shutdown: Stop the CVE refresh scheduler
    try:
        from backend.vulnerability.cve_refresh_service import cve_refresh_service

        await cve_refresh_service.stop_scheduler()
        logger.info("CVE refresh scheduler stopped")
    except Exception as e:
        logger.exception("Error stopping CVE refresh scheduler: %s", e)

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
        logger.exception("Error stopping heartbeat monitor: %s", e)

    logger.info("=== FASTAPI LIFESPAN SHUTDOWN COMPLETE ===")
