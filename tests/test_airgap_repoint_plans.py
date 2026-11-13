# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Repointing an air-gapped site's hosts at its own repository, for every
package manager the collector mirrors (ROADMAP 25.9, 2026-11-13): before,
only apt hosts were pointed there, so "Equip for backup" on any other host
of an air-gapped site had nowhere to install restate from."""

import pytest

from backend.services import airgap_repoint_service as repoint

URL = "http://repo.site.lan/mirror/fedora/44"


def _argvs(plan):
    return [c["argv"] for c in plan["commands"]]


@pytest.mark.parametrize(
    "distro,kind,path",
    [
        ("ubuntu", "apt", "/etc/apt/sources.list.d/sysmanage-airgap.list"),
        ("fedora", "dnf", "/etc/yum.repos.d/sysmanage-airgap.repo"),
        ("rocky", "dnf", "/etc/yum.repos.d/sysmanage-airgap.repo"),
        ("opensuse-leap", "zypper", "/etc/zypp/repos.d/sysmanage-airgap.repo"),
        ("alpine", "apk", "/etc/apk/repositories"),
        ("freebsd", "pkg", "/usr/local/etc/pkg/repos/sysmanage-airgap.conf"),
    ],
)
def test_each_package_manager_gets_the_mirror_as_a_file(distro, kind, path):
    found_kind, plan = repoint.repoint_plan(distro, URL, "noble")
    assert found_kind == kind
    files = {f["path"]: f for f in plan["files"]}
    assert URL in files[path]["content"]
    assert files[path]["owner_uid"] == 0 and files[path]["permissions"] == "0644"


def test_no_shell_and_signatures_stay_on():
    """sudoers grants no shell, and the mirrors keep the distributions'
    signed packages and indexes."""
    for distro in ("ubuntu", "fedora", "opensuse-leap", "alpine", "freebsd"):
        _kind, plan = repoint.repoint_plan(distro, URL, "noble")
        for argv in _argvs(plan):
            assert argv[0] == "sudo" and argv[1] not in ("sh", "bash", "/bin/sh")
        text = "".join(f["content"] for f in plan["files"])
        assert "gpgcheck=0" not in text and "trusted=yes" not in text
        assert 'signature_type: "none"' not in text


def test_upstream_repositories_are_switched_off():
    _k, dnf = repoint.repoint_plan("fedora", URL, "")
    argvs = _argvs(dnf)
    # every repository off, then ours on again (the file is deployed first)
    assert argvs.index(
        ["sudo", "dnf", "config-manager", "--set-disabled", "*"]
    ) < argvs.index(
        ["sudo", "dnf", "config-manager", "--set-enabled", "sysmanage-airgap"]
    )
    assert argvs[-1] == ["sudo", "dnf", "makecache"]
    _k, zypper = repoint.repoint_plan("sles", URL, "")
    assert [
        "sudo",
        "zypper",
        "--non-interactive",
        "modifyrepo",
        "--all",
        "--disable",
    ] in _argvs(zypper)
    _k, pkg = repoint.repoint_plan("freebsd", URL, "")
    off = next(f for f in pkg["files"] if f["path"].endswith("/FreeBSD.conf"))
    assert "FreeBSD: { enabled: no }" in off["content"]
    _k, apk = repoint.repoint_plan("alpine", URL, "")
    assert apk["files"][0]["content"] == URL + "\n"  # the only repository


def test_an_unknown_distribution_is_left_alone():
    assert repoint.repoint_plan("plan9", URL, "") is None
