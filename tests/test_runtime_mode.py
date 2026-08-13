# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""One flag decides production-vs-development, and its default is production.

The direction matters more than the flag: a missing or misspelt setting must
fail toward TLS on 443, because the worst case there is a link that redirects.
Defaulting the other way would let a forgotten line downgrade a real deployment
to plaintext.
"""

import pytest

from backend.config.runtime_mode import is_dev_mode


def test_absent_flag_means_production():
    assert is_dev_mode({}) is False
    assert is_dev_mode(None) is False
    assert is_dev_mode({"webui": {"port": 3000}}) is False


def test_a_typo_means_production_not_development():
    """`dev_moed: true` must not quietly turn TLS off."""
    assert is_dev_mode({"dev_moed": True}) is False
    assert is_dev_mode({"devmode": True}) is False


@pytest.mark.parametrize("value", [True, "true", "True", "yes", "on", "1"])
def test_truthy_spellings_enable_dev_mode(value):
    """YAML gives real booleans, but a quoted "true" should still count."""
    assert is_dev_mode({"dev_mode": value}) is True


@pytest.mark.parametrize("value", [False, "false", "no", "off", "0", "", None])
def test_falsey_spellings_stay_in_production(value):
    assert is_dev_mode({"dev_mode": value}) is False


@pytest.mark.parametrize("key", ["dev_mode", "development_mode", "development"])
def test_tolerated_spellings_of_the_key(key):
    """A flag that silently does nothing is worse than a permissive one."""
    assert is_dev_mode({key: True}) is True
