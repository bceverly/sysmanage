"""
Plan-based child host creation dispatch.

Extracted from ``child_host_virtualization.py`` to keep that module under the
1000-line lint cap.  This module contains every per-engine ``_try_*_plan_based_creation``
helper plus the small request-builder + utility helpers they share.

Public entry point: ``_try_plan_based_creation`` — called from
``child_host_virtualization.create_child_host_request``.  Returns ``True`` if a
Pro+ engine plan was queued, ``False`` to fall through to the legacy
``create_child_host`` WS dispatch.

NOTE: the legacy dispatch is intentionally kept as a fallback (per the user's
directive to retain the historical implementation as architectural reference
until the engine path is fully validated in production).
"""

import logging
import secrets

from backend.licensing.module_loader import module_loader
from backend.persistence import models


def _enqueue_create_plan(host_id: str, plan: dict, command_params: dict, timeout: int):
    """Enqueue a create plan and register a child_host_op correlation.

    Reads ``child_host_id`` from ``command_params`` (set by the server-side
    HostChild row insert in ``create_child_host_request``) so the result
    handler can update the row's status when the agent reports back.
    """
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import (
        enqueue_apply_plan,
        register_child_host_correlation,
    )

    message_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=timeout)
    child_id = command_params.get("child_host_id")
    if child_id:
        register_child_host_correlation(
            message_id, str(child_id), "create", str(host_id)
        )
    return message_id


# ---------------------------------------------------------------------------
# Small param-extraction helpers (used only inside this module)
# ---------------------------------------------------------------------------


def _param_or(params, key, default):
    """Return ``params.get(key)`` if truthy, else ``default``.

    Wraps the common ``params.get(k) or default`` idiom so callers building
    request objects from flat dicts don't accumulate one cognitive-complexity
    point per field.
    """
    return params.get(key) or default


def _first_param_or(params, keys, default):
    """Return the first truthy value among ``params[keys[i]]``, else ``default``."""
    for key in keys:
        value = params.get(key)
        if value:
            return value
    return default


# ---------------------------------------------------------------------------
# Agent config YAML — server-side mirror of container_engine helper
# ---------------------------------------------------------------------------


def _build_agent_config_yaml(command_params):
    """Generate /etc/sysmanage-agent.yaml content for a child KVM VM.

    Mirrors container_engine._generate_agent_config_yaml so the agent
    inside the guest can register back to this server.  Required because
    without a config file the spawned agent has no idea where its parent
    server lives, and the host never appears in the UI.
    """
    server_url = command_params.get("server_url") or "localhost"
    server_port = command_params.get("server_port") or 8443
    use_https = bool(command_params.get("use_https"))
    auto_approve_token = command_params.get("auto_approve_token")

    lines = [
        "# SysManage Agent Configuration (auto-generated)",
        "server:",
        f'  hostname: "{server_url}"',
        f"  port: {server_port}",
        f"  use_https: {str(use_https).lower()}",
        "",
        "logging:",
        '  level: "INFO"',
        "",
        "websocket:",
        "  reconnect_interval: 10",
        "",
        "script_execution:",
        "  enabled: true",
        "  timeout: 300",
        "  max_concurrent: 3",
        "  allowed_shells:",
        '    - "bash"',
        '    - "sh"',
        '    - "dash"',
    ]
    if auto_approve_token:
        lines.extend(
            [
                "",
                "auto_approve:",
                f'  token: "{auto_approve_token}"',
            ]
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FreeBSD bootstrap helpers (used by KVM create plan for FreeBSD guests)
# ---------------------------------------------------------------------------


def _is_freebsd_distribution(distribution: str) -> bool:
    """Server-side mirror of the engine's FreeBSD detection."""
    if not distribution:
        return False
    lower = distribution.lower()
    return "freebsd" in lower or "bsd" in lower


def _generate_freebsd_bootstrap_keypair():
    """Return (openssh_pubkey_str, pem_privkey_str) for one-shot bootstrap.

    Uses the existing ``cryptography`` dep — no new requirements.  Keys
    are 2048-bit RSA (FreeBSD's stock OpenSSH supports it) and live only
    long enough for the SSH-bootstrap step on the agent.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privkey_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pubkey = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        .decode("utf-8")
    )
    return pubkey + " sysmanage-bootstrap", privkey_pem


_KVM_DECOMPRESS_EXTENSIONS = (("xz", "xz"), ("gz", "gz"), ("bz2", "bz2"))


def _derive_kvm_base_image_path(cloud_image_url: str, vm_name: str):
    """Return ``(base_image_path, decompress_mode)`` from the cloud image URL.

    The base image is named after the URL's basename (with a trailing
    ``.xz``/``.gz``/``.bz2`` stripped if present) so re-runs against the
    same VM name don't re-download.
    """
    url_basename = cloud_image_url.rsplit("/", 1)[-1] or f"{vm_name}.qcow2"
    decompress = ""
    local_qcow2_name = url_basename
    for ext, mode in _KVM_DECOMPRESS_EXTENSIONS:
        if url_basename.endswith(f".{ext}"):
            decompress = mode
            local_qcow2_name = url_basename[: -(len(ext) + 1)]
            break
    return f"/var/lib/libvirt/images/{local_qcow2_name}", decompress


def _freebsd_bootstrap_material(distribution_label: str):
    """Return ``(ssh_pubkey, ssh_privkey_pem, temp_root_password)`` for
    FreeBSD KVM creates; empty strings for non-FreeBSD distros."""
    if not _is_freebsd_distribution(distribution_label):
        return "", "", ""
    pub, priv = _generate_freebsd_bootstrap_keypair()
    return pub, priv, secrets.token_urlsafe(24)


# ---------------------------------------------------------------------------
# KVM
# ---------------------------------------------------------------------------


def _build_kvm_create_request(virt_engine, command_params, base_image_path):
    """Construct a ``VmCreateRequest`` from the flat ``command_params`` dict."""
    distribution_label = _param_or(command_params, "distribution_label", "ubuntu")
    pub, priv, root_pw = _freebsd_bootstrap_material(distribution_label)
    agent_config_yaml = _param_or(
        command_params,
        "agent_config_yaml",
        None,
    ) or _build_agent_config_yaml(command_params)
    vm_name = command_params["vm_name"]
    return virt_engine.VmCreateRequest(
        vm_name=vm_name,
        hostname=_param_or(command_params, "hostname", vm_name),
        distribution=distribution_label,
        username=_param_or(command_params, "username", "admin"),
        password_hash=_param_or(command_params, "password_hash", ""),
        memory=_param_or(command_params, "memory", "2G"),
        disk_size=_param_or(command_params, "disk_size", "20G"),
        cpus=int(_param_or(command_params, "cpus", 2)),
        base_image_path=base_image_path,
        agent_install_commands=_param_or(command_params, "agent_install_commands", []),
        agent_config_yaml=agent_config_yaml,
        ssh_pubkey=pub,
        ssh_privkey_pem=priv,
        temp_root_password=root_pw,
        server_url=_param_or(command_params, "server_url", ""),
        server_port=int(_param_or(command_params, "server_port", 8080)),
        use_https=bool(command_params.get("use_https")),
        auto_approve_token=_param_or(command_params, "auto_approve_token", ""),
        autoinstall_mode=_param_or(command_params, "autoinstall_mode", ""),
        install_iso_url=_param_or(command_params, "install_iso_url", ""),
        vm_ip=_param_or(command_params, "vm_ip", ""),
        gateway_ip=_param_or(command_params, "gateway_ip", ""),
        dns_server=_param_or(command_params, "dns_server", ""),
        root_password_hash=_param_or(command_params, "root_password_hash", ""),
        timezone=_param_or(command_params, "timezone", "UTC"),
        debian_codename=_param_or(command_params, "debian_codename", "bookworm"),
        debian_mirror=_param_or(command_params, "debian_mirror", "deb.debian.org"),
        ubuntu_codename=_param_or(command_params, "ubuntu_codename", "noble"),
        alpine_version=_param_or(command_params, "alpine_version", "3.20"),
    )


def _try_kvm_plan_based_creation(command_params, host_id):
    """Build + dispatch a KVM create plan via the virtualization_engine.

    For FreeBSD: engine emits nuageinit user-data + bootstrap.sh + SSH-
    driven post-boot bootstrap.  We generate an ephemeral SSH keypair
    and a one-shot root password here so the engine can wire them into
    the cidata + plan files.

    For Linux: engine emits standard cloud-init runcmd plan.

    Returns True if plan was dispatched, False to fall through to legacy.
    """
    _vlog = logging.getLogger(__name__)
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is None:
        _vlog.warning("KVM plan path: virtualization_engine not loaded")
        return False

    cloud_image_url = command_params.get("cloud_image_url") or ""
    vm_name = command_params.get("vm_name")
    if not vm_name or not cloud_image_url:
        _vlog.warning(
            "KVM plan path: missing vm_name=%r or cloud_image_url=%r — "
            "falling back to legacy WS dispatch",
            vm_name,
            cloud_image_url,
        )
        return False

    try:
        base_image_path, decompress = _derive_kvm_base_image_path(
            cloud_image_url, vm_name
        )
        download_req = virt_engine.ImageDownloadRequest(
            url=cloud_image_url,
            dest_path=base_image_path,
            decompress=decompress,
        )
        download_plan = virt_engine.build_kvm_image_download_plan(download_req)
        create_req = _build_kvm_create_request(
            virt_engine, command_params, base_image_path
        )
        create_plan = virt_engine.build_kvm_create_plan(create_req)

        # Merge: download files (none) + create files, download cmds + create cmds.
        merged_plan = {
            "engine": "virtualization_engine",
            "hypervisor": "kvm",
            "action": "create",
            "vm_name": vm_name,
            "files": list(create_plan.get("files") or []),
            "commands": list(download_plan.get("commands") or [])
            + list(create_plan.get("commands") or []),
        }

        _enqueue_create_plan(host_id, merged_plan, command_params, 2400)
        return True
    except Exception as exc:  # nosec B110  pylint: disable=broad-exception-caught
        # Fall back to legacy WS command path on any failure
        _vlog.warning(
            "KVM plan path failed for host %s: %s — falling back to legacy WS",
            host_id,
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# bhyve
# ---------------------------------------------------------------------------


def _build_bhyve_create_request(virt_engine, command_params, raw_image_path, iso_path):
    """Construct a ``BhyveCreateRequest`` from the flat ``command_params`` dict."""
    vm_name = command_params["vm_name"]
    return virt_engine.BhyveCreateRequest(
        vm_name=vm_name,
        hostname=_param_or(command_params, "hostname", vm_name),
        template=_param_or(command_params, "template", "freebsd"),
        iso_path=iso_path,
        raw_image_path=raw_image_path,
        memory=_param_or(command_params, "memory", "2G"),
        disk_size=_param_or(command_params, "disk_size", "20G"),
        cpus=int(_param_or(command_params, "cpus", 2)),
        network_switch=_param_or(command_params, "network_switch", "public"),
        username=_param_or(command_params, "username", ""),
        password_hash=_param_or(command_params, "password_hash", ""),
        server_url=_param_or(command_params, "server_url", ""),
        server_port=int(_param_or(command_params, "server_port", 8080)),
        use_https=bool(command_params.get("use_https")),
        auto_approve_token=_param_or(command_params, "auto_approve_token", ""),
    )


def _bhyve_synthesize_download_plan(virt_engine, vm_name, cloud_image_url):
    """Return ``(download_plan, raw_image_path)`` for a cloud-image bhyve
    create, or ``(None, "")`` on synthesis failure (caller falls back to
    legacy WS dispatch).  bhyve wants ``.raw``, not ``.qcow2``, so we
    rewrite the suffix derived by ``_derive_kvm_base_image_path``."""
    try:
        base_image_path, decompress = _derive_kvm_base_image_path(
            cloud_image_url, vm_name
        )
        if base_image_path.endswith(".qcow2"):
            base_image_path = base_image_path[: -len(".qcow2")] + ".raw"
        download_req = virt_engine.ImageDownloadRequest(
            url=cloud_image_url,
            dest_path=base_image_path,
            decompress=decompress,
        )
        return (
            virt_engine.build_kvm_image_download_plan(download_req),
            base_image_path,
        )
    except Exception as exc:  # nosec B110
        logging.getLogger(__name__).warning(
            "bhyve plan path: image download synthesis failed (%s); "
            "falling back to legacy WS dispatch",
            exc,
        )
        return None, ""


def _bhyve_merge_download_into_create_plan(create_plan, download_plan, vm_name):
    """Prepend download_plan commands to create_plan so raw_image_path
    exists before the bhyve create steps run."""
    return {
        "engine": create_plan["engine"],
        "hypervisor": create_plan["hypervisor"],
        "action": create_plan["action"],
        "vm_name": vm_name,
        "files": list(create_plan.get("files") or []),
        "commands": list(download_plan.get("commands") or [])
        + list(create_plan.get("commands") or []),
    }


def _try_bhyve_plan_based_creation(command_params, host_id):
    """Build + dispatch a bhyve create plan via the virtualization_engine.

    For raw FreeBSD images: engine emits a firstboot rc.d script and an
    image-mod helper that the parent agent runs (mdconfig+mount+inject+
    unmount), then vm-bhyve creates+starts the VM.  On first boot the
    sysmanage-agent is auto-installed.

    When neither ``raw_image_path`` nor ``iso_path`` is supplied but a
    ``cloud_image_url`` is in the params, the server prepends a download
    step (using ``build_kvm_image_download_plan`` — the URL semantics
    are identical) and points raw_image_path at the downloaded file.
    """
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is None:
        return False
    vm_name = command_params.get("vm_name")
    if not vm_name:
        return False
    raw_image_path = command_params.get("raw_image_path") or ""
    iso_path = command_params.get("iso_path") or ""
    cloud_image_url = command_params.get("cloud_image_url") or ""

    download_plan = None
    if not raw_image_path and not iso_path and cloud_image_url:
        download_plan, raw_image_path = _bhyve_synthesize_download_plan(
            virt_engine, vm_name, cloud_image_url
        )
        if download_plan is None:
            return False

    # If we still have neither, the engine plan would be "just vm create"
    # with no install — fall back to legacy.
    if not raw_image_path and not iso_path:
        return False

    try:
        create_plan = virt_engine.build_bhyve_create_plan(
            _build_bhyve_create_request(
                virt_engine, command_params, raw_image_path, iso_path
            )
        )
        merged_plan = (
            _bhyve_merge_download_into_create_plan(create_plan, download_plan, vm_name)
            if download_plan is not None
            else create_plan
        )
        _enqueue_create_plan(host_id, merged_plan, command_params, 3600)
        return True
    except Exception as exc:  # nosec B110  pylint: disable=broad-exception-caught
        logging.getLogger(__name__).warning(
            "bhyve plan path failed for host %s; falling back to legacy WS: %s",
            host_id,
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# VMM (OpenBSD vmd)
# ---------------------------------------------------------------------------

# RFC 6598 carrier-grade-NAT addresses used solely as in-engine fallback
# defaults for the OpenBSD VMM autoinstall network.  These never appear on
# any wire — vmd's bridged tap lives on the parent host's RFC1918 LAN.
# Extracted as constants because SonarQube flags inline IP literals as a
# security hotspot; keeping them here makes the intent explicit.
_VMM_DEFAULT_GATEWAY_IP = "100.64.0.1"  # nosec B104  # NOSONAR
_VMM_DEFAULT_VM_IP = "100.64.0.101"  # nosec B104  # NOSONAR


def _build_vmm_create_request(virt_engine, command_params):
    """Construct a ``VmmCreateRequest`` + autoinstall flag.

    ``password_hash`` in command_params is the per-user password hash;
    map it to ``user_password_hash`` for the engine.  Autoinstall fires
    only when both user + root password hashes are present.
    """
    vm_name = command_params["vm_name"]
    user_pw_hash = _first_param_or(
        command_params, ("user_password_hash", "password_hash"), ""
    )
    root_pw_hash = _param_or(command_params, "root_password_hash", "")
    return virt_engine.VmmCreateRequest(
        vm_name=vm_name,
        hostname=_param_or(command_params, "hostname", vm_name),
        memory=_param_or(command_params, "memory", "1G"),
        disk_size=_param_or(command_params, "disk_size", "20G"),
        cpus=int(_param_or(command_params, "cpus", 1)),
        iso_path=_param_or(command_params, "iso_path", ""),
        disk_path=_param_or(command_params, "disk_path", ""),
        network_switch=_param_or(command_params, "network_switch", "default"),
        autoinstall=bool(user_pw_hash and root_pw_hash),
        openbsd_version=_param_or(command_params, "openbsd_version", "7.7"),
        username=_param_or(command_params, "username", ""),
        user_password_hash=user_pw_hash,
        root_password_hash=root_pw_hash,
        gateway_ip=_param_or(command_params, "gateway_ip", _VMM_DEFAULT_GATEWAY_IP),
        vm_ip=_param_or(command_params, "vm_ip", _VMM_DEFAULT_VM_IP),
        server_url=_param_or(command_params, "server_url", ""),
        server_port=int(_param_or(command_params, "server_port", 8080)),
        use_https=bool(command_params.get("use_https")),
        auto_approve_token=_param_or(command_params, "auto_approve_token", ""),
    )


def _try_vmm_plan_based_creation(command_params, host_id):
    """Build + dispatch a VMM (OpenBSD vmd) create plan via the engine.

    When autoinstall fields are present (root_password_hash etc.), the
    engine emits the full httpd-prep + sets-download + bsd.rd-embed
    orchestration that the agent's restored child_host_vmm code used.
    """
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is None:
        return False
    if not command_params.get("vm_name"):
        return False
    try:
        create_req = _build_vmm_create_request(virt_engine, command_params)
        plan = virt_engine.build_vmm_create_plan(create_req)

        _enqueue_create_plan(host_id, plan, command_params, 2400)
        return True
    except Exception:  # nosec B110  pylint: disable=broad-exception-caught
        return False


# ---------------------------------------------------------------------------
# WSL
# ---------------------------------------------------------------------------


def _try_wsl_plan_based_creation(command_params, host_id):
    """Build + dispatch a WSL create plan via the container_engine.

    Uses the new ``build_wsl_create_plan`` apply_deployment_plan path
    with 1800 s on ``wsl --install`` and the explicit systemd-restart
    dance preserved from the legacy execute_command_sequence path.
    """
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        return False
    builder = getattr(container_engine, "build_wsl_create_plan", None)
    if builder is None:
        return False

    distribution = command_params.get("distribution")
    if not distribution:
        return False
    try:
        req = container_engine.WslCreateRequest(
            distribution=distribution,
            hostname=_param_or(
                command_params,
                "hostname",
                command_params.get("vm_name") or distribution,
            ),
            username=_param_or(command_params, "username", "admin"),
            password_hash=_param_or(command_params, "password_hash", ""),
            agent_install_commands=_param_or(
                command_params, "agent_install_commands", []
            ),
            agent_config_yaml=_param_or(command_params, "agent_config_yaml", "")
            or _build_agent_config_yaml(command_params),
        )
        plan = builder(req)

        # pylint: disable=import-outside-toplevel
        _enqueue_create_plan(host_id, plan, command_params, 2400)
        return True
    except Exception as exc:  # nosec B110  pylint: disable=broad-exception-caught
        logging.getLogger(__name__).warning(
            "WSL engine plan path failed for host %s; falling back to legacy "
            "execute_command_sequence: %s",
            host_id,
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# LXD
# ---------------------------------------------------------------------------


def _try_lxd_plan_based_creation(command_params, host_id):
    """Build + dispatch an LXD create plan via the container_engine.

    Uses the new ``build_lxd_create_plan`` apply_deployment_plan path
    which has a 1800 s timeout on ``lxc launch`` (so first-time image
    pulls don't time out at 120 s like the legacy path) and an
    IPv4-or-IPv6 wait-for-network step.

    Returns True if dispatched, False to fall through to the legacy
    ``create_container_with_plan`` execute_command_sequence path
    (kept for now as architectural reference per audit).
    """
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        return False
    builder = getattr(container_engine, "build_lxd_create_plan", None)
    if builder is None:
        return False

    container_name = command_params.get("container_name") or command_params.get(
        "vm_name"
    )
    if not container_name:
        return False
    try:
        req = container_engine.LxdCreateRequest(
            container_name=container_name,
            distribution=_param_or(command_params, "distribution", ""),
            hostname=_param_or(command_params, "hostname", container_name),
            username=_param_or(command_params, "username", "admin"),
            password_hash=_param_or(command_params, "password_hash", ""),
            agent_install_commands=_param_or(
                command_params, "agent_install_commands", []
            ),
            agent_config_yaml=_param_or(command_params, "agent_config_yaml", "")
            or _build_agent_config_yaml(command_params),
        )
        plan = builder(req)

        # pylint: disable=import-outside-toplevel
        _enqueue_create_plan(host_id, plan, command_params, 2400)
        return True
    except Exception as exc:  # nosec B110  pylint: disable=broad-exception-caught
        logging.getLogger(__name__).warning(
            "LXD engine plan path failed for host %s; falling back to legacy "
            "execute_command_sequence: %s",
            host_id,
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def try_plan_based_creation(request, command_params, host_id, session):
    """Attempt plan-based creation via the matching Pro+ engine.

    For lxd:     routes through container_engine apply_deployment_plan
                 (build_lxd_create_plan) with execute_command_sequence
                 fallback for environments without the engine.
    For wsl:     routes through container_engine apply_deployment_plan
                 (build_wsl_create_plan) with execute_command_sequence fallback.
    For kvm:     routes through virtualization_engine (Phase 10.1).
    For bhyve:   routes through virtualization_engine (raw image path).
    For vmm:     routes through virtualization_engine (autoinstall path).

    Returns True if plan-based creation was used, False otherwise.
    """
    if request.child_type == "kvm":
        return _try_kvm_plan_based_creation(command_params, host_id)
    if request.child_type == "bhyve":
        return _try_bhyve_plan_based_creation(command_params, host_id)
    if request.child_type == "vmm":
        return _try_vmm_plan_based_creation(command_params, host_id)

    # Try the new apply_deployment_plan path first for LXD/WSL; fall
    # through to the legacy execute_command_sequence service method only
    # if the new builder isn't available or raised.
    if request.child_type == "lxd" and _try_lxd_plan_based_creation(
        command_params, host_id
    ):
        return True
    if request.child_type == "wsl" and _try_wsl_plan_based_creation(
        command_params, host_id
    ):
        return True

    if request.child_type not in ("lxd", "wsl"):
        return False

    try:
        container_engine = module_loader.get_module("container_engine")
        if container_engine is None:
            return False

        # LEGACY: execute_command_sequence shape with hardcoded per-step
        # timeouts.  Kept as fallback + architectural reference until the
        # apply_deployment_plan path is fully validated for both lxd and
        # wsl (audit PR-05 / PR-07).
        service_cls = getattr(container_engine, "ContainerEngineServiceImpl", None)
        if not service_cls or not hasattr(service_cls, "create_container_with_plan"):
            return False

        ce_logger = logging.getLogger("container_engine")
        service = service_cls(db=session, models=models, logger=ce_logger)
        steps = service.create_container_with_plan(
            child_type=request.child_type,
            params=command_params,
            host_id=host_id,
            db_session=session,
        )
        return steps is not None
    except Exception:  # nosec B110
        return False
