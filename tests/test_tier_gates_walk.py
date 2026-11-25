# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Every edition gate, walked route by route (Phase 25 edition audit,
2026-11-14; ROADMAP "Every tier 402-clean when unlicensed, in both repos").

The app is assembled as production assembles it -- every OSS router, then
each engine's router or, with the engine absent, its stubs -- and every route
is called once per edition as a user holding every role, with path, query and
body values made up from the route's own schema (see tests/tier_walk.py).  A
new route is covered the day it is added; nothing here lists routes to check.

What each edition must see:

* **No server errors.**  An unlicensed call is answered, never a traceback.
* **A license answer is 402.**  Any answer naming a missing license
  (``detail.error == "pro_plus_required"``) is HTTP 402.  The shared gates
  answered 403 until this audit, so an unlicensed caller -- or a Professional
  license asking for an Enterprise feature -- read "forbidden".
* **Nothing answers ``200 {"licensed": false}``.**  The stubs once did, for
  reads and writes alike; a write so answered told a script its deploy or
  dispatch had worked, and a read so answered hid the license behind a
  success.  Both are 402 now, like every other license answer.  The only
  exceptions are the reviewed Community reads below that carry a
  ``licensed`` flag beside real data.
* **Each tier opens exactly its own modules and features.**  Where a gate
  names the module or feature it needs, a license of that tier is refused
  (402) exactly when the tier does not include it; when it does, the answer
  is "licensed but not loaded" (503), since no engine is loaded here.
* **Community backups are untouched** ("never hold safety hostage"): every
  backup route answers without a 402 except the reviewed Pro+ ones below.
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import pytest

from backend.licensing.features import (
    TIER_FEATURES,
    TIER_MODULES,
    LicenseTier,
)
from tests import tier_walk

# A 5xx the walk accepts, each with the reason: none is about the license.
ENVIRONMENT_5XX = {
    ("GET", "/api/agent/server-identity"): (
        "503 tls_identity_unknown: this machine's nginx does not serve the "
        "agent TLS identity"
    ),
}

# Community reads that answer 200 with a ``licensed`` flag among real data:
# the page works unlicensed and the flag only says whether one licensed
# extra is on offer.  Each is reviewed; a Pro+ read never belongs here.
COMMUNITY_LICENSED_FLAG = {
    ("GET", "/api/v1/hardware-health/smartmontools"): (
        "Community host list; ``licensed`` says whether the automatic "
        "install (Enterprise) can be offered"
    ),
    ("GET", "/api/v1/backups/offsite"): (
        "the off-site cloud copy's record and restore are Community; "
        "``licensed`` says whether setting it up can be offered (27.3)"
    ),
}

# Backup routes whose gate depends on what is already there: the walk's
# sample data has a target, so adding one is a SECOND target, which is
# Enterprise (27.3); the first is Community (tests/test_backups_targets.py
# proves both answers).
DEPENDS_ON_STATE = {
    ("POST", "/api/v1/backups/targets"): (
        "the first target is Community; another is Enterprise (27.3)"
    ),
}

# The backup routes that need the Professional+ backup engine.  Every OTHER
# route whose path names a backup is Community and must never answer 402:
# backing up, restoring, browsing, the break-glass export, the server's own
# (unencrypted) backup, restate-proxy as a transport, Equip.
PRO_PLUS_BACKUP = {
    # Enterprise backup operations (27.1, backup_ops_engine): restore readiness.
    ("GET", "/api/v1/backups/readiness"),
    ("PUT", "/api/v1/host/{host_id}/backup-readiness"),
    # ... and four-eyes restore approval (27.2).
    ("GET", "/api/v1/backups/four-eyes"),
    ("PUT", "/api/v1/backups/four-eyes"),
    ("POST", "/api/v1/backups/restore-requests/{request_id}/approve"),
    ("POST", "/api/v1/backups/restore-requests/{request_id}/reject"),
    ("POST", "/api/v1/backups/restore-requests/{request_id}/withdraw"),
    # ... and fleet restore jobs (27.2).
    ("GET", "/api/v1/backups/fleet-restores"),
    ("POST", "/api/v1/backups/fleet-restores"),
    ("GET", "/api/v1/backups/fleet-restores/{job_id}"),
    ("POST", "/api/v1/backups/fleet-restores/{job_id}/cancel"),
    # ... and legal hold (27.2): placing and releasing; honoring needs none.
    ("GET", "/api/v1/backups/legal-holds"),
    ("POST", "/api/v1/host/{host_id}/backup-snapshots/{snapshot}/hold"),
    ("POST", "/api/v1/backups/legal-holds/{hold_id}/release"),
    # ... and off-site copies (27.3): setting or stopping one.
    ("PUT", "/api/v1/backups/targets/{target_id}/replica"),
    # ... and the cloud copy (27.3, Pro+ backup_engine): setting one up and a
    # new key.  Its other routes find no copy in the walk (404); turning it
    # off, checking, restoring and the key export are Community.
    ("POST", "/api/v1/backups/offsite"),
    ("POST", "/api/v1/backups/offsite/{copy_id}/rotate-key"),
    ("GET", "/api/v1/host/{host_id}/backup-drift"),
    ("POST", "/api/v1/host/{host_id}/backup-drift/compute"),
    ("PUT", "/api/v1/host/{host_id}/backup-drift/ignore"),
    ("GET", "/api/v1/host/{host_id}/backup-retention-preview"),
    ("PUT", "/api/v1/backups/escrow/key"),
    ("GET", "/api/v1/backups/tag-policies"),
    ("POST", "/api/v1/backups/tag-policies"),
    ("PUT", "/api/v1/backups/tag-policies/{policy_id}"),
    ("DELETE", "/api/v1/backups/tag-policies/{policy_id}"),
    ("POST", "/api/v1/backups/tag-policies/apply"),
    ("GET", "/api/v1/backups/host/{host_id}/use-tag-policy"),
    ("POST", "/api/v1/backups/host/{host_id}/use-tag-policy"),
    # The backup engine's own routes (24.6 encryption, rotation, signing);
    # the break-glass export Community needs is /api/v1/backups/break-glass.
    ("GET", "/api/v1/backup-encryption/host/{host_id}"),
    ("POST", "/api/v1/backup-encryption/host/{host_id}"),
    ("POST", "/api/v1/backup-encryption/host/{host_id}/rotate"),
    ("GET", "/api/v1/backup-encryption/settings"),
    ("PUT", "/api/v1/backup-encryption/settings"),
    ("GET", "/api/v1/backup-encryption/signing"),
    ("POST", "/api/v1/backup-encryption/signing"),
    ("POST", "/api/v1/backup-encryption/break-glass"),
}

_APP = {}


def _app():
    if "app" not in _APP:
        _APP["app"] = tier_walk.build_app()
    return _APP["app"]


@pytest.fixture
def edition(client, db_session, tmp_path):
    """``edition(tier)`` -> a context yielding a client of the walk's app
    with that tier's license cached and no engine loaded."""
    # pylint: disable=import-outside-toplevel
    from backend.licensing.license_service import license_service
    from backend.main import app as main_app
    from backend.persistence.models import User

    user = db_session.query(User).filter_by(userid="test_user@example.com").one()
    user.is_admin = True
    db_session.commit()
    tier_walk.seed(db_session)
    app = _app()
    overrides = dict(main_app.dependency_overrides)

    @contextmanager
    def run(tier):
        with ExitStack() as stack:
            tier_walk.no_side_effects(stack)
            # The always-mounted federation identity routes create a key and a
            # TLS certificate on first read under /var/lib/sysmanage, which a
            # developer box can write and a CI runner cannot (500 there only).
            # Keep them in the test's own directory.
            fed = tmp_path / "federation"
            for getter, path in (
                ("get_federation_identity_key_file", fed / "identity-ed25519.pem"),
                ("get_federation_tls_cert_file", fed / "identity-cert.pem"),
                ("get_federation_peer_public_key_dir", fed / "peers"),
            ):
                stack.enter_context(
                    patch(f"backend.config.config.{getter}", lambda p=path: str(p))
                )
            stack.enter_context(
                patch.object(
                    license_service, "_cached_license", tier_walk.tier_license(tier)
                )
            )
            app.dependency_overrides.clear()
            try:
                with tier_walk.walk_client(app, overrides) as test_client:
                    yield test_client
            finally:
                app.dependency_overrides.clear()

    return run


def _walk(edition, tier):
    with edition(tier) as test_client:
        return tier_walk.walk(test_client, _app())


def _server_errors(answers, licensed=False):
    """5xx answers, less the reviewed environment ones.  With a license, 503
    is the honest "licensed, but the engine is not loaded" (none is loaded
    here); unlicensed, a 503 would hide the missing license."""
    return [
        f"{method} {path} -> {response.status_code}: {response.text[:160]}"
        for method, path, response in answers
        if response.status_code >= 500
        and (method, path) not in ENVIRONMENT_5XX
        and not (licensed and response.status_code == 503)
    ]


def _quiet_unlicensed(response):
    """A 2xx that says "not licensed" -- the shape the stubs used before
    every unlicensed read and write became a 402."""
    if not 200 <= response.status_code < 300:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("licensed") is False


def test_the_walk_is_not_blind():
    """Guard for the guard: a walk that found no routes would pass."""
    found = set(tier_walk.http_routes(_app()))
    assert len(found) > 800, f"only {len(found)} routes -- the walk is blind"
    for route in (
        ("POST", "/api/v1/fleet/bulk"),  # an engine stub
        ("GET", "/api/v1/advisor/rules"),  # a module-gated OSS router
        ("GET", "/api/v1/backups/overview"),  # Community
    ):
        assert route in found, route


def test_unlicensed_every_license_answer_is_a_clean_402(edition):
    answers = _walk(edition, LicenseTier.COMMUNITY)
    failures = _server_errors(answers)
    for method, path, response in answers:
        if tier_walk.license_error(response) and response.status_code != 402:
            failures.append(
                f"{method} {path} -> {response.status_code} for a missing license"
            )
        reviewed = (method, path) in COMMUNITY_LICENSED_FLAG
        if _quiet_unlicensed(response) and not reviewed:
            failures.append(
                f"{method} {path} -> {response.status_code} licensed:false, want 402"
            )
    assert not failures, "Unlicensed, these are not 402-clean:\n  " + "\n  ".join(
        failures
    )


def _tier_codes(tier):
    return {m.value for m in TIER_MODULES.get(tier, set())} | {
        f.value for f in TIER_FEATURES.get(tier, set())
    }


def _wrong_for_tier(tier, method, path, response):
    detail = tier_walk.license_error(response)
    if detail is None:
        return None
    code = detail.get("module") or detail.get("feature")
    if code is None:  # "any Pro+ license" (requires_pro_plus)
        entitled = tier != LicenseTier.COMMUNITY
    else:
        entitled = code in _tier_codes(tier)
    expected = 503 if entitled else 402
    if response.status_code == expected:
        return None
    return f"{method} {path} -> {response.status_code} for {code!r} (want {expected})"


@pytest.mark.parametrize(
    "tier",
    [LicenseTier.PROFESSIONAL, LicenseTier.ENTERPRISE, LicenseTier.MULTITENANT_SAAS],
)
def test_each_tier_opens_exactly_its_own_modules(edition, tier):
    answers = _walk(edition, tier)
    failures = _server_errors(answers, licensed=True)
    for method, path, response in answers:
        wrong = _wrong_for_tier(tier, method, path, response)
        if wrong:
            failures.append(wrong)
    assert not failures, f"{tier.value}: gates disagree with the tier:\n  " + (
        "\n  ".join(failures)
    )


def test_community_backups_are_untouched_and_pro_plus_backups_refuse(edition):
    answers = _walk(edition, LicenseTier.COMMUNITY)
    walked = {(method, path) for method, path, _response in answers}
    assert PRO_PLUS_BACKUP <= walked, PRO_PLUS_BACKUP - walked  # no stale entry
    failures = []
    for method, path, response in answers:
        if "backup" not in path or path.startswith("/api/auth/"):
            continue
        # A federated site's backup STATUS (27.1) is a federation route, gated
        # with the rest of federation, not a backup route.
        if "/federation/" in path:
            continue
        status = response.status_code
        if (method, path) in DEPENDS_ON_STATE:
            continue
        if (method, path) in PRO_PLUS_BACKUP:
            if status != 402:
                failures.append(f"Pro+ {method} {path} -> {status}, want 402")
        elif status == 402 or status >= 500:
            failures.append(f"Community {method} {path} -> {status}")
    assert not failures, "\n  ".join(["Backups by edition:"] + failures)


def _put(test_client, url, body):
    return test_client.put(url, json=body).status_code


def test_phase_25_gates_that_depend_on_what_is_asked(edition):
    """Gates the walk cannot see because they depend on the body: asking for
    a Pro+ setting is 402, the same call without it is Community."""
    host = f"/api/v1/host/{tier_walk.SAMPLE_ID}/backup-policy"
    target = f"/api/v1/backups/targets/{tier_walk.SAMPLE_ID}"
    with edition(LicenseTier.COMMUNITY) as test_client:
        # Grandfather-father-son retention and scheduled verification.
        assert _put(test_client, host, {"keep_last": 7}) == 200
        assert _put(test_client, host, {"keep_last": 7, "keep_daily": 7}) == 402
        assert _put(test_client, host, {"verify_interval_days": 30}) == 402
        # restate-proxy is a Community transport; bandwidth by hour is Pro+,
        # and clearing the rules stays possible after a lapse.
        proxy = {"transport": "proxy", "proxy_host": "nas.walk.example"}
        assert _put(test_client, target + "/transport", proxy) == 200
        assert (
            _put(test_client, target + "/proxy-bandwidth", {"rules": ["20MiB/s"]})
            == 402
        )
        assert _put(test_client, target + "/proxy-bandwidth", {"rules": []}) == 200
        # Agent mutual TLS is Community.
        assert (
            _put(
                test_client,
                "/api/v1/agent-certificates",
                {"mode": "enforced", "force": True},
            )
            == 200
        )
        # An air-gap ingest needs the repository engine: queued unlicensed
        # it would never run.
        ingest = test_client.post("/api/v1/airgap/repository/ingest-device")
        assert ingest.status_code == 402
        # Package-manager repair and Ubuntu Pro attach are Community.
        repair = test_client.post(
            "/api/v1/hosts/repair-package-manager",
            json={"host_ids": [tier_walk.SAMPLE_ID]},
        )
        assert repair.status_code == 200
        attach = test_client.post(
            f"/api/v1/host/{tier_walk.SAMPLE_ID}/ubuntu-pro/attach",
            json={"token": "C1234567890"},
        )
        assert attach.status_code != 402


@pytest.mark.parametrize(
    "edition_tier", [LicenseTier.COMMUNITY, LicenseTier.PROFESSIONAL]
)
def test_a_tenant_edition_narrows_a_saas_license(edition, edition_tier):
    """Multi-tenancy (13.1.J): a SaaS-licensed server gates each tenant by
    its own edition, so a Community or Professional tenant must see exactly
    what a Community or Professional license would -- 402 above its tier."""
    with patch(
        "backend.services.tenant_edition.edition_for_active_tenant",
        return_value=edition_tier.value,
    ):
        answers = _walk(edition, LicenseTier.MULTITENANT_SAAS)
    failures = _server_errors(answers, licensed=True)
    for method, path, response in answers:
        wrong = _wrong_for_tier(edition_tier, method, path, response)
        if wrong:
            failures.append(wrong)
    assert not failures, f"{edition_tier.value} tenant:\n  " + "\n  ".join(failures)
