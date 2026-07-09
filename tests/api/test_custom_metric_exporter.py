"""Tests for backend.api.custom_metric_exporter.

Covers the Prometheus text-exposition endpoint (``GET /metrics/custom-metrics``)
that surfaces the latest ok custom-metric sample per (metric, host):

  * 200 + ``text/plain`` content type + the ``# HELP``/``# TYPE`` header
  * the correct ``sysmanage_custom_metric_value{...} <value>`` line per host,
    latest-ok only (a newer errored sample must NOT override an older ok one,
    and errored/NULL samples are excluded)
  * Prometheus label-value escaping (backslash, double-quote, newline)
  * two hosts each get their own series
  * the app still boots and the route is mounted at exactly the root path
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.persistence.db import Base
from backend.persistence.models.core import Host
from backend.persistence.models.custom_metric import (
    SAMPLE_STATUS_ERROR,
    SAMPLE_STATUS_OK,
    CustomMetric,
    CustomMetricSample,
)

_TABLE_NAMES = ["custom_metric", "host", "custom_metric_sample"]


@pytest.fixture
def scratch_session():
    # StaticPool + one shared connection: TestClient runs the request on a
    # different thread than this fixture, so a per-thread SQLite connection
    # would see an empty DB (and error cross-thread).  A single shared
    # connection makes the seeded schema visible to the request thread.
    engine = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        Base.metadata.create_all(
            engine,
            tables=[Base.metadata.tables[t] for t in _TABLE_NAMES],
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def client(scratch_session, monkeypatch):
    """TestClient whose exporter reads the seeded scratch DB.

    The endpoint walks ``iter_host_databases()`` (the shared per-tenant seam),
    which in collapsed mode opens the one bootstrap DB.  We patch it to yield the
    seeded scratch session (tenant_id=None → collapsed/no tenant label) and a
    no-op close so the fixture stays in control of the session lifecycle.
    """

    class _NoCloseSession:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def close(self):  # exporter closes yielded sessions; keep ours open.
            pass

    def fake_iter():
        yield ("bootstrap", None, _NoCloseSession(scratch_session))

    monkeypatch.setattr("backend.persistence.partitions.iter_host_databases", fake_iter)
    return TestClient(app)


def _add_host(session, fqdn):
    host = Host(id=uuid.uuid4(), fqdn=fqdn, active=True)
    session.add(host)
    session.commit()
    return host


def _add_metric(session, name, unit=None):
    metric = CustomMetric(
        id=uuid.uuid4(),
        name=name,
        script="echo 1",
        interpreter="sh",
        unit=unit,
    )
    session.add(metric)
    session.commit()
    return metric


def _add_sample(session, metric, host, value, collected_at, status=SAMPLE_STATUS_OK):
    sample = CustomMetricSample(
        id=uuid.uuid4(),
        custom_metric_id=metric.id,
        host_id=host.id,
        value=value,
        status=status,
        collected_at=collected_at,
    )
    session.add(sample)
    session.commit()
    return sample


def test_exposition_happy_path(scratch_session, client):
    now = datetime.now(timezone.utc)
    metric = _add_metric(scratch_session, "disk-free", unit="%")
    host_a = _add_host(scratch_session, "a.example.com")
    host_b = _add_host(scratch_session, "b.example.com")

    # host_a: an older ok sample then a NEWER ok sample -> newest wins (42.5).
    _add_sample(scratch_session, metric, host_a, 10.0, now - timedelta(hours=2))
    _add_sample(scratch_session, metric, host_a, 42.5, now - timedelta(minutes=5))
    # host_a also has a newer ERRORED sample that must NOT override the ok one.
    _add_sample(
        scratch_session,
        metric,
        host_a,
        None,
        now,
        status=SAMPLE_STATUS_ERROR,
    )
    # host_b: a single ok sample.
    _add_sample(scratch_session, metric, host_b, 7.0, now - timedelta(minutes=1))

    resp = client.get("/metrics/custom-metrics")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "version=0.0.4" in resp.headers["content-type"]

    body = resp.text
    assert (
        "# HELP sysmanage_custom_metric_value Latest value of a user-defined "
        "custom metric." in body
    )
    assert "# TYPE sysmanage_custom_metric_value gauge" in body
    # Header appears exactly once.
    assert body.count("# HELP sysmanage_custom_metric_value") == 1
    assert body.count("# TYPE sysmanage_custom_metric_value") == 1

    # Latest-ok value for host_a is 42.5 (not 10.0, not the errored None).
    assert (
        'sysmanage_custom_metric_value{metric="disk-free",'
        'host="a.example.com",unit="%"} 42.5' in body
    )
    # host_b series.
    assert (
        'sysmanage_custom_metric_value{metric="disk-free",'
        'host="b.example.com",unit="%"} 7.0' in body
    )
    # No tenant label in collapsed mode.
    assert "tenant=" not in body
    # The stale 10.0 value never appears.
    assert "} 10.0" not in body


def test_metric_with_no_ok_sample_is_skipped(scratch_session, client):
    now = datetime.now(timezone.utc)
    metric = _add_metric(scratch_session, "flaky", unit="ms")
    host = _add_host(scratch_session, "h.example.com")
    # Only an errored sample -> the metric must not appear at all.
    _add_sample(scratch_session, metric, host, None, now, status=SAMPLE_STATUS_ERROR)

    resp = client.get("/metrics/custom-metrics")
    assert resp.status_code == 200
    assert "flaky" not in resp.text
    # Header still present.
    assert "# TYPE sysmanage_custom_metric_value gauge" in resp.text


def test_label_value_escaping(scratch_session, client):
    now = datetime.now(timezone.utc)
    # Name with a double-quote and backslash; fqdn with a newline.
    metric = _add_metric(scratch_session, 'we"ird\\name', unit="x")
    host = _add_host(scratch_session, "line1\nline2")
    _add_sample(scratch_session, metric, host, 3.0, now)

    resp = client.get("/metrics/custom-metrics")
    body = resp.text

    # backslash -> \\ , double-quote -> \" , newline -> \n (literal backslash-n)
    assert 'metric="we\\"ird\\\\name"' in body
    assert 'host="line1\\nline2"' in body
    # A raw newline must NOT appear inside the label section.
    assert "line1\nline2" not in body


def test_empty_db_returns_header_only(client):
    resp = client.get("/metrics/custom-metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "# HELP sysmanage_custom_metric_value" in body
    assert "# TYPE sysmanage_custom_metric_value gauge" in body
    assert "sysmanage_custom_metric_value{" not in body


def test_tenant_label_emitted_in_mt_mode(scratch_session, monkeypatch):
    """When iter_host_databases yields a tenant_id, a ``tenant`` label appears."""
    now = datetime.now(timezone.utc)
    metric = _add_metric(scratch_session, "cpu", unit="%")
    host = _add_host(scratch_session, "t.example.com")
    _add_sample(scratch_session, metric, host, 55.0, now)

    class _NoCloseSession:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def close(self):
            pass

    def fake_iter():
        yield ("tenant abc", "tenant-abc-123", _NoCloseSession(scratch_session))

    monkeypatch.setattr("backend.persistence.partitions.iter_host_databases", fake_iter)
    resp = TestClient(app).get("/metrics/custom-metrics")
    assert resp.status_code == 200
    assert (
        'sysmanage_custom_metric_value{metric="cpu",host="t.example.com",'
        'unit="%",tenant="tenant-abc-123"} 55.0' in resp.text
    )


def test_route_mounted_at_root_not_under_api_v1():
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/metrics/custom-metrics" in paths
    assert "/api/v1/metrics/custom-metrics" not in paths
