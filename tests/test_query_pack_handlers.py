# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Ingesting query-pack results from an agent (Phase 21.1 S4).

WHY THIS FILE EXISTS
--------------------
The first live round trip lost every measurement. Both hosts ran all three
queries and answered; the agent's reply did not echo ``run_id``, so the server
could not tell which run the results belonged to and discarded all of them:

    Query pack results arrived for run None, which does not exist on this
    server; 3 result(s) discarded

Nothing caught it because the two halves were tested separately and correctly.
The agent tests asserted it runs SQL and reports coverage; the service tests
asserted it records and grades what it is handed. The CONTRACT between them --
the shape the agent returns and the field the server correlates on -- was the
one thing neither side owned.

So these tests feed the handler exactly what the agent produces, and the agent
suite has a matching test that the field is echoed. Either one failing means
the round trip is broken.
"""

import uuid
from datetime import datetime, timezone

import pytest

from backend.api.handlers import query_pack_handlers as handlers
from backend.persistence import models


def agent_reply(run_id, results=None, contract_version=1):
    """The envelope an agent actually sends back.

    Mirrors ``query_pack_operations.run_query_pack`` wrapping
    ``query_pack_runner.run_pack`` -- note the DOUBLE nesting: the command
    result carries {"success", "result"} and the runner's own dict is inside
    that ``result``. Getting that wrong is how the correlation was lost.
    """
    return {
        "command_id": str(uuid.uuid4()),
        "success": True,
        "result": {
            "success": True,
            "result": {
                "run_id": run_id,
                "pack_name": "s4-smoke",
                "contract_version": contract_version,
                "results": (
                    results
                    if results is not None
                    else [
                        {"name": "root_accounts", "status": "ok", "rows": [{"uid": 0}]}
                    ]
                ),
            },
        },
    }


@pytest.fixture
def run(session):
    row = models.QueryPackRun(
        id=uuid.uuid4(),
        host_id=uuid.uuid4(),
        pack_name="s4-smoke",
        status=models.RUN_STATUS_PENDING,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(row)
    session.flush()
    return row


@pytest.mark.asyncio
async def test_results_are_attached_to_the_run_the_agent_names(session, run):
    """THE regression. This is the exact shape that came back empty-handed."""
    reply = agent_reply(str(run.id))
    out = await handlers.handle_query_pack_result(session, None, reply)
    assert out["status"] == "recorded"
    session.refresh(run)
    assert run.status == models.RUN_STATUS_SUCCESS
    assert run.queries_ok == 1
    assert run.contract_version == 1


@pytest.mark.asyncio
async def test_a_reply_without_a_run_id_is_reported_not_silently_dropped(
    session, caplog
):
    """Losing measurements is a real loss -- they cannot be retaken until the
    next interval -- so it must be visible rather than a quiet no-op."""
    reply = agent_reply(None)
    out = await handlers.handle_query_pack_result(session, None, reply)
    assert out["status"] == "ignored"
    assert "discarded" in caplog.text


@pytest.mark.asyncio
async def test_an_uncovered_query_grades_the_run_partial(session, run):
    """The substrate's property surviving the ingest path."""
    reply = agent_reply(
        str(run.id),
        results=[
            {"name": "root_accounts", "status": "ok", "rows": [{"uid": 0}]},
            {"name": "deb_count", "status": "not_covered", "reason": "wrong_platform"},
        ],
    )
    await handlers.handle_query_pack_result(session, None, reply)
    session.refresh(run)
    assert run.status == models.RUN_STATUS_PARTIAL
    assert run.queries_not_covered == 1


@pytest.mark.asyncio
async def test_a_failed_command_closes_its_run(session, run):
    """Left PENDING it would present the host as still collecting forever."""
    reply = {
        "command_id": str(uuid.uuid4()),
        "success": False,
        "error": "The query pack has no queries.",
        "result": {"run_id": str(run.id)},
    }
    out = await handlers.handle_query_pack_result(session, None, reply)
    assert out["status"] == "failed"
    session.refresh(run)
    assert run.status == models.RUN_STATUS_FAILED
    assert "no queries" in (run.error or "")
