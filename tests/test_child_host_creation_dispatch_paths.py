# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The per-hypervisor plan builders behind ``try_plan_based_creation``.

Every one of these helpers returns ``False`` on any failure -- the module is
deliberately written so a declining engine never raises into the request -- and
the caller turns that into a flat 502.  That design means a builder can start
returning False for a *new* reason (a renamed engine field, a dropped kwarg)
and the only visible symptom is "create child host failed", identical to the
symptom of the engine not being licensed at all.  These tests pin which inputs
are supposed to produce True so a regression is attributable.

The engines themselves are Pro+ closed modules, so they are faked here to the
surface this module actually touches: the request classes, ``model_fields``
capability probes, and the ``build_*_plan`` functions.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.api.child_host_creation_dispatch import (
    _bhyve_merge_download_into_create_plan,
    _bhyve_resolve_install_inputs,
    _bhyve_synthesize_download_plan,
    _build_bhyve_create_request,
    _build_vmm_create_request,
    _child_enrollment_token,
    _enqueue_create_plan,
    _load_network_details_payload,
    _resolve_vmm_linux_autoinstall,
    _try_bhyve_plan_based_creation,
    _try_kvm_plan_based_creation,
    _try_lxd_plan_based_creation,
    _try_vmm_plan_based_creation,
    _try_wsl_plan_based_creation,
    try_plan_based_creation,
)

DISPATCH = "backend.api.child_host_creation_dispatch"


def _req_class(fields=()):
    """A stand-in for a pydantic engine request.

    ``model_fields`` matters: the module probes it to decide whether the
    LOADED engine build understands a newer kwarg (``cloud_image_url``,
    ``linux_autoinstall_distro``).  A plain kwargs-capturing class would make
    every capability probe pass and hide exactly the skew being tested.
    """

    class _Req:
        model_fields = {name: object() for name in fields}

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    return _Req


def _virt_engine(**overrides):
    engine = SimpleNamespace(
        ImageDownloadRequest=_req_class(),
        VmCreateRequest=_req_class(),
        BhyveCreateRequest=_req_class(),
        VmmCreateRequest=_req_class(),
        build_kvm_image_download_plan=lambda req: {"commands": ["download"]},
        build_kvm_create_plan=lambda req: {
            "files": ["cidata"],
            "commands": ["create"],
        },
        build_bhyve_create_plan=lambda req: {
            "engine": "virtualization_engine",
            "hypervisor": "bhyve",
            "action": "create",
            "files": ["rc.d"],
            "commands": ["vm create"],
        },
        build_vmm_create_plan=lambda req: {"commands": ["vmctl start"]},
    )
    for key, value in overrides.items():
        setattr(engine, key, value)
    return engine


def _container_engine(**overrides):
    engine = SimpleNamespace(
        WslCreateRequest=_req_class(),
        LxdCreateRequest=_req_class(),
        build_wsl_create_plan=lambda req: {"commands": ["wsl --install"]},
        build_lxd_create_plan=lambda req: {"commands": ["lxc launch"]},
    )
    for key, value in overrides.items():
        setattr(engine, key, value)
    return engine


class _Enqueued:
    """Captures what a builder handed to the queue."""

    def __init__(self):
        self.calls = []

    def __call__(self, host_id, plan, command_params, timeout):
        self.calls.append(
            SimpleNamespace(
                host_id=host_id,
                plan=plan,
                command_params=command_params,
                timeout=timeout,
            )
        )
        return "msg-1"

    @property
    def plan(self):
        return self.calls[0].plan


class TestKvmPlanPath:
    def test_a_complete_request_is_built_and_queued(self):
        enqueued = _Enqueued()
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=_virt_engine()):
            with patch(f"{DISPATCH}._enqueue_create_plan", enqueued):
                ok = _try_kvm_plan_based_creation(
                    {
                        "vm_name": "vm1",
                        "cloud_image_url": "https://example.invalid/noble.img",
                    },
                    "host-1",
                )
        assert ok is True
        # The download must run BEFORE the create, or the create references a
        # base image that isn't on disk yet.
        assert enqueued.plan["commands"] == ["download", "create"]
        assert enqueued.plan["files"] == ["cidata"]
        assert enqueued.calls[0].timeout == 2400

    def test_an_unlicensed_engine_declines_rather_than_raising(self):
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=None):
            assert _try_kvm_plan_based_creation({"vm_name": "vm1"}, "host-1") is False

    @pytest.mark.parametrize(
        "params",
        [
            {"cloud_image_url": "https://example.invalid/x.img"},
            {"vm_name": "vm1"},
            {"vm_name": "", "cloud_image_url": ""},
        ],
        ids=["no-vm-name", "no-image-url", "neither"],
    )
    def test_incomplete_params_decline(self, params):
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=_virt_engine()):
            assert _try_kvm_plan_based_creation(params, "host-1") is False

    def test_an_engine_that_raises_is_contained(self):
        def _boom(req):
            raise RuntimeError("engine build failed")

        engine = _virt_engine(build_kvm_create_plan=_boom)
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=engine):
            ok = _try_kvm_plan_based_creation(
                {"vm_name": "vm1", "cloud_image_url": "https://example.invalid/x.img"},
                "host-1",
            )
        assert ok is False


class TestBhyveInstallInputs:
    def test_a_raw_image_is_used_as_is_with_no_download_step(self):
        raw, iso, url, plan, ok = _bhyve_resolve_install_inputs(
            _virt_engine(), "vm1", {"raw_image_path": "/img/vm1.raw"}
        )
        assert (raw, iso, plan, ok) == ("/img/vm1.raw", "", None, True)
        assert url == ""

    def test_an_engine_that_accepts_cloud_image_url_needs_no_synthesis(self):
        engine = _virt_engine(BhyveCreateRequest=_req_class(["cloud_image_url"]))
        raw, _, url, plan, ok = _bhyve_resolve_install_inputs(
            engine, "vm1", {"cloud_image_url": "https://example.invalid/x.qcow2"}
        )
        # The engine downloads it internally; we must not prepend our own step.
        assert plan is None and ok is True and raw == ""
        assert url == "https://example.invalid/x.qcow2"

    def test_an_older_engine_gets_a_synthesized_download_and_a_raw_target(self):
        raw, _, _, plan, ok = _bhyve_resolve_install_inputs(
            _virt_engine(),
            "vm1",
            {"cloud_image_url": "https://example.invalid/x.qcow2"},
        )
        assert ok is True
        assert plan == {"commands": ["download"]}
        # bhyve boots raw disks, not qcow2 -- the suffix rewrite is the point.
        assert raw.endswith(".raw")
        assert not raw.endswith(".qcow2")

    def test_no_install_source_at_all_is_refused(self):
        *_, ok = _bhyve_resolve_install_inputs(_virt_engine(), "vm1", {})
        assert ok is False

    def test_a_failed_synthesis_is_refused_rather_than_half_planned(self):
        def _boom(req):
            raise RuntimeError("no")

        engine = _virt_engine(build_kvm_image_download_plan=_boom)
        *_, plan, ok = _bhyve_resolve_install_inputs(
            engine, "vm1", {"cloud_image_url": "https://example.invalid/x.qcow2"}
        )
        assert plan is None and ok is False

    def test_synthesis_failure_reports_an_empty_path(self):
        def _boom(req):
            raise RuntimeError("no")

        plan, path = _bhyve_synthesize_download_plan(
            _virt_engine(build_kvm_image_download_plan=_boom),
            "vm1",
            "https://example.invalid/x.qcow2",
        )
        assert (plan, path) == (None, "")


class TestBhyveCreateRequest:
    def test_cloud_image_url_is_forwarded_only_when_no_local_source_exists(self):
        with_local = _build_bhyve_create_request(
            _virt_engine(),
            {"vm_name": "vm1", "cloud_image_url": "https://example.invalid/x.qcow2"},
            "/img/vm1.raw",
            "",
        )
        assert with_local.kwargs["cloud_image_url"] == ""

        without_local = _build_bhyve_create_request(
            _virt_engine(),
            {"vm_name": "vm1", "cloud_image_url": "https://example.invalid/x.qcow2"},
            "",
            "",
        )
        assert (
            without_local.kwargs["cloud_image_url"] == "https://example.invalid/x.qcow2"
        )

    def test_the_hostname_defaults_to_the_vm_name(self):
        req = _build_bhyve_create_request(
            _virt_engine(), {"vm_name": "vm1"}, "/img/vm1.raw", ""
        )
        assert req.kwargs["hostname"] == "vm1"
        assert req.kwargs["template"] == "freebsd"
        assert req.kwargs["cpus"] == 2

    def test_numeric_params_arriving_as_strings_are_coerced(self):
        # The UI posts form values; ``cpus="4"`` would otherwise reach the
        # engine as a string and fail validation deep inside it.
        req = _build_bhyve_create_request(
            _virt_engine(),
            {"vm_name": "vm1", "cpus": "4", "server_port": "8443"},
            "/img/vm1.raw",
            "",
        )
        assert req.kwargs["cpus"] == 4
        assert req.kwargs["server_port"] == 8443


class TestBhyveMerge:
    def test_download_commands_are_prepended_and_metadata_preserved(self):
        merged = _bhyve_merge_download_into_create_plan(
            {
                "engine": "virtualization_engine",
                "hypervisor": "bhyve",
                "action": "create",
                "files": ["rc.d"],
                "commands": ["vm create"],
            },
            {"commands": ["fetch"]},
            "vm1",
        )
        assert merged["commands"] == ["fetch", "vm create"]
        assert merged["vm_name"] == "vm1"
        assert merged["hypervisor"] == "bhyve"


class TestBhyvePlanPath:
    def test_a_raw_image_create_is_queued_unmerged(self):
        enqueued = _Enqueued()
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=_virt_engine()):
            with patch(f"{DISPATCH}._enqueue_create_plan", enqueued):
                ok = _try_bhyve_plan_based_creation(
                    {"vm_name": "vm1", "raw_image_path": "/img/vm1.raw"}, "host-1"
                )
        assert ok is True
        assert enqueued.plan["commands"] == ["vm create"]
        # bhyve image prep is slow; a 2400s timeout would kill a real create.
        assert enqueued.calls[0].timeout == 3600

    def test_a_cloud_image_create_is_queued_with_the_download_merged_in(self):
        enqueued = _Enqueued()
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=_virt_engine()):
            with patch(f"{DISPATCH}._enqueue_create_plan", enqueued):
                ok = _try_bhyve_plan_based_creation(
                    {
                        "vm_name": "vm1",
                        "cloud_image_url": "https://example.invalid/x.qcow2",
                    },
                    "host-1",
                )
        assert ok is True
        assert enqueued.plan["commands"] == ["download", "vm create"]

    def test_an_unlicensed_engine_or_missing_name_declines(self):
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=None):
            assert _try_bhyve_plan_based_creation({"vm_name": "vm1"}, "h") is False
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=_virt_engine()):
            assert _try_bhyve_plan_based_creation({}, "h") is False

    def test_an_engine_that_raises_is_contained(self):
        def _boom(req):
            raise RuntimeError("nope")

        engine = _virt_engine(build_bhyve_create_plan=_boom)
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=engine):
            ok = _try_bhyve_plan_based_creation(
                {"vm_name": "vm1", "raw_image_path": "/img/vm1.raw"}, "host-1"
            )
        assert ok is False


class TestVmmLinuxAutoinstall:
    def test_an_engine_without_the_field_reports_nothing(self):
        assert _resolve_vmm_linux_autoinstall(
            {}, {"linux_autoinstall_distro": "debian"}
        ) == (
            "",
            "",
            "",
        )

    @pytest.mark.parametrize("distro", ["alpine", "debian", "ubuntu"])
    def test_supported_distros_are_resolved(self, distro):
        out = _resolve_vmm_linux_autoinstall(
            {"linux_autoinstall_distro": object()},
            {
                "linux_autoinstall_distro": distro.upper(),
                "linux_autoinstall_version": "1.0",
                "linux_autoinstall_iso_url": "https://example.invalid/i.iso",
            },
        )
        assert out == (distro, "1.0", "https://example.invalid/i.iso")

    @pytest.mark.parametrize("distro", ["", "gentoo", "windows"])
    def test_anything_off_the_allowlist_resolves_to_nothing(self, distro):
        out = _resolve_vmm_linux_autoinstall(
            {"linux_autoinstall_distro": object()},
            {"linux_autoinstall_distro": distro},
        )
        assert out == ("", "", "")


class TestVmmCreateRequest:
    def test_both_password_hashes_present_turns_autoinstall_on(self):
        req = _build_vmm_create_request(
            _virt_engine(),
            {
                "vm_name": "vm1",
                "password_hash": "$6$user",
                "root_password_hash": "$6$root",
            },
        )
        assert req.kwargs["autoinstall"] is True
        # password_hash is the USER's hash under a different name; mapping it to
        # root would hand the operator's user password to root.
        assert req.kwargs["user_password_hash"] == "$6$user"
        assert req.kwargs["root_password_hash"] == "$6$root"

    def test_a_missing_root_hash_leaves_autoinstall_off(self):
        req = _build_vmm_create_request(
            _virt_engine(), {"vm_name": "vm1", "password_hash": "$6$user"}
        )
        assert req.kwargs["autoinstall"] is False

    def test_a_linux_autoinstall_request_suppresses_the_openbsd_autoinstall(self):
        engine = _virt_engine(
            VmmCreateRequest=_req_class(["linux_autoinstall_distro", "cloud_image_url"])
        )
        req = _build_vmm_create_request(
            engine,
            {
                "vm_name": "vm1",
                "password_hash": "$6$user",
                "root_password_hash": "$6$root",
                "linux_autoinstall_distro": "debian",
                "linux_autoinstall_version": "13",
            },
        )
        assert req.kwargs["autoinstall"] is False
        assert req.kwargs["linux_autoinstall_distro"] == "debian"
        assert req.kwargs["linux_autoinstall_version"] == "13"
        # The Linux installer builds its own disk; a cloud image would be
        # downloaded and then thrown away.
        assert "cloud_image_url" not in req.kwargs

    def test_cloud_image_url_rides_along_on_the_legacy_non_autoinstall_path(self):
        engine = _virt_engine(VmmCreateRequest=_req_class(["cloud_image_url"]))
        req = _build_vmm_create_request(
            engine,
            {"vm_name": "vm1", "cloud_image_url": "https://example.invalid/x.qcow2"},
        )
        assert req.kwargs["cloud_image_url"] == "https://example.invalid/x.qcow2"

    def test_an_older_engine_never_sees_the_cloud_image_kwarg(self):
        req = _build_vmm_create_request(
            _virt_engine(),
            {"vm_name": "vm1", "cloud_image_url": "https://example.invalid/x.qcow2"},
        )
        assert "cloud_image_url" not in req.kwargs

    def test_the_carrier_grade_nat_defaults_are_applied_when_unspecified(self):
        req = _build_vmm_create_request(_virt_engine(), {"vm_name": "vm1"})
        assert req.kwargs["gateway_ip"] == "100.64.0.1"
        assert req.kwargs["vm_ip"] == "100.64.0.101"
        assert req.kwargs["openbsd_version"] == "7.7"


class TestVmmPlanPath:
    def test_a_named_vm_is_queued(self):
        enqueued = _Enqueued()
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=_virt_engine()):
            with patch(f"{DISPATCH}._enqueue_create_plan", enqueued):
                assert _try_vmm_plan_based_creation({"vm_name": "vm1"}, "h") is True
        assert enqueued.calls[0].timeout == 2400

    def test_no_engine_or_no_name_declines(self):
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=None):
            assert _try_vmm_plan_based_creation({"vm_name": "vm1"}, "h") is False
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=_virt_engine()):
            assert _try_vmm_plan_based_creation({}, "h") is False

    def test_an_engine_that_raises_is_contained(self):
        def _boom(req):
            raise RuntimeError("nope")

        engine = _virt_engine(build_vmm_create_plan=_boom)
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=engine):
            assert _try_vmm_plan_based_creation({"vm_name": "vm1"}, "h") is False


class TestWslPlanPath:
    def test_a_distribution_is_enough_to_queue_a_plan(self):
        enqueued = _Enqueued()
        with patch(
            f"{DISPATCH}.module_loader.get_module", return_value=_container_engine()
        ):
            with patch(f"{DISPATCH}._enqueue_create_plan", enqueued):
                ok = _try_wsl_plan_based_creation({"distribution": "Ubuntu"}, "h")
        assert ok is True

    def test_an_engine_predating_the_builder_declines(self):
        # getattr(..., None) rather than hasattr on the module: an older Pro+
        # build loads fine but has no build_wsl_create_plan.
        engine = _container_engine()
        del engine.build_wsl_create_plan
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=engine):
            assert (
                _try_wsl_plan_based_creation({"distribution": "Ubuntu"}, "h") is False
            )

    def test_no_engine_or_no_distribution_declines(self):
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=None):
            assert (
                _try_wsl_plan_based_creation({"distribution": "Ubuntu"}, "h") is False
            )
        with patch(
            f"{DISPATCH}.module_loader.get_module", return_value=_container_engine()
        ):
            assert _try_wsl_plan_based_creation({}, "h") is False

    def test_an_agent_config_is_synthesized_when_the_caller_supplied_none(self):
        captured = {}

        def _build(req):
            captured.update(req.kwargs)
            return {"commands": []}

        engine = _container_engine(build_wsl_create_plan=_build)
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=engine):
            with patch(f"{DISPATCH}._enqueue_create_plan", _Enqueued()):
                _try_wsl_plan_based_creation({"distribution": "Ubuntu"}, "h")
        # A blank config means the child boots with no server to phone home to.
        assert captured["agent_config_yaml"].strip()

    def test_a_builder_that_raises_is_contained(self):
        def _boom(req):
            raise RuntimeError("nope")

        engine = _container_engine(build_wsl_create_plan=_boom)
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=engine):
            assert (
                _try_wsl_plan_based_creation({"distribution": "Ubuntu"}, "h") is False
            )


class TestLxdPlanPath:
    @pytest.mark.parametrize("key", ["container_name", "vm_name"])
    def test_either_name_key_identifies_the_container(self, key):
        enqueued = _Enqueued()
        with patch(
            f"{DISPATCH}.module_loader.get_module", return_value=_container_engine()
        ):
            with patch(f"{DISPATCH}._enqueue_create_plan", enqueued):
                assert _try_lxd_plan_based_creation({key: "c1"}, "h") is True

    def test_no_engine_no_builder_and_no_name_all_decline(self):
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=None):
            assert _try_lxd_plan_based_creation({"container_name": "c1"}, "h") is False
        engine = _container_engine()
        del engine.build_lxd_create_plan
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=engine):
            assert _try_lxd_plan_based_creation({"container_name": "c1"}, "h") is False
        with patch(
            f"{DISPATCH}.module_loader.get_module", return_value=_container_engine()
        ):
            assert _try_lxd_plan_based_creation({}, "h") is False

    def test_a_builder_that_raises_is_contained(self):
        def _boom(req):
            raise RuntimeError("nope")

        engine = _container_engine(build_lxd_create_plan=_boom)
        with patch(f"{DISPATCH}.module_loader.get_module", return_value=engine):
            assert _try_lxd_plan_based_creation({"container_name": "c1"}, "h") is False


class TestEnqueueCreatePlan:
    def test_a_child_host_id_registers_the_result_correlation(self):
        with patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan",
            return_value="msg-9",
        ) as enqueue:
            with patch(
                "backend.services.proplus_dispatch.register_child_host_correlation"
            ) as register:
                out = _enqueue_create_plan(
                    "host-1", {"commands": []}, {"child_host_id": "child-7"}, 2400
                )
        assert out == "msg-9"
        assert enqueue.call_args.kwargs["timeout"] == 2400
        # Without this the HostChild row never leaves "creating".
        register.assert_called_once_with("msg-9", "child-7", "create", "host-1")

    def test_no_child_row_means_nothing_to_correlate(self):
        with patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan", return_value="m"
        ):
            with patch(
                "backend.services.proplus_dispatch.register_child_host_correlation"
            ) as register:
                _enqueue_create_plan("host-1", {"commands": []}, {}, 2400)
        register.assert_not_called()


class TestChildEnrollmentToken:
    def test_no_parent_means_no_token(self):
        assert _child_enrollment_token(None) is None
        assert _child_enrollment_token("") is None

    def test_an_unresolvable_tenant_declines_rather_than_inventing_a_placement(self):
        with patch(
            "backend.services.host_tenant_index.tenant_for_host", return_value=None
        ):
            assert _child_enrollment_token("parent-1") is None

    def test_the_parents_tenant_is_what_the_token_is_minted_for(self):
        with patch(
            "backend.services.host_tenant_index.tenant_for_host",
            return_value="tenant-9",
        ):
            with patch(
                "backend.api.proplus_routes._provisioning_enrollment_token_fn",
                return_value="tok",
            ) as mint:
                assert _child_enrollment_token("parent-1") == "tok"
        mint.assert_called_once_with(tenant_id="tenant-9")

    def test_a_failure_anywhere_in_the_chain_is_contained(self):
        with patch(
            "backend.services.host_tenant_index.tenant_for_host",
            side_effect=RuntimeError("db down"),
        ):
            assert _child_enrollment_token("parent-1") is None


class TestLoadNetworkDetailsPayload:
    def test_a_database_failure_yields_no_payload_rather_than_raising(self):
        # This runs deep in the dispatch chain, possibly off the request
        # thread; raising here would abort a create over a DNS nicety.
        with patch(
            "backend.persistence.partitions.tenant_engine_for_host",
            side_effect=RuntimeError("no engine"),
        ):
            assert _load_network_details_payload("host-1") is None


class TestPublicEntryPoint:
    @pytest.mark.parametrize(
        "child_type,helper",
        [
            ("kvm", "_try_kvm_plan_based_creation"),
            ("bhyve", "_try_bhyve_plan_based_creation"),
            ("vmm", "_try_vmm_plan_based_creation"),
            ("lxd", "_try_lxd_plan_based_creation"),
            ("wsl", "_try_wsl_plan_based_creation"),
        ],
    )
    def test_each_child_type_routes_to_its_own_builder(self, child_type, helper):
        request = SimpleNamespace(child_type=child_type)
        with patch(f"{DISPATCH}.{helper}", return_value=True) as target:
            assert try_plan_based_creation(request, {"p": 1}, "h", None) is True
        target.assert_called_once_with({"p": 1}, "h")

    def test_an_unknown_child_type_declines(self):
        request = SimpleNamespace(child_type="virtualbox")
        assert try_plan_based_creation(request, {}, "h", None) is False
