# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Built-in host metrics (Phase 21.5).

What is under test: the five series become system-defined custom metrics
(created lazily, once, never on top of an operator's own metric of the same
name), the server keeps ONE sample per series per 15 minutes however often
the agent reports, a disabled built-in stops collecting, and nothing is
stored unless observability_engine is licensed.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.handlers.custom_metric_handlers import handle_host_metrics
from backend.persistence.db import Base
from backend.persistence.models.custom_metric import CustomMetric, CustomMetricSample
from backend.services import host_metrics

_TABLE_NAMES = [
    "custom_metric",
    "host",
    "tags",
    "custom_metric_tag",
    "custom_metric_sample",
]
T0 = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
HOST = uuid.uuid4()


@pytest.fixture
def session():
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[t] for t in _TABLE_NAMES]
    )
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        yield s
    engine.dispose()


def _report(minutes, **metrics):
    return {
        "collected_at": (T0 + timedelta(minutes=minutes)).isoformat(),
        "metrics": metrics or {"host.cpu_percent": 10.0, "host.load_1m": 0.5},
    }


def _samples(session, key=None):
    query = session.query(CustomMetricSample).join(CustomMetric)
    if key:
        query = query.filter(CustomMetric.builtin_key == key)
    return query.order_by(CustomMetricSample.collected_at).all()


def test_builtins_are_created_once_as_system_metrics(session):
    first = host_metrics.ensure_builtin_metrics(session)
    session.commit()
    second = host_metrics.ensure_builtin_metrics(session)
    assert set(first) == set(host_metrics.BUILTIN_KEYS)
    assert {k: m.id for k, m in first.items()} == {k: m.id for k, m in second.items()}
    cpu = first["host.cpu_percent"]
    # No script, no tags: the tag-driven deploy can never ship it to an agent.
    assert cpu.script == "" and not cpu.tags
    assert cpu.unit == "%" and first["host.load_1m"].unit is None
    assert session.query(CustomMetric).count() == len(host_metrics.BUILTINS)


def test_an_operator_metric_with_the_same_name_is_never_adopted(session):
    session.add(
        CustomMetric(name="host.cpu_percent", script="echo 1", interpreter="sh")
    )
    session.commit()
    builtins = host_metrics.ensure_builtin_metrics(session)
    assert "host.cpu_percent" not in builtins
    assert len(builtins) == len(host_metrics.BUILTINS) - 1
    operator = session.query(CustomMetric).filter_by(name="host.cpu_percent").one()
    assert operator.builtin_key is None and operator.script == "echo 1"


def test_one_sample_per_series_per_15_minutes(session):
    # The agent reports every 5 minutes for half an hour.
    for minutes in range(0, 35, 5):
        host_metrics.store_host_metrics(session, HOST, _report(minutes))
        session.commit()
    stored = [
        s.collected_at.replace(tzinfo=timezone.utc)
        for s in _samples(session, "host.cpu_percent")
    ]
    assert stored == [T0, T0 + timedelta(minutes=15), T0 + timedelta(minutes=30)]


def test_a_report_a_little_early_is_still_kept(session):
    host_metrics.store_host_metrics(session, HOST, _report(0))
    session.commit()
    # 14.5 minutes later: agent jitter must not stretch the gap to 20 minutes.
    stored = host_metrics.store_host_metrics(session, HOST, _report(14.5))
    assert stored == 2


def test_only_the_series_reported_are_stored(session):
    host_metrics.store_host_metrics(
        session, HOST, _report(0, **{"host.cpu_percent": 5.0, "host.bogus": 1.0})
    )
    session.commit()
    samples = _samples(session)
    assert [s.custom_metric.builtin_key for s in samples] == ["host.cpu_percent"]
    assert samples[0].value == 5.0 and samples[0].status == "ok"


def test_non_numeric_values_are_not_readings(session):
    report = _report(
        0,
        **{
            "host.cpu_percent": "high",
            "host.load_1m": float("nan"),
            "host.swap_used_percent": True,
        }
    )
    assert host_metrics.store_host_metrics(session, HOST, report) == 0


def test_a_disabled_builtin_stops_collecting(session):
    builtins = host_metrics.ensure_builtin_metrics(session)
    builtins["host.load_1m"].enabled = False
    session.commit()
    host_metrics.store_host_metrics(session, HOST, _report(0))
    session.commit()
    assert [s.custom_metric.builtin_key for s in _samples(session)] == [
        "host.cpu_percent"
    ]


def test_hosts_are_thinned_independently(session):
    other = uuid.uuid4()
    host_metrics.store_host_metrics(session, HOST, _report(0))
    session.commit()
    assert host_metrics.store_host_metrics(session, other, _report(5)) == 2


def _run(coro):
    return asyncio.run(coro)


def test_handler_stores_nothing_when_unlicensed(session):
    with patch.object(host_metrics, "collecting", return_value=False):
        ack = _run(
            handle_host_metrics(session, SimpleNamespace(host_id=HOST), _report(0))
        )
    assert ack == {"message_type": "host_metrics_ack"}
    assert session.query(CustomMetric).count() == 0
    assert session.query(CustomMetricSample).count() == 0


def test_handler_stores_when_licensed_and_accepts_both_payload_shapes(session):
    with patch.object(host_metrics, "collecting", return_value=True):
        _run(handle_host_metrics(session, SimpleNamespace(host_id=HOST), _report(0)))
        _run(
            handle_host_metrics(
                session, SimpleNamespace(host_id=HOST), {"data": _report(15)}
            )
        )
    assert len(_samples(session, "host.cpu_percent")) == 2


def test_handler_without_a_host_is_an_error_not_a_crash(session):
    ack = _run(handle_host_metrics(session, SimpleNamespace(host_id=None), _report(0)))
    assert ack["error_type"] == "host_not_registered"
