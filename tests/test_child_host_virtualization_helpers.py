# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Parameter assembly for child-host creation.

These helpers decide what the guest is built from and what secrets travel to
it, and both kinds of mistake are silent.  Forwarding half a Windows group
(an IP with no gateway, a domain user with no domain) puts credentials on a
config ISO for a join that is never attempted; dropping an engine-resolved
install command falls back to a DB row that has been drifting since it was
seeded.  Nothing raises in either case -- the VM just comes up wrong.

The Pro+ ``virtualization_engine`` is a closed module, so it is faked to the
three functions this module calls into.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import child_host_virtualization as chv
from backend.api.child_host_models import CreateWslChildHostRequest

MOD = "backend.api.child_host_virtualization"


def _distribution(**overrides):
    row = SimpleNamespace(
        distribution_name="Ubuntu",
        distribution_version="24.04",
        install_identifier="ubuntu-24.04",
        cloud_image_url="https://cloud.invalid/noble.img",
        agent_install_commands=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _request(**overrides):
    payload = {
        "child_type": "kvm",
        "distribution": "ubuntu-24.04",
        "hostname": "guest",
        "username": "admin",
        "password": "hunter2",
    }
    payload.update(overrides)
    return CreateWslChildHostRequest(**payload)


def _engine(**overrides):
    engine = SimpleNamespace(
        get_agent_install_commands=lambda name, version: ["apt install sysmanage"],
        get_cloud_image_url=lambda dist: "https://engine.invalid/noble.img",
        detect_autoinstall_mode=lambda dist: "ubuntu_autoinstall",
    )
    for key, value in overrides.items():
        setattr(engine, key, value)
    return engine


def _modules(**by_name):
    """Patch module_loader.get_module with a per-name lookup."""
    return patch(f"{MOD}.module_loader.get_module", side_effect=by_name.get)


class TestCheckContainerModule:
    def test_an_unlicensed_server_gets_a_clean_402(self):
        with _modules():
            with pytest.raises(HTTPException) as exc:
                chv._check_container_module()
        assert exc.value.status_code == 402
        assert "Professional+" in exc.value.detail

    def test_a_licensed_server_passes_through(self):
        with _modules(container_engine=object()):
            assert chv._check_container_module() is None


class TestParseAgentInstallCommands:
    def test_the_engine_is_authoritative_over_the_seeded_row(self):
        distribution = _distribution(agent_install_commands=["stale command"])
        with _modules(virtualization_engine=_engine()):
            out = chv._parse_agent_install_commands(distribution)
        # Seeded rows drift: the Phase 11.8 PPA migration left the table
        # carrying the legacy direct-download path for months.
        assert out == ["apt install sysmanage"]

    def test_an_engine_that_returns_nothing_falls_back_to_the_row(self):
        engine = _engine(get_agent_install_commands=lambda name, version: [])
        distribution = _distribution(agent_install_commands=["db command"])
        with _modules(virtualization_engine=engine):
            assert chv._parse_agent_install_commands(distribution) == ["db command"]

    def test_an_engine_that_raises_falls_back_to_the_row(self):
        def _boom(name, version):
            raise RuntimeError("unknown distro")

        engine = _engine(get_agent_install_commands=_boom)
        distribution = _distribution(agent_install_commands=["db command"])
        with _modules(virtualization_engine=engine):
            assert chv._parse_agent_install_commands(distribution) == ["db command"]

    def test_a_json_encoded_column_is_decoded(self):
        distribution = _distribution(agent_install_commands=json.dumps(["a", "b"]))
        with _modules():
            assert chv._parse_agent_install_commands(distribution) == ["a", "b"]

    @pytest.mark.parametrize(
        "value", ["not json at all", {"a": 1}, 42], ids=["bad-json", "dict", "int"]
    )
    def test_an_unusable_column_yields_no_commands(self, value):
        # An empty list means "install nothing" -- the guest comes up without
        # an agent, which is visible.  A crash here would abort the create.
        with _modules():
            assert (
                chv._parse_agent_install_commands(
                    _distribution(agent_install_commands=value)
                )
                == []
            )

    def test_no_distribution_at_all_yields_no_commands(self):
        assert chv._parse_agent_install_commands(None) == []

    def test_an_empty_column_with_no_engine_yields_no_commands(self):
        with _modules():
            assert chv._parse_agent_install_commands(_distribution()) == []


class TestDistributionToDict:
    def test_only_the_four_engine_fields_are_projected(self):
        assert chv._distribution_to_dict(_distribution()) == {
            "cloud_image_url": "https://cloud.invalid/noble.img",
            "install_identifier": "ubuntu-24.04",
            "distribution_name": "Ubuntu",
            "distribution_version": "24.04",
        }

    def test_none_projects_to_none(self):
        assert chv._distribution_to_dict(None) is None


class TestGetCloudImageUrl:
    def test_the_engine_answer_wins(self):
        with _modules(virtualization_engine=_engine()):
            assert (
                chv._get_cloud_image_url(_distribution())
                == "https://engine.invalid/noble.img"
            )

    def test_an_engine_that_raises_falls_back_to_the_row(self):
        def _boom(dist):
            raise RuntimeError("no")

        with _modules(virtualization_engine=_engine(get_cloud_image_url=_boom)):
            assert (
                chv._get_cloud_image_url(_distribution())
                == "https://cloud.invalid/noble.img"
            )

    def test_an_https_install_identifier_serves_as_the_image(self):
        distribution = _distribution(
            cloud_image_url=None, install_identifier="https://iso.invalid/x.img"
        )
        with _modules():
            assert chv._get_cloud_image_url(distribution) == "https://iso.invalid/x.img"

    def test_a_non_url_install_identifier_is_not_an_image(self):
        distribution = _distribution(cloud_image_url=None)
        with _modules():
            assert chv._get_cloud_image_url(distribution) is None

    def test_no_distribution_yields_nothing(self):
        assert chv._get_cloud_image_url(None) is None


class TestValidatePlatformForChildType:
    @pytest.mark.parametrize(
        "child_type,platform",
        [("wsl", "Windows 11"), ("kvm", "Linux")],
    )
    def test_a_matching_platform_passes(self, child_type, platform):
        chv._validate_platform_for_child_type(
            SimpleNamespace(platform=platform), child_type
        )

    @pytest.mark.parametrize(
        "child_type,platform",
        [("wsl", "Linux"), ("wsl", None), ("kvm", "Windows 11"), ("kvm", None)],
    )
    def test_a_mismatched_platform_is_a_400(self, child_type, platform):
        with pytest.raises(HTTPException) as exc:
            chv._validate_platform_for_child_type(
                SimpleNamespace(platform=platform), child_type
            )
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("child_type", ["lxd", "vmm", "bhyve"])
    def test_unconstrained_child_types_are_not_platform_checked(self, child_type):
        # bhyve/vmm are validated by the engine at plan time, on the real
        # OS string rather than a substring match.
        chv._validate_platform_for_child_type(
            SimpleNamespace(platform="Anything"), child_type
        )


class TestDetermineChildName:
    def test_lxd_uses_the_container_name(self):
        assert (
            chv._determine_child_name(_request(child_type="lxd", container_name="c1"))
            == "c1"
        )

    @pytest.mark.parametrize("child_type", ["vmm", "kvm", "bhyve"])
    def test_the_vm_types_use_the_vm_name(self, child_type):
        assert (
            chv._determine_child_name(_request(child_type=child_type, vm_name="vm1"))
            == "vm1"
        )

    def test_wsl_uses_the_distribution(self):
        assert (
            chv._determine_child_name(_request(child_type="wsl", distribution="Ubuntu"))
            == "Ubuntu"
        )

    @pytest.mark.parametrize("child_type", ["lxd", "vmm", "kvm", "bhyve"])
    def test_a_missing_name_is_a_400_naming_the_child_type(self, child_type):
        with pytest.raises(HTTPException) as exc:
            chv._determine_child_name(_request(child_type=child_type))
        assert exc.value.status_code == 400


class TestResolveServerUrl:
    def test_a_routable_host_is_returned_untouched(self):
        assert chv._resolve_server_url("sysmanage.example.invalid") == (
            "sysmanage.example.invalid"
        )

    @pytest.mark.parametrize("api_host", ["0.0.0.0", "localhost", "127.0.0.1"])
    def test_a_listen_all_address_resolves_to_the_fqdns_ip(self, api_host):
        # A child host handed "0.0.0.0" has nothing to connect back to.
        with patch("socket.getfqdn", return_value="server.invalid"):
            with patch("socket.gethostbyname", return_value="10.0.0.5"):
                assert chv._resolve_server_url(api_host) == "10.0.0.5"

    def test_a_loopback_fqdn_falls_through_to_the_outbound_route(self):
        sock = SimpleNamespace(
            connect=lambda addr: None,
            getsockname=lambda: ("192.168.1.20", 0),
            close=lambda: None,
        )
        with patch("socket.getfqdn", return_value="server.invalid"):
            with patch("socket.gethostbyname", return_value="127.0.1.1"):
                with patch("socket.socket", return_value=sock):
                    assert chv._resolve_server_url("localhost") == "192.168.1.20"

    def test_a_total_resolution_failure_degrades_to_localhost(self):
        with patch("socket.getfqdn", side_effect=OSError("no dns")):
            assert chv._resolve_server_url("localhost") == "localhost"


class TestHashChildPassword:
    @pytest.mark.parametrize("child_type", ["vmm", "kvm", "bhyve"])
    def test_the_vm_types_use_the_os_specific_hash(self, child_type):
        with patch(f"{MOD}.hash_password_for_os", return_value="$6$os") as hasher:
            out = chv._hash_child_password(_request(child_type=child_type))
        # A bcrypt hash in an OpenBSD master.passwd is not a login.
        assert out == "$6$os"
        assert hasher.call_args[0][1] == "ubuntu-24.04"

    @pytest.mark.parametrize("child_type", ["wsl", "lxd"])
    def test_the_container_types_use_bcrypt(self, child_type):
        out = chv._hash_child_password(_request(child_type=child_type))
        assert out.startswith("$2b$")


class TestAddVmmParams:
    def test_the_vm_name_and_root_hash_are_added(self):
        params = {}
        with patch(f"{MOD}.hash_password_for_os", return_value="$6$root"):
            chv._add_vmm_params(params, _request(child_type="vmm", vm_name="vm1"))
        assert params["vm_name"] == "vm1"
        assert params["root_password_hash"] == "$6$root"
        assert "iso_url" not in params

    def test_an_explicit_root_password_is_preferred(self):
        with patch(f"{MOD}.hash_password_for_os", return_value="$6$x") as hasher:
            chv._add_vmm_params(
                {}, _request(child_type="vmm", vm_name="v", root_password="rootpw")
            )
        assert hasher.call_args[0][0] == "rootpw"

    def test_the_user_password_is_the_root_fallback(self):
        with patch(f"{MOD}.hash_password_for_os", return_value="$6$x") as hasher:
            chv._add_vmm_params({}, _request(child_type="vmm", vm_name="v"))
        assert hasher.call_args[0][0] == "hunter2"

    def test_an_iso_url_rides_along_when_set(self):
        params = {}
        with patch(f"{MOD}.hash_password_for_os", return_value="$6$x"):
            chv._add_vmm_params(
                params,
                _request(child_type="vmm", vm_name="v", iso_url="http://i/x.iso"),
            )
        assert params["iso_url"] == "http://i/x.iso"


class TestDetectAutoinstallMode:
    def test_the_engine_answer_wins(self):
        with _modules(virtualization_engine=_engine()):
            assert chv._detect_autoinstall_mode(_distribution()) == "ubuntu_autoinstall"

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Debian", "preseed"),
            ("Ubuntu Server", "ubuntu_autoinstall"),
            ("Alpine Linux", "alpine_apkovl"),
            ("Rocky Linux", ""),
        ],
    )
    def test_the_oss_fallback_keys_off_the_distribution_name(self, name, expected):
        distribution = _distribution(
            distribution_name=name, install_identifier="http://x/netinst.ISO"
        )
        with _modules():
            assert chv._detect_autoinstall_mode(distribution) == expected

    def test_a_non_iso_installer_has_no_autoinstall_mode(self):
        distribution = _distribution(install_identifier="ubuntu-24.04")
        with _modules():
            assert chv._detect_autoinstall_mode(distribution) == ""

    def test_an_engine_that_raises_falls_back(self):
        def _boom(dist):
            raise RuntimeError("no")

        distribution = _distribution(
            distribution_name="Debian", install_identifier="http://x/netinst.iso"
        )
        with _modules(virtualization_engine=_engine(detect_autoinstall_mode=_boom)):
            assert chv._detect_autoinstall_mode(distribution) == "preseed"

    @pytest.mark.parametrize("distribution", [None, "no-identifier"])
    def test_nothing_to_inspect_yields_no_mode(self, distribution):
        row = None if distribution is None else _distribution(install_identifier=None)
        with _modules():
            assert chv._detect_autoinstall_mode(row) == ""


class TestPopulateAutoinstallParams:
    def test_the_mode_iso_and_network_triple_are_forwarded(self):
        params = {}
        distribution = _distribution(install_identifier="http://x/netinst.iso")
        request = SimpleNamespace(
            vm_ip="10.0.0.9", gateway_ip="10.0.0.1", dns_server="10.0.0.53"
        )
        with _modules(virtualization_engine=_engine()):
            chv._populate_autoinstall_params(params, request, distribution)
        assert params["autoinstall_mode"] == "ubuntu_autoinstall"
        assert params["install_iso_url"] == "http://x/netinst.iso"
        assert params["vm_ip"] == "10.0.0.9"
        assert params["dns_server"] == "10.0.0.53"

    def test_a_cloud_image_distribution_gets_no_autoinstall_keys(self):
        params = {}
        engine = _engine(detect_autoinstall_mode=lambda dist: "")
        with _modules(virtualization_engine=engine):
            chv._populate_autoinstall_params(params, _request(), _distribution())
        assert params == {}

    def test_missing_network_fields_default_to_empty_for_the_engine(self):
        params = {}
        with _modules(virtualization_engine=_engine()):
            chv._populate_autoinstall_params(params, SimpleNamespace(), _distribution())
        assert params["vm_ip"] == ""
        assert params["gateway_ip"] == ""

    def test_a_caller_supplied_value_is_not_overwritten(self):
        params = {"vm_ip": "already-set"}
        request = SimpleNamespace(vm_ip="10.0.0.9")
        with _modules(virtualization_engine=_engine()):
            chv._populate_autoinstall_params(params, request, _distribution())
        assert params["vm_ip"] == "already-set"


class TestRequestAttr:
    @pytest.mark.parametrize(
        "request_obj,expected",
        [
            (SimpleNamespace(vm_ip="10.0.0.9"), "10.0.0.9"),
            (SimpleNamespace(vm_ip=None), ""),
            (SimpleNamespace(), ""),
        ],
    )
    def test_a_missing_or_null_attribute_reads_as_empty(self, request_obj, expected):
        assert chv._request_attr(request_obj, "vm_ip") == expected


class TestAddCloudVmParams:
    def test_the_request_values_win_over_the_per_type_defaults(self):
        params = {}
        request = _request(vm_name="vm1", memory="8G", disk_size="100G", cpus=8)
        with _modules(virtualization_engine=_engine()):
            chv._add_cloud_vm_params(params, request, _distribution(), "2G", "20G", 2)
        assert (params["memory"], params["disk_size"], params["cpus"]) == (
            "8G",
            "100G",
            8,
        )

    def test_the_per_type_defaults_apply_when_the_request_is_blank(self):
        params = {}
        request = _request(vm_name="vm1", memory=None, disk_size=None, cpus=None)
        with _modules(virtualization_engine=_engine()):
            chv._add_cloud_vm_params(params, request, _distribution(), "1G", "20G", 1)
        assert (params["memory"], params["disk_size"], params["cpus"]) == (
            "1G",
            "20G",
            1,
        )

    def test_the_distribution_label_is_forwarded_for_the_cloud_init_renderer(self):
        params = {}
        with _modules(virtualization_engine=_engine()):
            chv._add_cloud_vm_params(
                params,
                _request(vm_name="v"),
                _distribution(distribution_name="FreeBSD"),
                "2G",
                "20G",
                2,
            )
        # The engine branches on this to pick shell, package names and
        # service-control commands.
        assert params["distribution_label"] == "FreeBSD"

    def test_no_distribution_means_no_image_or_label(self):
        params = {}
        with _modules():
            chv._add_cloud_vm_params(
                params, _request(vm_name="v"), None, "2G", "20G", 2
            )
        assert "cloud_image_url" not in params
        assert "distribution_label" not in params


class TestIsWindowsDistribution:
    @pytest.mark.parametrize(
        "identifier,expected",
        [
            ("windows-server-2022", True),
            ("  WINDOWS-SERVER-2025  ", True),
            ("ubuntu-24.04", False),
            ("", False),
            (None, False),
        ],
    )
    def test_only_the_windows_server_catalog_entries_match(self, identifier, expected):
        assert chv._is_windows_distribution(identifier) is expected


class TestWindowsParams:
    def test_the_defaulted_fields_are_always_sent(self):
        params = {}
        chv._add_windows_params(
            params,
            _request(windows_edition=None, windows_timezone=None, windows_locale=None),
        )
        # An empty edition is "no edition", not "use the default" -- a blank
        # must never reach the engine.
        assert params["windows_edition"] == "standard-core"
        assert params["windows_timezone"] == "UTC"
        assert params["windows_locale"] == "en-US"

    def test_optional_fields_travel_only_when_set(self):
        params = {}
        chv._add_windows_params(params, _request(windows_iso_path="/isos/ws2022.iso"))
        assert params["windows_iso_path"] == "/isos/ws2022.iso"
        assert "windows_product_key" not in params

    def test_the_static_network_group_travels_together(self):
        params = {}
        chv._add_windows_params(
            params,
            _request(
                windows_static_ip="10.0.0.9",
                windows_gateway="10.0.0.1",
                windows_dns_servers="10.0.0.53",
            ),
        )
        assert params["windows_static_ip"] == "10.0.0.9"
        assert params["windows_gateway"] == "10.0.0.1"

    def test_a_gateway_without_an_ip_is_not_sent(self):
        # The engine refuses an address with no gateway at plan time; sending
        # half the group would only move the failure later.
        params = {}
        chv._add_windows_params(params, _request(windows_gateway="10.0.0.1"))
        assert "windows_gateway" not in params

    def test_domain_credentials_do_not_travel_without_a_domain(self):
        params = {}
        chv._add_windows_params(
            params,
            _request(windows_domain_user="svc", windows_domain_password="secret"),
        )
        # Otherwise the credentials land on a config ISO for a join that is
        # never attempted.
        assert "windows_domain_user" not in params
        assert "windows_domain_password" not in params

    def test_a_domain_join_carries_its_dependents(self):
        params = {}
        chv._add_windows_params(
            params,
            _request(
                windows_join_domain="corp.invalid",
                windows_domain_ou="OU=Servers",
                windows_domain_user="svc",
            ),
        )
        assert params["windows_join_domain"] == "corp.invalid"
        assert params["windows_domain_ou"] == "OU=Servers"

    def test_copy_when_set_raises_on_a_field_the_model_does_not_have(self):
        # Deliberate: a name that isn't on the request model is a bug in this
        # module, not something to skip silently.
        with pytest.raises(AttributeError):
            chv._copy_when_set({}, _request(), ("no_such_field",))


class TestStoreWindowsProductKey:
    def test_a_key_is_vaulted_and_only_the_secret_id_is_returned(self):
        session = SimpleNamespace(add=lambda row: None, flush=lambda: None)
        vault = SimpleNamespace(
            store_secret=lambda **kw: {"vault_token": "t", "vault_path": "p"}
        )
        with patch(f"{MOD}.VaultService", return_value=vault):
            with patch(f"{MOD}.models.Secret") as secret_cls:
                secret_cls.return_value = SimpleNamespace(id="sec-1")
                out = chv._store_windows_product_key(
                    session, _request(windows_product_key="AAAAA-BBBBB"), "vm1"
                )
        assert out == "sec-1"
        # The key itself must never be a column on host_child.
        assert secret_cls.call_args.kwargs["vault_token"] == "t"
        assert "AAAAA-BBBBB" not in str(secret_cls.call_args.kwargs)

    @pytest.mark.parametrize("key", [None, "", "   "])
    def test_no_key_is_the_normal_evaluation_media_path(self, key):
        with patch(f"{MOD}.VaultService") as vault:
            assert (
                chv._store_windows_product_key(
                    None, _request(windows_product_key=key), "vm1"
                )
                is None
            )
        vault.assert_not_called()


class TestBuildCommandParams:
    def _build(self, request, distribution=None, **overrides):
        kwargs = {
            "password_hash": "$6$hash",
            "agent_install_commands": ["apt install"],
            "server_url": "10.0.0.1",
            "api_port": 8443,
            "use_https": True,
            "new_child_id": "child-1",
            "auto_approve_token": None,
            "distribution": distribution,
        }
        kwargs.update(overrides)
        return chv._build_command_params(
            request,
            kwargs["password_hash"],
            kwargs["agent_install_commands"],
            kwargs["server_url"],
            kwargs["api_port"],
            kwargs["use_https"],
            kwargs["new_child_id"],
            kwargs["auto_approve_token"],
            kwargs["distribution"],
        )

    def test_the_common_envelope_is_always_present(self):
        with _modules():
            params = self._build(_request(child_type="wsl"))
        assert params["child_host_id"] == "child-1"
        assert params["password_hash"] == "$6$hash"
        assert params["server_port"] == 8443
        assert params["use_https"] is True

    def test_lxd_carries_the_container_name(self):
        with _modules():
            params = self._build(_request(child_type="lxd", container_name="c1"))
        assert params["container_name"] == "c1"

    def test_vmm_carries_its_own_root_hash(self):
        with _modules():
            with patch(f"{MOD}.hash_password_for_os", return_value="$6$root"):
                params = self._build(_request(child_type="vmm", vm_name="v"))
        assert params["root_password_hash"] == "$6$root"

    @pytest.mark.parametrize(
        "child_type,memory,disk",
        [("kvm", "2G", "20G"), ("bhyve", "1G", "20G")],
    )
    def test_each_vm_type_has_its_own_resource_defaults(self, child_type, memory, disk):
        request = _request(
            child_type=child_type, vm_name="v", memory=None, disk_size=None
        )
        with _modules():
            params = self._build(request, _distribution())
        assert (params["memory"], params["disk_size"]) == (memory, disk)

    def test_a_windows_kvm_request_carries_both_parameter_sets(self):
        request = _request(
            child_type="kvm", vm_name="v", distribution="windows-server-2022"
        )
        with _modules():
            params = self._build(request, _distribution())
        # Both are sent and the engine picks; the cloud-init fields are inert
        # on the Windows path rather than wrong.
        assert params["windows_edition"] == "standard-core"
        assert params["vm_name"] == "v"

    def test_a_linux_kvm_request_carries_no_windows_fields(self):
        with _modules():
            params = self._build(
                _request(child_type="kvm", vm_name="v"), _distribution()
            )
        assert not any(k.startswith("windows_") for k in params)

    def test_an_auto_approve_token_rides_along_only_when_minted(self):
        with _modules():
            assert "auto_approve_token" not in self._build(_request(child_type="wsl"))
            params = self._build(_request(child_type="wsl"), auto_approve_token="tok")
        assert params["auto_approve_token"] == "tok"
