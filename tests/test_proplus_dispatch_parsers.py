"""
Tests for the result-parsing helpers in ``backend.services.proplus_dispatch``.

Covers the parsers that translate engine-plan stdout (sectioned shell
output from build_check_virtualization_support_plan and
build_list_child_hosts_plan) into the structured dicts the legacy result
handlers consume.  These parsers are load-bearing — without them the
engine-path probes silently no-op.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access

from backend.services import proplus_dispatch as pd

# ---------------------------------------------------------------------------
# _split_section_blocks
# ---------------------------------------------------------------------------


class TestSplitSectionBlocks:
    def test_splits_by_marker(self):
        text = "===A===\nfoo\nbar\n===B===\nbaz\n"
        out = pd._split_section_blocks(text)
        assert out["a"] == "foo\nbar"
        assert out["b"] == "baz"

    def test_lowercases_section_names(self):
        out = pd._split_section_blocks("===KVM===\nx\n===LXD===\ny\n")
        assert "kvm" in out
        assert "lxd" in out
        assert "KVM" not in out

    def test_empty_section(self):
        out = pd._split_section_blocks("===A===\n===B===\nbaz\n")
        assert out["a"] == ""
        assert out["b"] == "baz"

    def test_no_sections(self):
        out = pd._split_section_blocks("just some stdout\nwith no markers\n")
        assert out == {}


# ---------------------------------------------------------------------------
# _normalize_status
# ---------------------------------------------------------------------------


class TestNormalizeStatus:
    def test_running_variants(self):
        for state in ("Running", "running", "RUNNING", "Running (12345)"):
            assert pd._normalize_status(state) == "running"

    def test_stopped_variants(self):
        for state in ("Stopped", "stopped", "shut off", "exited", "off"):
            assert pd._normalize_status(state) == "stopped"

    def test_paused_variants(self):
        for state in ("Paused", "paused", "frozen"):
            assert pd._normalize_status(state) == "paused"

    def test_empty_returns_unknown(self):
        assert pd._normalize_status("") == "unknown"
        assert pd._normalize_status("   ") == "unknown"


# ---------------------------------------------------------------------------
# Per-section parsers
# ---------------------------------------------------------------------------


class TestParseLxdSection:
    def test_empty_returns_empty(self):
        assert pd._parse_lxd_section("") == []
        assert pd._parse_lxd_section("[]") == []

    def test_invalid_json_returns_empty(self):
        # Non-JSON text shouldn't crash — just empty list.
        assert pd._parse_lxd_section("not json at all") == []

    def test_extracts_name_status_type(self):
        text = (
            '[{"name":"lxd-2204","status":"Running","type":"container",'
            '"architecture":"x86_64"}]'
        )
        out = pd._parse_lxd_section(text)
        assert len(out) == 1
        assert out[0]["child_name"] == "lxd-2204"
        assert out[0]["child_type"] == "lxd"
        assert out[0]["status"] == "running"
        assert out[0]["type"] == "container"
        assert out[0]["architecture"] == "x86_64"

    def test_skips_entries_without_name(self):
        out = pd._parse_lxd_section('[{"status":"Running"}]')
        assert out == []


class TestParseKvmSection:
    def test_parses_virsh_list_table(self):
        text = (
            " Id   Name              State\n"
            "-----------------------------------\n"
            " 1    test-vm           running\n"
            " -    other-vm          shut off\n"
        )
        out = pd._parse_kvm_section(text)
        assert len(out) == 2
        assert out[0]["child_name"] == "test-vm"
        assert out[0]["status"] == "running"
        assert out[1]["child_name"] == "other-vm"
        assert out[1]["status"] == "stopped"

    def test_skips_header_and_separator(self):
        text = "Id   Name   State\n---\n"
        assert pd._parse_kvm_section(text) == []

    def test_empty_returns_empty(self):
        assert pd._parse_kvm_section("") == []


class TestParseBhyveSection:
    def test_parses_vm_list_table_with_pid(self):
        text = (
            "NAME       DATASTORE    LOADER     CPU  MEMORY  VNC      AUTO    STATE\n"
            "myvm       default      uefi       2    2G      -        Yes     Running (12345)\n"
            "otherbsd   default      uefi       1    1G      -        No      Stopped\n"
        )
        out = pd._parse_bhyve_section(text)
        assert len(out) == 2
        assert out[0]["child_name"] == "myvm"
        # The "(12345)" is the PID; parser must skip past it to find "Running".
        assert out[0]["status"] == "running"
        assert out[1]["child_name"] == "otherbsd"
        assert out[1]["status"] == "stopped"

    def test_skips_blank_lines(self):
        text = "NAME  STATE\n\n\nmyvm  Running\n"
        out = pd._parse_bhyve_section(text)
        assert len(out) == 1


class TestParseVmmSection:
    def test_parses_vmctl_status(self):
        text = (
            "   ID   PID VCPUS  MAXMEM  CURMEM     TTY        OWNER NAME\n"
            "    1 12345     2   2.0G   1.0G    /dev/ttyp0     root  bsdvm\n"
        )
        out = pd._parse_vmm_section(text)
        assert len(out) == 1
        assert out[0]["child_name"] == "bsdvm"
        # Presence in vmctl status implies running.
        assert out[0]["status"] == "running"

    def test_empty_table_returns_empty(self):
        text = "   ID   PID VCPUS  MAXMEM  CURMEM     TTY        OWNER NAME\n"
        assert pd._parse_vmm_section(text) == []


class TestParseWslSection:
    def test_parses_wsl_list_verbose(self):
        text = (
            "  NAME            STATE           VERSION\n"
            "* Ubuntu          Running         2\n"
            "  Ubuntu-22.04    Stopped         2\n"
        )
        out = pd._parse_wsl_section(text)
        assert len(out) == 2
        assert out[0]["child_name"] == "Ubuntu"
        assert out[0]["status"] == "running"
        assert out[1]["child_name"] == "Ubuntu-22.04"
        assert out[1]["status"] == "stopped"

    def test_strips_default_distro_marker(self):
        # The leading '*' marks the default distro; parser must strip it
        # so the name doesn't end up "*Ubuntu".
        text = "  NAME    STATE\n* Ubuntu  Running\n"
        out = pd._parse_wsl_section(text)
        assert out[0]["child_name"] == "Ubuntu"


# ---------------------------------------------------------------------------
# _parse_list_child_hosts_stdout (end-to-end)
# ---------------------------------------------------------------------------


class TestParseListChildHostsStdout:
    def test_full_sectioned_input(self):
        text = (
            "===LXD===\n"
            '[{"name":"ct1","status":"Running","type":"container"}]\n'
            "===KVM===\n"
            " Id   Name   State\n"
            "-----------------\n"
            " 1    vm1    running\n"
            "===BHYVE===\n"
            "NAME  DATASTORE  LOADER  CPU  MEMORY  VNC  AUTO  STATE\n"
            "bvm1  default    uefi    1    1G      -    No   Running (1)\n"
            "===VMM===\n"
            "   ID   PID VCPUS  MAXMEM  CURMEM     TTY        OWNER NAME\n"
            "    1     2     2   2.0G   1.0G    /dev/ttyp0    root  bsd1\n"
            "===WSL===\n"
            "  NAME    STATE    VERSION\n"
            "* Ubuntu  Running  2\n"
        )
        out = pd._parse_list_child_hosts_stdout(text)
        # One entry per hypervisor.
        names_by_type = {(c["child_type"], c["child_name"]) for c in out}
        assert ("lxd", "ct1") in names_by_type
        assert ("kvm", "vm1") in names_by_type
        assert ("bhyve", "bvm1") in names_by_type
        assert ("vmm", "bsd1") in names_by_type
        assert ("wsl", "Ubuntu") in names_by_type

    def test_missing_sections_handled(self):
        # Only LXD section present; other hypervisors absent.
        text = "===LXD===\n" '[{"name":"ct1","status":"Running"}]\n'
        out = pd._parse_list_child_hosts_stdout(text)
        assert len(out) == 1
        assert out[0]["child_type"] == "lxd"


# ---------------------------------------------------------------------------
# _parse_capability_probe_stdout
# ---------------------------------------------------------------------------


class TestParseCapabilityProbeStdout:
    def test_kvm_intel_with_full_install(self):
        text = (
            "===KVM===\n"
            "cpu:vmx\n"
            "devkvm:yes\n"
            "virsh:yes\n"
            "libvirtd:yes\n"
            "===LXD===\n"
            "lxc:no\n"
            "snap_lxd:no\n"
            "initialized:no\n"
            "===BHYVE===\n"
            "===VMM===\n"
            "===WSL===\n"
            "wsl:none\n"
        )
        out = pd._parse_capability_probe_stdout(text)
        assert "kvm" in out["supported_types"]
        assert out["capabilities"]["kvm"]["available"] is True
        assert out["capabilities"]["kvm"]["enabled"] is True
        assert out["capabilities"]["kvm"]["running"] is True
        # LXD section all "no" — should NOT be in supported_types.
        assert "lxd" not in out["supported_types"]
        # WSL "none" — not present.
        assert "wsl" not in out["supported_types"]

    def test_amd_cpu_detected(self):
        text = "===KVM===\ncpu:svm\ndevkvm:no\nvirsh:no\nlibvirtd:no\n"
        out = pd._parse_capability_probe_stdout(text)
        assert "kvm" in out["supported_types"]
        assert out["capabilities"]["kvm"]["available"] is True
        assert out["capabilities"]["kvm"]["needs_enable"] is True

    def test_no_virtualization_at_all(self):
        text = (
            "===KVM===\ncpu:none\ndevkvm:no\nvirsh:no\nlibvirtd:no\n"
            "===LXD===\nlxc:no\nsnap_lxd:no\ninitialized:no\n"
            "===BHYVE===\n"
            "===VMM===\n"
            "===WSL===\nwsl:none\n"
        )
        out = pd._parse_capability_probe_stdout(text)
        assert out["supported_types"] == []
        assert out["capabilities"] == {}

    def test_lxd_present(self):
        text = (
            "===KVM===\ncpu:none\ndevkvm:no\nvirsh:no\nlibvirtd:no\n"
            "===LXD===\nlxc:yes\nsnap_lxd:yes\ninitialized:yes\n"
            "===BHYVE===\n===VMM===\n===WSL===\nwsl:none\n"
        )
        out = pd._parse_capability_probe_stdout(text)
        assert "lxd" in out["supported_types"]
        assert out["capabilities"]["lxd"]["installed"] is True
        assert out["capabilities"]["lxd"]["initialized"] is True
        assert out["capabilities"]["lxd"]["needs_install"] is False
        assert out["capabilities"]["lxd"]["needs_init"] is False

    def test_bhyve_loaded(self):
        text = (
            "===KVM===\n===LXD===\n"
            "===BHYVE===\nvmm:loaded\nvmbhyve:yes\n"
            "===VMM===\n===WSL===\n"
        )
        out = pd._parse_capability_probe_stdout(text)
        assert "bhyve" in out["supported_types"]
        assert out["capabilities"]["bhyve"]["enabled"] is True
        assert out["capabilities"]["bhyve"]["installed"] is True

    def test_vmm_running(self):
        text = (
            "===KVM===\n===LXD===\n===BHYVE===\n"
            "===VMM===\nvmctl:yes\ndevvmm:yes\nvmd:running\n"
            "===WSL===\n"
        )
        out = pd._parse_capability_probe_stdout(text)
        assert "vmm" in out["supported_types"]
        assert out["capabilities"]["vmm"]["running"] is True
        assert out["capabilities"]["vmm"]["needs_enable"] is False


# ---------------------------------------------------------------------------
# Correlation map
# ---------------------------------------------------------------------------


class TestCorrelations:
    def test_register_and_pop_child_host(self):
        msg_id = "msg-1"
        pd.register_child_host_correlation(msg_id, "child-uuid", "start", "host-uuid")
        # pylint: disable=protected-access
        eng, primary, host = pd._pop_correlation(msg_id)
        assert eng == "child_host_op"
        assert primary == "start:child-uuid"
        assert host == "host-uuid"

    def test_register_host_op(self):
        msg_id = "msg-2"
        pd.register_host_op_correlation(msg_id, "init_kvm", "host-uuid")
        # pylint: disable=protected-access
        eng, primary, host = pd._pop_correlation(msg_id)
        assert eng == "host_op"
        assert primary == "init_kvm"
        assert host == "host-uuid"

    def test_pop_returns_none_for_unknown(self):
        # pylint: disable=protected-access
        assert pd._pop_correlation("never-registered") is None
