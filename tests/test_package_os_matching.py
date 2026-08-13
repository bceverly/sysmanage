# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""An agent reports a DISTRIBUTION; the host record stores a PLATFORM.

``handle_packages_batch_start`` used to compare those field-for-field::

    if os_name != host.platform or os_version != host.platform_release:

An Ubuntu agent reports ``os_name="Ubuntu"``, ``os_version="26.04"`` while its
host row holds ``platform="Linux"``, ``platform_release="Ubuntu 26.04"``.  Those
never match, so EVERY Linux batch was rejected with ``os_mismatch`` and no
package row was ever written.

That failure is silent and self-perpetuating: the automatic collection trigger
(``is_new_os_version_combination``) fires when an OS/version has NO rows, so a
rejected catalog is immediately re-requested, rejected again, for ever.
Measured on the dev host 2026-08-06: 78,979 messages / 9.4 GB in eight days --
83% of everything the agent sent -- for a catalog that never landed.  Observed
live 2026-08-12: 1,023 batch payload messages received against 0 successful
batch starts, and zero Ubuntu rows in ``available_packages``.

FreeBSD masked it for two years: there the distribution and the platform are
both "FreeBSD", so the naive comparison accidentally passed -- which is why the
only rows in the table were FreeBSD's.

These tests pin the real-world field values, not a simplified model of them.
"""

import pytest

from backend.api.package_host_selector import (
    BSD_VARIANTS,
    LINUX_DISTROS,
    host_matches_os,
)


class _Host:
    """Minimal stand-in: only the two fields the check reads."""

    def __init__(self, platform, platform_release):
        self.platform = platform
        self.platform_release = platform_release


def test_ubuntu_agent_matches_its_own_linux_host():
    """The exact case that produced 9.4 GB of rejected traffic."""
    host = _Host("Linux", "Ubuntu 26.04")
    assert host_matches_os(host, "Ubuntu", "26.04")


@pytest.mark.parametrize("distro", LINUX_DISTROS)
def test_every_linux_distro_matches_its_host_row(distro):
    """A distro added to the list must work, not just the one that was found."""
    host = _Host("Linux", f"{distro} 1.2")
    assert host_matches_os(host, distro, "1.2")


def test_freebsd_still_matches():
    """The case that accidentally worked must keep working."""
    assert host_matches_os(_Host("FreeBSD", "15.0-RELEASE-p8"), "FreeBSD", "15.0")


@pytest.mark.parametrize("bsd", BSD_VARIANTS)
def test_bsd_variants_match_on_platform(bsd):
    assert host_matches_os(_Host(bsd, "14.2-RELEASE"), bsd, "14.2")


def test_windows_matches():
    assert host_matches_os(_Host("Windows", "2022"), "Windows", "2022")


def test_macos_matches_on_platform_alone():
    """platform_release is a marketing name ("Sequoia 15.6") the agent never sends."""
    assert host_matches_os(_Host("macOS", "Sequoia 15.6"), "macOS", "15.6")


def test_a_genuine_mismatch_is_still_rejected():
    """The check must still do its job: this is not a rubber stamp.

    A Fedora agent reporting against an Ubuntu host row is exactly what the
    validation exists to catch -- the catalog is keyed by OS, so accepting it
    would corrupt another OS's package list.
    """
    assert not host_matches_os(_Host("Linux", "Ubuntu 26.04"), "Fedora", "42")


def test_wrong_version_of_the_right_distro_is_rejected():
    assert not host_matches_os(_Host("Linux", "Ubuntu 26.04"), "Ubuntu", "24.04")


def test_freebsd_agent_against_a_linux_host_is_rejected():
    assert not host_matches_os(_Host("Linux", "Ubuntu 26.04"), "FreeBSD", "15.0")


@pytest.mark.parametrize(
    "platform,release",
    [(None, None), ("", ""), ("Linux", None), (None, "Ubuntu 26.04"), ("Linux", "")],
)
def test_unknown_host_os_is_permissive(platform, release):
    """A host that has not yet reported platform details must not be rejected.

    Rejecting here reintroduces exactly the silent, self-perpetuating loop this
    fix removes: the packages never land, so they are requested again.
    """
    assert host_matches_os(_Host(platform, release), "Ubuntu", "26.04")


def test_release_may_carry_a_suffix():
    """platform_release is matched by prefix, as find_hosts_for_os does with LIKE."""
    assert host_matches_os(_Host("Linux", "Ubuntu 26.04.1 LTS"), "Ubuntu", "26.04")
    assert host_matches_os(_Host("FreeBSD", "15.0-RELEASE-p8"), "FreeBSD", "15.0")


def test_legacy_host_shape_with_distro_as_platform_is_accepted():
    """Some host rows carry the distro as the platform ("Ubuntu" / "22.04").

    Accepted on purpose: a false reject is the expensive direction, because it
    reproduces the silent re-request loop.  The genuine-mismatch tests above
    still pass, so this tolerance does not blunt the check.
    """
    assert host_matches_os(_Host("Ubuntu", "22.04"), "Ubuntu", "22.04")
    assert not host_matches_os(_Host("Ubuntu", "22.04"), "Fedora", "42")
