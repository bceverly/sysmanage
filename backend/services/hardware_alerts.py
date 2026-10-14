# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Hardware alerts on arrival (Phase 23.1 S5).

The alerting engine (Pro+, ``alerting_engine``) evaluates its rules every
60 seconds.  A failing drive should not wait for that: when a hardware report
CHANGED something -- a component's state, or the operating system announced
a problem (S3) -- the handler hands the host to the engine here, and its
``hardware_health`` rules are evaluated for that host at once.

Off the event loop (a notification can be a slow SMTP round trip) and on its
own session; without the engine, or on any error, nothing happens here and
the 60-second tick still catches it.
"""

import asyncio
import logging

from sqlalchemy.orm import sessionmaker

from backend.licensing.module_loader import module_loader

logger = logging.getLogger(__name__)

ENGINE = "alerting_engine"
CONDITIONS = ("hardware_health",)


def _evaluate(bind, host_id) -> int:
    engine = module_loader.get_module(ENGINE)
    evaluate = getattr(engine, "evaluate_host_now", None) if engine else None
    if evaluate is None:
        return 0
    session = sessionmaker(bind=bind)()
    try:
        return evaluate(session, str(host_id), CONDITIONS)
    finally:
        session.close()


async def on_report(db, host, events) -> None:
    """Evaluate ``host``'s hardware rules now, if the report changed anything."""
    if not events:
        return
    try:
        fired = await asyncio.to_thread(_evaluate, db.get_bind(), host.id)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Hardware alerts for host %s (%s) not evaluated on arrival: %s; "
            "the next alerting tick will",
            host.id, getattr(host, "fqdn", "?"), exc,
        )  # fmt: skip
        return
    if fired:
        logger.info(
            "Hardware alerts for host %s: %d raised or escalated", host.id, fired
        )
