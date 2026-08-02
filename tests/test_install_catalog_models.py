# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 18.2 S3 install-source catalog models (OSS half).

The engine owns the CRUD and boot-resolution logic; what lives here is the
schema plus the netboot lifecycle rule that keeps a finished machine from
reinstalling itself, and the serialisation rule that keeps the answer-file
bearer token out of API responses.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import uuid
from datetime import datetime, timedelta, timezone

from backend.persistence.models.provisioning import (
    INSTALL_ASSIGNMENT_STATES,
    INSTALL_TEMPLATE_TYPES,
    HostInstallAssignment,
    InstallSource,
)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _source(**kw):
    base = {
        "id": uuid.uuid4(),
        "name": "ubuntu-24.04",
        "os_family": "ubuntu",
        "version": "24.04",
        "arch": "x86_64",
        "kernel_path": "u24/linux",
        "initrd_path": "u24/initrd",
        "install_tree_url": "http://mirror/u24",
        "template_type": "autoinstall",
        "enabled": True,
    }
    base.update(kw)
    return InstallSource(**base)


def _assignment(**kw):
    base = {
        "id": uuid.uuid4(),
        "mac_address": "52:54:00:99:09:01",
        "install_source_id": uuid.uuid4(),
        "state": "assigned",
        "params": {},
    }
    base.update(kw)
    return HostInstallAssignment(**base)


class TestInstallSource:
    def test_to_dict_shape(self):
        row = _source(boot_args="console=ttyS0")
        out = row.to_dict()
        assert out["os_family"] == "ubuntu"
        assert out["template_type"] == "autoinstall"
        assert out["boot_args"] == "console=ttyS0"
        assert out["mirror_repository_id"] is None

    def test_mirror_provenance_serialises_as_string(self):
        mirror_id = uuid.uuid4()
        out = _source(mirror_repository_id=mirror_id).to_dict()
        assert out["mirror_repository_id"] == str(mirror_id)

    def test_template_types_vocabulary(self):
        assert set(INSTALL_TEMPLATE_TYPES) == {
            "autoinstall",
            "preseed",
            "kickstart",
            "autoyast",
            "bsdinstall",
        }

    def test_freebsd_source_may_omit_initrd(self):
        """FreeBSD netboots pxeboot + an mfsroot, not a Linux kernel+initrd."""
        out = _source(
            os_family="freebsd",
            template_type="bsdinstall",
            kernel_path="fbsd/pxeboot",
            initrd_path=None,
        ).to_dict()
        assert out["initrd_path"] is None


class TestNetbootArmed:
    def test_armed_states(self):
        for state in ("assigned", "building", "failed"):
            assert _assignment(state=state).netboot_armed() is True

    def test_installed_disarms_netboot(self):
        """THE lifecycle rule: without it, a netboot-first machine reinstalls
        itself on every reboot and wipes the OS it just installed."""
        assert _assignment(state="installed").netboot_armed() is False

    def test_failed_stays_armed_for_a_retry(self):
        assert _assignment(state="failed").netboot_armed() is True

    def test_states_vocabulary(self):
        assert set(INSTALL_ASSIGNMENT_STATES) == {
            "assigned",
            "building",
            "installed",
            "failed",
        }


class TestAssignmentToDict:
    def test_never_serialises_the_bearer_token(self):
        """The boot token guards the answer file (which carries an enrollment
        token).  It must not leak through the operator API."""
        out = _assignment(boot_token="super-secret-value").to_dict()
        assert "boot_token" not in out
        assert out["has_boot_token"] is True
        assert "super-secret-value" not in str(out)

    def test_reports_absent_token(self):
        assert _assignment(boot_token=None).to_dict()["has_boot_token"] is False

    def test_exposes_expiry_and_armed_state(self):
        expires = _now() + timedelta(hours=6)
        out = _assignment(state="installed", boot_token_expires_at=expires).to_dict()
        assert out["boot_token_expires_at"] == expires.isoformat()
        assert out["netboot_armed"] is False

    def test_placement_ids_serialise(self):
        site, group = uuid.uuid4(), uuid.uuid4()
        out = _assignment(site_id=site, access_group_id=group).to_dict()
        assert out["site_id"] == str(site)
        assert out["access_group_id"] == str(group)

    def test_optional_fields_default_to_none(self):
        out = _assignment().to_dict()
        for key in (
            "partition_template_id",
            "finish_template_id",
            "hostname",
            "site_id",
            "access_group_id",
            "last_boot_at",
        ):
            assert out[key] is None
