# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The advisor endpoints, exercised THROUGH the router (Phase 21.2 S4).

Through the router on purpose -- query packs shipped seven GETs gated on a
role that did not exist, and service-level tests stayed green. And against a
real (SQLite) schema, because what matters most here is a property of the
data: the not-assessable count travels beside every finding count and is
never folded into "no recommendations".
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import advisor
from backend.auth.auth_bearer import require_authenticated_user
from backend.persistence import models
from backend.persistence.db import Base
from backend.persistence.partitions import get_tenant_db
from backend.services import advisor_tick

NOW = datetime.now(timezone.utc).replace(tzinfo=None)

RULE = {
    "id": "SEC-001",
    "version": 1,
    "contract": 1,
    "title": "Critical CVE with a fix",
    "lens": "security",
    "requires": {"domains": ["vuln"]},
    "when": "SELECT package_name FROM sm_vuln_finding",
    "impact": 5,
    "likelihood": 4,
    "remediation": "Upgrade {package_name}",
}


class Engine:
    """Stands in for advisor_engine: codes for a bad rule, worst-finding score."""

    def validate_rule(self, rule):
        return (
            [] if rule.get("title") else [{"code": "missing_field", "field": "title"}]
        )

    def score_host(self, results):
        fired = [r["risk"] for r in results if r["outcome"] == "fires"]
        gaps = any(r["outcome"] == "not_assessable" for r in results)
        if fired:
            return {"score": max(fired) * 4, "level": "HIGH", "complete": not gaps}
        if results and not gaps:
            return {"score": 0, "level": "NONE", "complete": True}
        return {"score": None, "level": "UNKNOWN", "complete": False}

    def score_fleet(self, hosts):
        assessed = [h for h in hosts if h["score"] is not None]
        return {
            "total_hosts": len(hosts),
            "assessed_hosts": len(assessed),
            "unknown_hosts": len(hosts) - len(assessed),
        }

    def render_remediation(self, rule, matches):
        return [
            rule["remediation"].replace("{package_name}", m["package_name"])
            for m in matches
        ]


class User:
    userid = "admin@sysmanage.org"
    allowed = True

    def has_role(self, _role):
        return User.allowed


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(db_factory):
    app = FastAPI()
    app.include_router(advisor.router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = User

    def _db():
        # A generator, not the sessionmaker itself: FastAPI would read its
        # ``**local_kw`` as a required query parameter.
        session = db_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_tenant_db] = _db
    for dep in advisor.router.dependencies:
        app.dependency_overrides[dep.dependency] = lambda: None
    User.allowed = True
    with patch.object(advisor, "_engine", return_value=Engine()), patch.object(
        advisor_tick, "load_shared_rules", return_value=[]
    ):
        yield TestClient(app, raise_server_exceptions=False)


def _host(db_factory, fqdn="h1"):
    with db_factory() as db:
        host = models.Host(
            id=uuid.uuid4(), fqdn=fqdn, active=True, approval_status="approved"
        )
        db.add(host)
        db.commit()
        return host


def _result(db_factory, host, outcome, key="SEC-001", **kw):
    with db_factory() as db:
        db.add(
            models.AdvisorResult(
                host_id=host.id,
                rule_source="tenant",
                rule_key=key,
                outcome=outcome,
                lens="security",
                evaluated_at=NOW,
                **kw,
            )
        )
        db.commit()


def _create(client, rule=None):
    return client.post("/api/v1/advisor/rules", json={"rule": rule or RULE})


class TestRules:
    def test_create_list_update_delete(self, client):
        created = _create(client)
        assert created.status_code == 200, created.text
        rule_id = created.json()["id"]
        listed = client.get("/api/v1/advisor/rules").json()
        assert [r["key"] for r in listed["tenant"]] == ["SEC-001"]
        assert listed["tenant"][0]["errors"] == []
        changed = dict(RULE, title="Renamed")
        assert (
            client.put(
                f"/api/v1/advisor/rules/{rule_id}", json={"rule": changed}
            ).json()["title"]
            == "Renamed"
        )
        assert client.delete(f"/api/v1/advisor/rules/{rule_id}").status_code == 200
        assert client.get("/api/v1/advisor/rules").json()["tenant"] == []

    def test_a_rejected_rule_returns_every_problem_as_codes(self, client):
        response = _create(client, dict(RULE, title=""))
        assert response.status_code == 400
        assert response.json()["detail"]["errors"] == [
            {"code": "missing_field", "field": "title"}
        ]

    def test_validate_does_not_store(self, client):
        response = client.post(
            "/api/v1/advisor/rules/validate", json={"rule": dict(RULE, title="")}
        )
        assert response.json()["errors"][0]["code"] == "missing_field"
        assert client.get("/api/v1/advisor/rules").json()["tenant"] == []

    def test_a_duplicate_key_is_a_conflict(self, client):
        _create(client)
        assert _create(client).status_code == 409

    def test_writes_need_the_script_roles(self, client):
        User.allowed = False
        assert _create(client).status_code == 403

    def test_unknown_and_malformed_ids(self, client):
        assert client.delete(f"/api/v1/advisor/rules/{uuid.uuid4()}").status_code == 404
        assert client.delete("/api/v1/advisor/rules/not-a-uuid").status_code == 400

    def test_disabling_a_rule_clears_its_standing_outcomes(self, client, db_factory):
        rule_id = _create(client).json()["id"]
        host = _host(db_factory)
        _result(db_factory, host, "fires", risk=20, rule_id=uuid.UUID(rule_id))
        client.put(f"/api/v1/advisor/rules/{rule_id}", json={"enabled": False})
        assert client.get("/api/v1/advisor/feed").json()["rules"] == []


class TestFeed:
    def test_not_assessable_travels_beside_the_findings(self, client, db_factory):
        """THE property: three hosts could not be evaluated and the feed says so."""
        _create(client)
        _result(
            db_factory,
            _host(db_factory, "a"),
            "fires",
            risk=20,
            matches=[{"package_name": "openssl"}],
            match_count=1,
        )
        for name in ("b", "c", "d"):
            _result(
                db_factory,
                _host(db_factory, name),
                "not_assessable",
                gaps=[{"evidence": "vuln", "reason": "stale"}],
            )
        body = client.get("/api/v1/advisor/feed").json()
        entry = body["rules"][0]
        assert entry["hosts_firing"] == 1 and entry["hosts_not_assessable"] == 3
        assert entry["gap_reasons"] == {"stale": 3}
        assert body["totals"] == {
            "findings": 1,
            "not_assessable": 3,
            "not_applicable": 0,
            "clean": 0,
        }
        assert body["fleet"]["unknown_hosts"] == 3

    def test_a_blind_spot_outranks_a_clean_rule(self, client, db_factory):
        host = _host(db_factory)
        _result(db_factory, host, "does_not_fire", key="CLEAN")
        _result(db_factory, host, "not_assessable", key="BLIND")
        keys = [e["key"] for e in client.get("/api/v1/advisor/feed").json()["rules"]]
        assert keys == ["BLIND", "CLEAN"]

    def test_lens_filter(self, client, db_factory):
        _result(db_factory, _host(db_factory), "fires", risk=4)
        assert client.get("/api/v1/advisor/feed?lens=stability").json()["rules"] == []


class TestHostAndRuleViews:
    def test_host_view_groups_outcomes_and_renders_remediation(
        self, client, db_factory
    ):
        _create(client)
        host = _host(db_factory)
        _result(
            db_factory,
            host,
            "fires",
            risk=20,
            matches=[{"package_name": "openssl"}],
            match_count=1,
        )
        _result(
            db_factory,
            host,
            "not_assessable",
            key="OTHER",
            gaps=[{"evidence": "facts.mounts", "reason": "not_collected"}],
        )
        body = client.get(f"/api/v1/advisor/hosts/{host.id}").json()
        assert body["findings"][0]["remediation"] == ["Upgrade openssl"]
        assert body["not_assessable"][0]["gaps"][0]["reason"] == "not_collected"
        assert body["score"]["complete"] is False

    def test_an_unknown_host_is_404(self, client):
        assert client.get(f"/api/v1/advisor/hosts/{uuid.uuid4()}").status_code == 404

    def test_rule_hosts_by_outcome(self, client, db_factory):
        _result(db_factory, _host(db_factory, "a"), "fires", risk=20)
        _result(db_factory, _host(db_factory, "b"), "not_assessable")
        body = client.get(
            "/api/v1/advisor/rules/tenant/SEC-001/hosts?outcome=not_assessable"
        ).json()
        assert [h["fqdn"] for h in body["hosts"]] == ["b"]

    def test_bad_rule_filters_are_400(self, client):
        assert client.get("/api/v1/advisor/rules/bogus/X/hosts").status_code == 400
        assert (
            client.get("/api/v1/advisor/rules/tenant/X/hosts?outcome=bogus").status_code
            == 400
        )


class TestEvaluate:
    def test_evaluate_runs_this_database_only(self, client):
        with patch.object(
            advisor.tick, "evaluate_database", return_value={"results": 3}
        ) as run:
            assert client.post("/api/v1/advisor/evaluate").json() == {"results": 3}
        assert run.call_args.args[1] == "api"

    def test_evaluate_needs_run_script(self, client):
        User.allowed = False
        assert client.post("/api/v1/advisor/evaluate").status_code == 403
