# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Periodic driver for ``ConfigProfileAssignment`` cron schedules (Phase 20.1).

Assignments were storage-only until this existed: an operator could bind a
profile to a host, a tag or a site and give it a cron expression, and nothing
would ever fire it. This is the loop that makes an assignment mean something.

DUE-NESS IS DERIVED, NOT STORED
-------------------------------
There is no ``next_run`` column. An assignment is due when the next cron
occurrence AFTER its last apply has arrived, which is computed each tick from
``last_applied_at``. That is deliberate: a stored cursor has to be migrated
when it is added, kept correct when the cron changes, and repaired when it
drifts, and every one of those is a way for a schedule to silently stop.

It also means a schedule that was missed while the server was down fires ONCE
on the next tick rather than replaying every occurrence it slept through. A
catch-up storm across a fleet is far worse than a late apply.

``last_applied_at`` advances even when the target matched no hosts. The
schedule did fire; it simply had nothing to run against. Leaving it unset
would make an empty tag re-evaluate on every tick forever.

WHAT IT DOES NOT DECIDE
-----------------------
* Whether a host can run the command at all -- ``enqueue_message`` already
  refuses a command a host has not advertised support for (Phase 19), so this
  loop reuses that rather than inventing a second rule that could disagree.
* What the command looks like -- ``config_mgmt_dispatch`` builds it, and the
  apply endpoint uses the same builder. A scheduled apply that differed from
  a manual one would be a bug nobody finds until a fleet drifts.
* Cron semantics -- ``automation_engine`` owns the parser, as it does for
  air-gap collection schedules and upgrade profiles.

Unlicensed servers never reach any of this: assignments cannot be created
without ``config_management_engine``, so the loop finds nothing and the gate
at startup keeps it from running at all.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services import config_mgmt_dispatch as dispatch
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations
from backend.websocket.messages import CommandType, Message, MessageType

logger = logging.getLogger(__name__)

# 60s -- cron's finest granularity is one minute, so a tighter cadence is
# pure churn and a looser one lets a minute-boundary schedule slip a cycle.
TICK_INTERVAL_SECONDS = 60

# Shorter than the cadence so a transient DB blip recovers visibly, long
# enough that a persistent fault does not spam the log at full rate.
ERROR_BACKOFF_SECONDS = 30


def _naive_utc(value: datetime) -> datetime:
    """Rows are naive-UTC; comparing them to an aware value raises."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _is_due(automation, assignment, now: datetime) -> bool:
    """Whether this assignment's next occurrence has arrived.

    Anchored on the last apply, falling back to creation for one that has
    never run. A malformed cron is reported and skipped rather than raised:
    one bad expression must not stop every other assignment from firing.
    """
    anchor = assignment.last_applied_at or assignment.created_at
    if anchor is None:
        return True
    try:
        nxt = automation.next_run_from_cron(assignment.schedule, anchor)
    except Exception:  # pylint: disable=broad-except
        # The engine raises its own CronParseError type, which this module
        # cannot import without depending on a licensed artefact.
        logger.warning(
            "Config profile assignment %s has an unusable cron (%s); skipping",
            assignment.id,
            assignment.schedule,
        )
        return False
    return nxt is not None and _naive_utc(nxt) <= now


def _hosts_for(db_session, assignment) -> List[Any]:
    """The active hosts this assignment targets.

    Inactive hosts are excluded: queuing for one buries the work in a queue
    that may never drain while the operator sees it as dispatched.
    """
    query = db_session.query(models.Host).filter(models.Host.active.is_(True))

    if assignment.host_id:
        return query.filter(models.Host.id == assignment.host_id).all()
    if assignment.site_id:
        return query.filter(models.Host.site_id == assignment.site_id).all()
    if assignment.tag_id:
        return (
            query.join(models.HostTag, models.HostTag.host_id == models.Host.id)
            .filter(models.HostTag.tag_id == assignment.tag_id)
            .all()
        )
    # No target at all. The engine refuses to create one, so this is a row
    # that predates that rule or was written directly.
    return []


def _dispatch_one(db_session, host, parameters: Dict[str, Any]) -> bool:
    """Queue one apply. Returns False if this host could not take it.

    Per-host isolation is the point: an offline host, or one whose agent has
    not advertised config-management support, must not stop the rest of the
    fleet from getting the same profile.
    """
    command = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_CONFIG_PROFILE,
            "parameters": parameters,
        },
    )
    try:
        QueueOperations().enqueue_message(
            message_type="command",
            message_data=command.to_dict(),
            direction=QueueDirection.OUTBOUND,
            host_id=str(host.id),
            db=db_session,
        )
        return True
    except Exception:  # pylint: disable=broad-except
        # Includes UnsupportedCapabilityError, which is an ordinary outcome
        # for a host that cannot run playbooks -- not a fault worth a
        # traceback at warning level on every tick.
        logger.info(
            "Config profile not queued for host %s; it cannot take this command",
            host.id,
        )
        return False


def run_one_tick() -> Dict[str, Any]:
    """Fire every due assignment once. Never raises.

    Public rather than underscore-private so an operator-facing endpoint or a
    test can drive exactly one tick without waiting a minute for the loop.
    """
    summary: Dict[str, Any] = {
        "due": 0,
        "queued": 0,
        "skipped_hosts": 0,
        "no_cron_engine": False,
    }

    if module_loader.get_module("config_management_engine") is None:
        # Assignments cannot exist without the module; nothing to do.
        return summary

    automation = module_loader.get_module("automation_engine")
    if automation is None:
        # Without a cron parser nothing can be judged due. Reported rather
        # than guessed at -- firing everything would be worse than firing
        # nothing.
        summary["no_cron_engine"] = True
        return summary

    db_session = next(get_db())
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        assignments = (
            db_session.query(models.ConfigProfileAssignment)
            .join(
                models.ConfigProfile,
                models.ConfigProfile.id == models.ConfigProfileAssignment.profile_id,
            )
            .filter(
                models.ConfigProfileAssignment.enabled.is_(True),
                models.ConfigProfileAssignment.schedule.isnot(None),
                # An inactive profile is one somebody took out of service;
                # a schedule must not quietly keep applying it.
                models.ConfigProfile.is_active.is_(True),
            )
            .all()
        )

        for assignment in assignments:
            if not _is_due(automation, assignment, now):
                continue
            summary["due"] += 1

            profile = (
                db_session.query(models.ConfigProfile)
                .filter(models.ConfigProfile.id == assignment.profile_id)
                .first()
            )
            try:
                parameters = dispatch.parameters_for(
                    profile, check_mode=bool(assignment.check_mode)
                )
            except dispatch.DispatchError as exc:
                # A stored body that cannot be turned into a command. Advance
                # the cursor anyway: re-deciding this every minute produces an
                # identical failure and a flooded log.
                logger.error(
                    "Assignment %s cannot dispatch profile %s: %s",
                    assignment.id,
                    assignment.profile_id,
                    exc.message,
                )
                assignment.last_applied_at = now
                continue

            for host in _hosts_for(db_session, assignment):
                if _dispatch_one(db_session, host, parameters):
                    summary["queued"] += 1
                else:
                    summary["skipped_hosts"] += 1

            assignment.last_applied_at = now

        if summary["due"]:
            db_session.commit()
    except Exception:  # pylint: disable=broad-except
        logger.exception("Config profile assignment tick failed")
        db_session.rollback()
    finally:
        db_session.close()
    return summary


async def config_mgmt_assignment_tick_service() -> None:
    """Background service: one tick every ``TICK_INTERVAL_SECONDS``."""
    logger.info(
        "Starting config-profile assignment tick service (interval=%ds)",
        TICK_INTERVAL_SECONDS,
    )
    while True:
        try:
            summary = run_one_tick()
            if summary["due"] or summary["no_cron_engine"]:
                logger.info(
                    "Config assignment tick: due=%d queued=%d skipped_hosts=%d "
                    "automation_engine_absent=%s",
                    summary["due"],
                    summary["queued"],
                    summary["skipped_hosts"],
                    summary["no_cron_engine"],
                )
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Config assignment tick service cancelled — exiting loop")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Config assignment tick service error — sleeping then retrying"
            )
            await asyncio.sleep(ERROR_BACKOFF_SECONDS)
