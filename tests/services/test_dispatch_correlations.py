# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Dispatch correlations reach whichever worker handles the result.

The leader dispatches a plan; any worker may process the agent's result.
The correlation used to be that one process's memory, so a result handled
by another worker was dropped and the air-gap run waited forever
(2026-11-25)."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.persistence import models
from backend.services import dispatch_correlations, proplus_dispatch


@pytest.fixture
def bind():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.DispatchCorrelation.__table__.create(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def worker_memory():
    """This process's map, emptied: the 'other worker'."""
    with patch.dict(proplus_dispatch._CORRELATIONS, clear=True):
        yield proplus_dispatch._CORRELATIONS


def test_a_result_handled_by_another_worker_is_routed(bind, worker_memory):
    with patch.object(proplus_dispatch, "_outbound_engine", return_value=bind):
        proplus_dispatch.register_airgap_run_correlation(
            "m-1", "mirroring", "run-1", "h-1"
        )
    worker_memory.clear()  # the result lands on a worker that never saw it
    db = Session(bind=bind)
    try:
        with patch.object(proplus_dispatch, "_apply_simple_result") as applied:
            assert proplus_dispatch.route_proplus_command_result(
                "m-1", {"success": True, "result": {}}, db
            )
        assert applied.call_args.args[1:4] == ("airgap_run", "mirroring:run-1", "h-1")
        # Claimed: routed once, never twice.
        assert not proplus_dispatch.route_proplus_command_result(
            "m-1", {"success": True}, db
        )
    finally:
        db.close()


def test_the_dispatching_worker_clears_the_stored_copy(bind, worker_memory):
    with patch.object(proplus_dispatch, "_outbound_engine", return_value=bind):
        proplus_dispatch.register_airgap_run_correlation(
            "m-2", "building_iso", "run-2", "h-1"
        )
        assert proplus_dispatch._pop_correlation("m-2") == (
            "airgap_run",
            "building_iso:run-2",
            "h-1",
        )
    assert dispatch_correlations.take(bind, "m-2") is None


def test_an_unknown_result_is_not_routed(bind, worker_memory):
    db = Session(bind=bind)
    try:
        assert not proplus_dispatch.route_proplus_command_result(
            "nope", {"success": True}, db
        )
    finally:
        db.close()


def test_stale_correlations_are_pruned(bind):
    dispatch_correlations.save(bind, "old", "airgap_run", "x", "h")
    with Session(bind=bind) as session:
        row = session.get(models.DispatchCorrelation, "old")
        row.created_at = (
            row.created_at - dispatch_correlations.KEEP - timedelta(hours=1)
        )
        session.commit()
    dispatch_correlations.save(bind, "new", "airgap_run", "y", "h")
    assert dispatch_correlations.take(bind, "old") is None
    assert dispatch_correlations.take(bind, "new") == ("airgap_run", "y", "h")


def test_a_database_failure_never_breaks_dispatch(worker_memory):
    broken = create_engine("sqlite://")  # no table
    try:
        with patch.object(proplus_dispatch, "_outbound_engine", return_value=broken):
            proplus_dispatch.register_airgap_run_correlation(
                "m-3", "mirroring", "r", "h"
            )
            assert proplus_dispatch._pop_correlation("m-3")[0] == "airgap_run"
        assert dispatch_correlations.take(broken, "m-3") is None
    finally:
        broken.dispose()
