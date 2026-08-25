# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Pure helpers behind child-host creation dispatch.

These decide what a spawned VM is told about itself -- its DNS, its base
image, its bootstrap credentials -- and every one of them fails QUIETLY when
it gets a shape it did not expect: a wrong DNS list means a guest that boots
and cannot resolve, a wrong base-image name means a re-download per create,
and empty FreeBSD material means an unreachable guest.  None of that raises,
so none of it shows up without tests like these.
"""

from unittest.mock import patch

import pytest

from backend.api.child_host_creation_dispatch import (
    _adapter_dns_servers,
    _build_agent_config_yaml,
    _build_kvm_create_request,
    _derive_kvm_base_image_path,
    _extract_adapter_candidates,
    _first_param_or,
    _freebsd_bootstrap_material,
    _is_freebsd_distribution,
    _param_or,
    _resolve_parent_dns,
)


class TestAdapterExtraction:
    """``network_details`` shape varies by hardware collector."""

    def test_a_flat_list_is_already_the_adapter_list(self):
        payload = [{"name": "eth0"}, {"name": "eth1"}]
        assert _extract_adapter_candidates(payload) == payload

    @pytest.mark.parametrize("key", ["adapters", "interfaces", "network_adapters"])
    def test_each_known_wrapper_key_is_unwrapped(self, key):
        adapters = [{"name": "eth0"}]
        assert _extract_adapter_candidates({key: adapters}) == adapters

    def test_a_bare_adapter_dict_is_treated_as_one_adapter(self):
        # A single-NIC host may report the adapter itself at the top level;
        # returning [] here would silently lose its DNS.
        payload = {"name": "eth0", "dns_servers": ["10.0.0.1"]}
        assert _extract_adapter_candidates(payload) == [payload]

    @pytest.mark.parametrize("payload", [None, "eth0", 42])
    def test_a_non_dict_non_list_yields_nothing(self, payload):
        assert _extract_adapter_candidates(payload) == []

    def test_a_wrapper_key_holding_a_non_list_is_ignored(self):
        # {"adapters": "eth0"} must not be mistaken for a list of adapters.
        payload = {"adapters": "eth0"}
        assert _extract_adapter_candidates(payload) == [payload]


class TestAdapterDns:
    @pytest.mark.parametrize("key", ["dns_servers", "dns", "nameservers"])
    def test_each_known_dns_key_is_read(self, key):
        assert _adapter_dns_servers({key: ["10.0.0.1"]}) == ["10.0.0.1"]

    def test_a_bare_string_is_accepted_as_one_server(self):
        assert _adapter_dns_servers({"dns": "10.0.0.1"}) == ["10.0.0.1"]

    def test_duplicates_are_collapsed_but_order_is_kept(self):
        # Order matters: the first resolver is the one the guest will use.
        adapter = {"dns_servers": ["10.0.0.1", "10.0.0.2"], "dns": ["10.0.0.1"]}
        assert _adapter_dns_servers(adapter) == ["10.0.0.1", "10.0.0.2"]

    def test_empty_and_non_string_entries_are_dropped(self):
        assert _adapter_dns_servers({"dns_servers": ["", None, 5, "10.0.0.1"]}) == [
            "10.0.0.1"
        ]

    @pytest.mark.parametrize("adapter", [None, "eth0", 42, {}])
    def test_junk_yields_no_servers_rather_than_raising(self, adapter):
        assert _adapter_dns_servers(adapter) == []


class TestResolveParentDns:
    """The guest inherits the parent's resolver, or the engine's default."""

    def test_no_host_id_short_circuits(self):
        assert _resolve_parent_dns("") == []

    def test_a_host_with_no_payload_yields_the_engine_default(self):
        with patch(
            "backend.api.child_host_creation_dispatch._load_network_details_payload",
            return_value=None,
        ):
            assert _resolve_parent_dns("h1") == []

    def test_the_first_adapter_WITH_dns_wins(self):
        # Not simply the first adapter: a management NIC with no DNS must not
        # shadow the one that actually has a resolver, or the guest gets the
        # public default on a split-horizon network.
        payload = {
            "adapters": [
                {"name": "eth0"},
                {"name": "eth1", "dns_servers": ["10.0.0.53"]},
            ]
        }
        with patch(
            "backend.api.child_host_creation_dispatch._load_network_details_payload",
            return_value=payload,
        ):
            assert _resolve_parent_dns("h1") == ["10.0.0.53"]


class TestParamHelpers:
    def test_param_or_treats_falsy_as_missing(self):
        assert _param_or({"a": ""}, "a", "fallback") == "fallback"
        assert _param_or({"a": 0}, "a", 8443) == 8443
        assert _param_or({"a": "x"}, "a", "fallback") == "x"
        assert _param_or({}, "a", "fallback") == "fallback"

    def test_first_param_or_returns_the_first_truthy_key(self):
        params = {"a": "", "b": "second", "c": "third"}
        assert _first_param_or(params, ["a", "b", "c"], "d") == "second"
        assert _first_param_or({}, ["a"], "d") == "d"


class TestFreeBsdDetection:
    @pytest.mark.parametrize(
        "label,expected",
        [
            ("FreeBSD 14.3", True),
            ("freebsd", True),
            ("OpenBSD 7.8", True),  # matches on "bsd"
            ("NetBSD 10", True),
            ("Ubuntu 24.04", False),
            ("", False),
        ],
    )
    def test_detection(self, label, expected):
        assert _is_freebsd_distribution(label) is expected

    def test_non_freebsd_gets_no_bootstrap_material(self):
        assert _freebsd_bootstrap_material("Ubuntu 24.04") == ("", "", "")

    def test_freebsd_material_is_a_real_keypair_and_a_fresh_password(self):
        pub, priv, password = _freebsd_bootstrap_material("FreeBSD 14.3")
        assert pub.endswith(" sysmanage-bootstrap")
        assert "PRIVATE KEY" in priv
        assert len(password) >= 20
        # Each create must get its own credentials; a shared password across
        # guests would be a fleet-wide secret.
        _, _, other = _freebsd_bootstrap_material("FreeBSD 14.3")
        assert password != other


class TestKvmBaseImagePath:
    def test_plain_qcow2_url(self):
        path, mode = _derive_kvm_base_image_path(
            "https://example.test/images/noble.qcow2", "vm1"
        )
        assert path == "/var/lib/libvirt/images/noble.qcow2"
        assert mode == ""

    @pytest.mark.parametrize("ext", ["xz", "gz", "bz2"])
    def test_compressed_urls_strip_the_extension_and_report_the_mode(self, ext):
        path, mode = _derive_kvm_base_image_path(
            f"https://example.test/images/noble.qcow2.{ext}", "vm1"
        )
        # The stripped name is what makes a re-run reuse the image instead of
        # downloading it again.
        assert path == "/var/lib/libvirt/images/noble.qcow2"
        assert mode == ext

    def test_a_trailing_slash_falls_back_to_the_vm_name(self):
        path, mode = _derive_kvm_base_image_path("https://example.test/images/", "vm1")
        assert path == "/var/lib/libvirt/images/vm1.qcow2"
        assert mode == ""

    def test_an_unknown_extension_is_not_treated_as_compression(self):
        path, mode = _derive_kvm_base_image_path("https://e.test/a.qcow2.zst", "vm1")
        assert path == "/var/lib/libvirt/images/a.qcow2.zst"
        assert mode == ""


class TestAgentConfigYaml:
    def test_defaults_when_nothing_is_supplied(self):
        with patch(
            "backend.api.child_host_creation_dispatch._child_enrollment_token",
            return_value=None,
        ):
            yaml_text = _build_agent_config_yaml({})
        assert 'hostname: "localhost"' in yaml_text
        assert "port: 8443" in yaml_text
        assert "use_https: false" in yaml_text
        assert "auto_approve:" not in yaml_text
        assert "security:" not in yaml_text

    def test_auto_approve_and_enrollment_token_are_SEPARATE_sections(self):
        # They do different jobs: auto_approve skips the approval queue,
        # security.enrollment_token selects the tenant database.  Emitting one
        # in place of the other is how child hosts landed in "No tenant".
        yaml_text = _build_agent_config_yaml(
            {
                "server_url": "sm.example.test",
                "server_port": 443,
                "use_https": True,
                "auto_approve_token": "AAT",
                "enrollment_token": "ENT",
            }
        )
        assert 'token: "AAT"' in yaml_text
        assert 'enrollment_token: "ENT"' in yaml_text
        assert "use_https: true" in yaml_text

    def test_an_explicit_enrollment_token_is_not_overridden_by_the_minter(self):
        with patch(
            "backend.api.child_host_creation_dispatch._child_enrollment_token",
            return_value="MINTED",
        ) as minter:
            yaml_text = _build_agent_config_yaml({"enrollment_token": "EXPLICIT"})
        assert 'enrollment_token: "EXPLICIT"' in yaml_text
        minter.assert_not_called()

    def test_the_token_is_minted_from_the_parent_when_absent(self):
        with patch(
            "backend.api.child_host_creation_dispatch._child_enrollment_token",
            return_value="MINTED",
        ) as minter:
            yaml_text = _build_agent_config_yaml({}, parent_host_id="parent-1")
        assert 'enrollment_token: "MINTED"' in yaml_text
        minter.assert_called_once_with("parent-1")


class TestKvmCreateRequest:
    """``_build_kvm_create_request`` turns a flat params dict into the engine's
    request object.  The DNS precedence here is the whole point of audit gap
    fix #5: without it a guest on a split-horizon network silently gets public
    Cloudflare resolvers and cannot see corporate records."""

    @staticmethod
    def _engine():
        class _Engine:
            @staticmethod
            def VmCreateRequest(**kwargs):  # noqa: N802 - mirrors engine API
                return kwargs

        return _Engine()

    def test_explicit_dns_server_wins_over_the_parent(self):
        with patch(
            "backend.api.child_host_creation_dispatch._resolve_parent_dns",
            return_value=["10.9.9.9"],
        ) as parent:
            out = _build_kvm_create_request(
                self._engine(),
                {"vm_name": "vm1", "dns_server": "10.0.0.53"},
                "/img/base.qcow2",
                host_id="h1",
            )
        assert out["dns_server"] == "10.0.0.53"
        # An operator who typed a resolver must not have it silently replaced.
        parent.assert_not_called()

    def test_the_parent_resolver_is_used_when_none_was_supplied(self):
        with patch(
            "backend.api.child_host_creation_dispatch._resolve_parent_dns",
            return_value=["10.0.0.53", "10.0.0.54"],
        ):
            out = _build_kvm_create_request(
                self._engine(), {"vm_name": "vm1"}, "/img/base.qcow2", host_id="h1"
            )
        assert out["dns_server"] == "10.0.0.53"
        assert out["dns_servers"] == ["10.0.0.53", "10.0.0.54"]

    def test_an_explicit_dns_servers_list_is_passed_through(self):
        with patch(
            "backend.api.child_host_creation_dispatch._resolve_parent_dns",
            return_value=["10.9.9.9"],
        ):
            out = _build_kvm_create_request(
                self._engine(),
                {"vm_name": "vm1", "dns_servers": ["8.8.8.8"]},
                "/img/base.qcow2",
                host_id="h1",
            )
        assert out["dns_servers"] == ["8.8.8.8"]

    def test_no_host_id_means_no_parent_lookup_and_no_dns_keys(self):
        # Nothing to inherit from: the engine applies its own default rather
        # than us inventing one.
        out = _build_kvm_create_request(
            self._engine(), {"vm_name": "vm1"}, "/img/base.qcow2", host_id=None
        )
        assert not out.get("dns_server")
        assert "dns_servers" not in out or out["dns_servers"] == []

    def test_freebsd_creates_carry_bootstrap_material(self):
        out = _build_kvm_create_request(
            self._engine(),
            {"vm_name": "vm1", "distribution_label": "FreeBSD 14.3"},
            "/img/base.qcow2",
        )
        blob = repr(out)
        assert "sysmanage-bootstrap" in blob
        assert "PRIVATE KEY" in blob

    def test_linux_creates_carry_none(self):
        out = _build_kvm_create_request(
            self._engine(),
            {"vm_name": "vm1", "distribution_label": "Ubuntu 24.04"},
            "/img/base.qcow2",
        )
        blob = repr(out)
        assert "sysmanage-bootstrap" not in blob
        assert "PRIVATE KEY" not in blob

    def test_the_base_image_path_is_passed_through_verbatim(self):
        out = _build_kvm_create_request(
            self._engine(), {"vm_name": "vm1"}, "/var/lib/libvirt/images/noble.qcow2"
        )
        assert "/var/lib/libvirt/images/noble.qcow2" in repr(out)
