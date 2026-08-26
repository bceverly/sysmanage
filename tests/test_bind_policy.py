# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A wildcard API bind must be impossible to do accidentally and silently.

SysManage puts nginx on 80/443 and the API on loopback 8080. Change `api.host`
to a wildcard and the API is published directly -- bypassing TLS, the security
headers and the upgrade validation that live in the nginx config. Agent
registration is unauthenticated by design (a new agent has no credentials yet),
so an exposed API is an open enrollment endpoint served in cleartext.

Nothing said so before. The value sat in a YAML file and the server started
happily, which is how the agent config templates came to point at port 8080
instead of at 443.
"""

import logging

import pytest

from backend.config.bind_policy import (
    check_api_bind,
    is_loopback_bind,
    is_wildcard_bind,
)


@pytest.mark.parametrize(
    "host", ["0.0.0.0", "::", "[::]", "*", "", "  0.0.0.0  ", None]
)
def test_wildcard_forms_are_all_recognised(host):
    """Missing counts as a wildcard: some stacks treat absent as "everywhere"."""
    assert is_wildcard_bind(host) is True


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "LOCALHOST"])
def test_loopback_forms_are_recognised(host):
    assert is_wildcard_bind(host) is False
    assert is_loopback_bind(host) is True


def test_specific_public_address_is_not_a_wildcard():
    """Binding one real interface is deliberate; it is not the accident."""
    assert is_wildcard_bind("10.0.0.5") is False
    assert is_loopback_bind("10.0.0.5") is False


def test_loopback_bind_is_silent(caplog):
    """The shipped default must not nag."""
    with caplog.at_level(logging.INFO):
        exposed = check_api_bind({"api": {"host": "localhost", "port": 8080}})
    assert exposed is False
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_wildcard_bind_warns_with_the_reason_and_the_fix(caplog):
    with caplog.at_level(logging.WARNING):
        exposed = check_api_bind({"api": {"host": "0.0.0.0", "port": 8080}})

    assert exposed is True
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1

    message = warnings[0].getMessage()
    # It has to say WHAT is wrong, WHY it matters, and WHAT to do -- a warning
    # that only says "bound to 0.0.0.0" gets scrolled past.
    assert "ALL interfaces" in message
    assert "unauthenticated" in message
    assert "api.host" in message and "localhost" in message
    assert "allow_public_bind" in message


def test_acknowledgement_silences_the_warning_without_disabling_the_check(caplog):
    """Legitimate cases exist: dev without a proxy, containers, external TLS.

    The escape hatch records a decision rather than switching the check off, and
    the function still reports the bind as exposed so callers cannot be misled.
    """
    with caplog.at_level(logging.INFO):
        exposed = check_api_bind(
            {"api": {"host": "0.0.0.0", "port": 8080, "allow_public_bind": True}}
        )
    assert exposed is True, "still exposed -- acknowledgement is not mitigation"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_missing_api_section_does_not_explode():
    """Startup checks must never be the thing that stops a server booting.

    An absent api.host resolves to the production default (localhost), which is
    what actually gets bound -- so the honest answer is "not exposed". This once
    asserted True, back when the check read the raw value and treated a missing
    one as a wildcard.
    """
    assert check_api_bind({}) is False
    assert check_api_bind(None) is False


def test_every_shipped_server_template_binds_loopback():
    """The templates are the defaults most installs actually run with.

    One of them shipping a wildcard would publish the API on every machine that
    used it, which is precisely the failure this module exists to make visible.
    """
    from pathlib import Path  # noqa: PLC0415

    import yaml  # noqa: PLC0415

    repo = Path(__file__).resolve().parent.parent
    templates = sorted(repo.glob("installer/**/sysmanage.yaml.example"))
    assert templates, "no shipped server templates found"

    offenders = []
    for template in templates:
        raw = yaml.safe_load(template.read_text(encoding="utf-8")) or {}
        host = (raw.get("api") or {}).get("host")
        if is_wildcard_bind(host):
            offenders.append(f"{template.relative_to(repo)}: api.host = {host!r}")
    assert (
        not offenders
    ), "these shipped templates publish the API on every interface:\n  " + "\n  ".join(
        offenders
    )


# ---------------------------------------------------------------------------
# Dev mode must have no friction
# ---------------------------------------------------------------------------


def test_dev_mode_binds_all_interfaces_so_lan_agents_just_work():
    """The point of dev mode is that things connect to it.

    There is no reverse proxy in dev, so the API *is* the endpoint. A loopback
    bind makes it unreachable from another machine by definition -- and the
    symptom is a laptop that cannot see the server for a reason buried in a YAML
    file nobody has opened.
    """
    from backend.config.bind_policy import resolve_api_bind_host  # noqa: PLC0415

    # Even though the shipped templates say localhost, dev mode upgrades it.
    assert (
        resolve_api_bind_host({"dev_mode": True, "api": {"host": "localhost"}})
        == "0.0.0.0"
    )
    assert resolve_api_bind_host({"dev_mode": True, "api": {}}) == "0.0.0.0"


def test_production_keeps_the_configured_loopback_bind():
    from backend.config.bind_policy import resolve_api_bind_host  # noqa: PLC0415

    assert resolve_api_bind_host({"api": {"host": "localhost"}}) == "localhost"
    assert resolve_api_bind_host({"api": {}}) == "localhost"
    assert resolve_api_bind_host({}) == "localhost"


def test_a_deliberately_chosen_interface_is_respected_in_dev():
    """Someone naming one interface knows which one they want."""
    from backend.config.bind_policy import resolve_api_bind_host  # noqa: PLC0415

    assert (
        resolve_api_bind_host({"dev_mode": True, "api": {"host": "10.0.0.5"}})
        == "10.0.0.5"
    )


def test_dev_mode_does_not_warn_about_the_wildcard_it_chose(caplog):
    """Crying wolf on every dev start is how people learn to ignore warnings."""
    with caplog.at_level(logging.INFO):
        check_api_bind({"dev_mode": True, "api": {"host": "0.0.0.0", "port": 8080}})
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_production_still_warns_about_a_wildcard(caplog):
    """The warning must survive the dev-mode carve-out."""
    with caplog.at_level(logging.WARNING):
        check_api_bind({"api": {"host": "0.0.0.0", "port": 8080}})
    assert [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_the_guard_reports_the_effective_bind_not_the_configured_one(caplog):
    """Dev mode binds 0.0.0.0 even though the file says localhost.

    A startup line claiming "localhost" while the socket answers on every
    interface is worse than no line at all.
    """
    caplog.set_level(logging.INFO, logger="backend.config.bind_policy")
    check_api_bind({"dev_mode": True, "api": {"host": "localhost", "port": 8080}})
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "0.0.0.0" in messages, messages
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
