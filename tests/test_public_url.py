# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Emailed links must land on a port the console actually serves.

Invitation and password-reset emails carry the only URL some recipients ever
see. Three call sites built it independently and all three built it the same
wrong way: scheme from ``api.certFile`` (unset, because nginx holds the
certificate) and port from ``webui.port`` (3000, which nginx no longer listens
on). The result was ``http://host:3000/accept-invitation`` -- wrong scheme,
closed port -- for every deployment following the shipped configuration.
"""

import pytest

from backend.config.public_url import build_public_base_url


def host():
    return "console.example.com"


# ---------------------------------------------------------------------------
# The two failures this replaces
# ---------------------------------------------------------------------------


def test_scheme_is_https_even_though_the_backend_holds_no_certificate():
    """nginx terminates TLS, so api.certFile is empty on a correct install.

    Deriving the scheme from it produced http:// links to an HTTPS-only site.
    """
    url = build_public_base_url({"api": {}, "webui": {}}, host)
    assert url.startswith("https://"), url


def test_default_port_is_not_pinned_into_the_link():
    """webui.port 3000 pointed at a port nginx stopped serving.

    With one origin on 443 the port simply does not belong in the URL.
    """
    url = build_public_base_url({"webui": {"port": 443}}, host)
    assert url == "https://console.example.com"
    assert ":443" not in url


# ---------------------------------------------------------------------------
# Explicit configuration wins
# ---------------------------------------------------------------------------


def test_public_url_is_used_verbatim():
    """The only correct answer for SaaS or any reverse-proxied deployment.

    The name customers use has nothing to do with the server's own hostname, so
    no amount of derivation can find it.
    """
    url = build_public_base_url(
        {"webui": {"public_url": "https://sysmanage.customer.example", "port": 3000}},
        host,
    )
    assert url == "https://sysmanage.customer.example"


def test_trailing_slash_is_stripped_so_paths_do_not_double_up():
    url = build_public_base_url({"webui": {"public_url": "https://x.example/"}}, host)
    assert url == "https://x.example"
    assert f"{url}/accept-invitation" == "https://x.example/accept-invitation"


def test_public_url_wins_even_over_a_non_default_port():
    url = build_public_base_url(
        {"webui": {"public_url": "https://x.example:8443", "port": 3000}}, host
    )
    assert url == "https://x.example:8443"


# ---------------------------------------------------------------------------
# Derivation fallback
# ---------------------------------------------------------------------------


def test_dev_mode_uses_http_and_the_vite_port():
    """A dev box with the UI on 3000 and no proxy still has to work."""
    url = build_public_base_url({"dev_mode": True, "webui": {"port": 3000}}, host)
    assert url == "http://console.example.com:3000"


def test_production_ignores_webui_port_entirely():
    """Absent the flag this is production: 443, and the port is not outward-facing.

    webui.port stays 3000 in the shipped templates because dev needs it; letting
    it leak into a production link is what produced http://host:3000 in the
    first place.
    """
    url = build_public_base_url({"webui": {"port": 3000}}, host)
    assert url == "https://console.example.com"


def test_a_forgotten_flag_fails_towards_https_not_plaintext():
    """The default direction is the whole point.

    A missing or misspelt setting must not silently downgrade a real deployment;
    the worst case for guessing https is a link that redirects.
    """
    for config in ({}, {"webui": {}}, {"dev_mode": False}, {"dev_moed": True}):
        assert build_public_base_url(config, host).startswith("https://"), config


@pytest.mark.parametrize("bad", ["", "abc", None])
def test_unparseable_port_is_ignored_rather_than_crashing_the_email(bad):
    """A bad port must not be why a password-reset email fails to send."""
    url = build_public_base_url({"dev_mode": True, "webui": {"port": bad}}, host)
    assert url == "http://console.example.com"


def test_missing_config_sections_do_not_explode():
    assert build_public_base_url({}, host) == "https://console.example.com"
    assert build_public_base_url(None, host) == "https://console.example.com"


def test_no_resolver_still_returns_something_usable():
    assert build_public_base_url({}) == "https://localhost"
