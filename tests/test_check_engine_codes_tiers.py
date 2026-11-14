# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""scripts/check_engine_codes.py: the cross-repo tier gate (edition audit,
2026-11-14) reads the generator's text the way the gate does."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_engine_codes.py"
_spec = importlib.util.spec_from_file_location("check_engine_codes", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _generator(pro, ent, modules):
    def listing(codes):
        return "".join(f'    "{code}",  # "decoy" in a comment\n' for code in codes)

    module_lines = "".join(
        f'    "{code}": {{\n        "name": "x",\n        "tier": "{tier}",\n    }},\n'
        for code, tier in modules.items()
    )
    return (
        f"PROFESSIONAL_FEATURES = [\n{listing(pro)}]\n\n"
        f"ENTERPRISE_FEATURES = PROFESSIONAL_FEATURES + [\n{listing(ent)}]\n\n"
        f"MODULES = {{\n{module_lines}}}\n"
    )


def test_both_feature_blocks_are_read_and_comments_ignored():
    tiers = gate.issued_by_tier(_generator(["health"], ["sso"], {}))
    assert tiers == {"professional": {"health"}, "enterprise": {"health", "sso"}}


def test_module_tiers_are_read():
    text = _generator(
        [], [], {"vuln_engine": "professional", "fleet_engine": "enterprise"}
    )
    assert gate.module_tiers(text) == {
        "vuln_engine": "professional",
        "fleet_engine": "enterprise",
    }


def _real_issue():
    """What the generator issues today, rebuilt from TIER_FEATURES."""
    from backend.licensing.features import TIER_FEATURES, LicenseTier

    pro = sorted(f.value for f in TIER_FEATURES[LicenseTier.PROFESSIONAL])
    ent = sorted(
        f.value
        for f in TIER_FEATURES[LicenseTier.ENTERPRISE]
        - TIER_FEATURES[LicenseTier.PROFESSIONAL]
    )
    return pro, ent


def test_tables_that_agree_pass():
    pro, ent = _real_issue()
    text = _generator(pro, ent, {"fleet_engine": "enterprise"})
    assert gate.tier_disagreements(text) == []


def test_a_feature_issued_lower_than_this_server_tiers_it_is_reported():
    """The generator selling an Enterprise capability at Professional."""
    pro, ent = _real_issue()
    text = _generator(pro + ["fips_mode"], [c for c in ent if c != "fips_mode"], {})
    assert any("'fips_mode'" in p for p in gate.tier_disagreements(text))


def test_a_feature_issued_higher_than_this_server_tiers_it_is_reported():
    """The reporting bug: "reports" issued at Professional, tiered here at
    Enterprise only, so a Professional tenant edition lost its reports."""
    pro, ent = _real_issue()
    text = _generator([c for c in pro if c != "reports"], ent + ["reports"], {})
    assert any("'reports'" in p for p in gate.tier_disagreements(text))


def test_a_module_tier_mismatch_is_reported():
    pro, ent = _real_issue()
    text = _generator(pro, ent, {"fleet_engine": "professional"})
    assert any("'fleet_engine'" in p for p in gate.tier_disagreements(text))


def test_an_engine_gate_no_license_can_open_is_reported(monkeypatch):
    monkeypatch.setattr(
        gate, "engine_gated_features", lambda: {"health_history": "health_engine"}
    )
    assert gate.never_issued(_generator(["health"], [], {})) == [
        "feature 'health_history' gated by health_engine is never issued"
    ]
    assert gate.never_issued(_generator(["health", "health_history"], [], {})) == []
