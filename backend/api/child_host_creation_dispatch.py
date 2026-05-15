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

import json
import logging
import secrets
from typing import List, Optional

from backend.licensing.module_loader import module_loader
from backend.persistence import db as db_module
from backend.persistence import models
from backend.utils.verbosity_logger import sanitize_log


def _load_network_details_payload(host_id: str):
    """Load and parse ``host.network_details`` JSON for one host; None on miss."""
    try:
        # pylint: disable=import-outside-toplevel
        from sqlalchemy.orm import sessionmaker

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with session_local() as session:
            host = session.query(models.Host).filter(models.Host.id == host_id).first()
            if not host or not host.network_details:
                return None
            try:
                return json.loads(host.network_details)
            except (TypeError, ValueError):
                return None
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _extract_adapter_candidates(payload) -> List:
    """Extract the list of adapter dicts from a ``network_details`` payload.

    The payload shape varies by hardware collector — sometimes it's a flat
    list of adapter dicts, sometimes a single dict with an ``adapters`` /
    ``interfaces`` / ``network_adapters`` key, sometimes a single adapter
    dict at the top level.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("adapters", "interfaces", "network_adapters"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return [payload]


def _adapter_dns_servers(adapter) -> List[str]:
    """Return DNS server strings declared on a single adapter dict."""
    if not isinstance(adapter, dict):
        return []
    out: List[str] = []
    for key in ("dns_servers", "dns", "nameservers"):
        value = adapter.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, str) and entry and entry not in out:
                    out.append(entry)
        elif isinstance(value, str) and value and value not in out:
            out.append(value)
    return out


def _resolve_parent_dns(host_id: str) -> List[str]:
    """Read DNS servers reported by the parent host's hardware inventory.

    Audit gap fix #5: the legacy agent's ``get_host_dns_servers()`` read
    /etc/resolv.conf on the parent at create time so VMs got the same
    DNS as their host (often a corporate / split-horizon resolver).
    The engine path defaults to Cloudflare when nothing's provided —
    which works for public lookups but breaks corporate DNS records.

    This helper reads ``host.network_details`` (JSON the agent uploads
    via the hardware collector) and pulls DNS servers from the first
    adapter that has any.  Returns an empty list if the host record
    is unavailable or has no DNS info; the engine then falls back to
    its default (1.1.1.1, 1.0.0.1).
    """
    if not host_id:
        return []
    payload = _load_network_details_payload(host_id)
    if payload is None:
        return []
    for adapter in _extract_adapter_candidates(payload):
        dns = _adapter_dns_servers(adapter)
        if dns:
            return dns
    return []


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


def _build_kvm_create_request(
    virt_engine, command_params, base_image_path, host_id: Optional[str] = None
):
    """Construct a ``VmCreateRequest`` from the flat ``command_params`` dict.

    Audit gap fix #5: when ``command_params`` doesn't carry explicit
    ``dns_server`` / ``dns_servers``, fall back to the parent host's
    reported DNS (read from ``host.network_details``).  Without that, the
    engine defaults to public Cloudflare resolvers — works for internet
    DNS but won't resolve corporate/split-horizon records.
    """
    distribution_label = _param_or(command_params, "distribution_label", "ubuntu")
    pub, priv, root_pw = _freebsd_bootstrap_material(distribution_label)
    agent_config_yaml = _param_or(
        command_params,
        "agent_config_yaml",
        None,
    ) or _build_agent_config_yaml(command_params)
    vm_name = command_params["vm_name"]

    # DNS resolution: explicit param wins; otherwise inherit from parent.
    dns_server_param = _param_or(command_params, "dns_server", "")
    dns_servers_param = command_params.get("dns_servers")
    parent_dns: List[str] = []
    if not dns_server_param and not dns_servers_param:
        parent_dns = _resolve_parent_dns(host_id) if host_id else []
    if not dns_server_param and parent_dns:
        dns_server_param = parent_dns[0]

    kwargs = {
        "vm_name": vm_name,
        "hostname": _param_or(command_params, "hostname", vm_name),
        "distribution": distribution_label,
        "username": _param_or(command_params, "username", "admin"),
        "password_hash": _param_or(command_params, "password_hash", ""),
        "memory": _param_or(command_params, "memory", "2G"),
        "disk_size": _param_or(command_params, "disk_size", "20G"),
        "cpus": int(_param_or(command_params, "cpus", 2)),
        "base_image_path": base_image_path,
        "agent_install_commands": _param_or(
            command_params, "agent_install_commands", []
        ),
        "agent_config_yaml": agent_config_yaml,
        "ssh_pubkey": pub,
        "ssh_privkey_pem": priv,
        "temp_root_password": root_pw,
        "server_url": _param_or(command_params, "server_url", ""),
        "server_port": int(_param_or(command_params, "server_port", 8080)),
        "use_https": bool(command_params.get("use_https")),
        "auto_approve_token": _param_or(command_params, "auto_approve_token", ""),
        "autoinstall_mode": _param_or(command_params, "autoinstall_mode", ""),
        "install_iso_url": _param_or(command_params, "install_iso_url", ""),
        "vm_ip": _param_or(command_params, "vm_ip", ""),
        "gateway_ip": _param_or(command_params, "gateway_ip", ""),
        "dns_server": dns_server_param,
        "root_password_hash": _param_or(command_params, "root_password_hash", ""),
        "timezone": _param_or(command_params, "timezone", "UTC"),
        "debian_codename": _param_or(command_params, "debian_codename", "bookworm"),
        "debian_mirror": _param_or(command_params, "debian_mirror", "deb.debian.org"),
        "ubuntu_codename": _param_or(command_params, "ubuntu_codename", "noble"),
        "alpine_version": _param_or(command_params, "alpine_version", "3.20"),
    }
    # Forward dns_servers list if the engine schema accepts it (it does
    # by default; pulled from parent inventory if not explicitly set).
    if isinstance(dns_servers_param, list) and dns_servers_param:
        kwargs["dns_servers"] = dns_servers_param
    elif parent_dns:
        kwargs["dns_servers"] = parent_dns

    return virt_engine.VmCreateRequest(**kwargs)


def _try_kvm_plan_based_creation(command_params, host_id):
    """Build + dispatch a KVM create plan via the virtualization_engine.

    For FreeBSD: engine emits nuageinit user-data + bootstrap.sh + SSH-
    driven post-boot bootstrap.  We generate an ephemeral SSH keypair
    and a one-shot root password here so the engine can wire them into
    the cidata + plan files.

    For Linux: engine emits standard cloud-init runcmd plan.

    Returns True if plan was dispatched, False to surface a 502 to the user.
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
            "engine path declined",
            sanitize_log(vm_name),
            sanitize_log(cloud_image_url),
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
            virt_engine, command_params, base_image_path, host_id=host_id
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
        # Engine path declined; the caller raises 502 to surface the failure.
        _vlog.warning(
            "KVM plan path failed for host %s: %s — engine path declined",
            sanitize_log(host_id),
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# bhyve
# ---------------------------------------------------------------------------


def _build_bhyve_create_request(virt_engine, command_params, raw_image_path, iso_path):
    """Construct a ``BhyveCreateRequest`` from the flat ``command_params`` dict.

    ``cloud_image_url`` is forwarded to the engine when raw_image_path is
    empty (audit PR-13).  The engine internalizes the download + decompress
    + qcow2->raw conversion and uses the resulting raw image as if the
    caller had supplied ``raw_image_path`` directly.
    """
    vm_name = command_params["vm_name"]
    cloud_image_url = ""
    if not raw_image_path and not iso_path:
        cloud_image_url = command_params.get("cloud_image_url") or ""
    return virt_engine.BhyveCreateRequest(
        vm_name=vm_name,
        hostname=_param_or(command_params, "hostname", vm_name),
        template=_param_or(command_params, "template", "freebsd"),
        iso_path=iso_path,
        raw_image_path=raw_image_path,
        cloud_image_url=cloud_image_url,
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
    create, or ``(None, "")`` on synthesis failure (caller surfaces a 502 to the user).  bhyve wants ``.raw``, not ``.qcow2``, so we
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
            "engine path declined",
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


def _bhyve_resolve_install_inputs(virt_engine, vm_name, command_params):
    """Resolve the bhyve install-source inputs.

    Returns ``(raw_image_path, iso_path, cloud_image_url, download_plan, ok)``
    where ``ok`` is False when the inputs are insufficient (caller surfaces a 502 to the user).  ``download_plan`` is non-None only when
    the loaded engine doesn't accept ``cloud_image_url`` directly and we
    had to synthesize a separate download step on the OSS side.
    """
    raw_image_path = command_params.get("raw_image_path") or ""
    iso_path = command_params.get("iso_path") or ""
    cloud_image_url = command_params.get("cloud_image_url") or ""
    download_plan = None

    if not raw_image_path and not iso_path and cloud_image_url:
        engine_supports_cloud_image_url = "cloud_image_url" in (
            getattr(virt_engine.BhyveCreateRequest, "model_fields", None) or {}
        )
        if not engine_supports_cloud_image_url:
            download_plan, raw_image_path = _bhyve_synthesize_download_plan(
                virt_engine, vm_name, cloud_image_url
            )
            if download_plan is None:
                return raw_image_path, iso_path, cloud_image_url, None, False

    if not raw_image_path and not iso_path and not cloud_image_url:
        return raw_image_path, iso_path, cloud_image_url, None, False
    return raw_image_path, iso_path, cloud_image_url, download_plan, True


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

    raw_image_path, iso_path, _cloud_url, download_plan, ok = (
        _bhyve_resolve_install_inputs(virt_engine, vm_name, command_params)
    )
    if not ok:
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
            "bhyve plan path failed for host %s; engine path declined: %s",
            sanitize_log(host_id),
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


def _resolve_vmm_linux_autoinstall(engine_fields, command_params):
    """Resolve linux_autoinstall_{distro,version,iso_url} from params.

    Returns a tuple of three strings (distro, version, iso_url).  The
    distro is empty when the engine doesn't accept the field, when the
    caller didn't request one, or when the requested value isn't in the
    supported allowlist (alpine/debian/ubuntu).
    """
    if "linux_autoinstall_distro" not in engine_fields:
        return "", "", ""
    distro = (_param_or(command_params, "linux_autoinstall_distro", "") or "").lower()
    if distro not in ("alpine", "debian", "ubuntu"):
        return "", "", ""
    version = _param_or(command_params, "linux_autoinstall_version", "")
    iso_url = _param_or(command_params, "linux_autoinstall_iso_url", "")
    return distro, version, iso_url


def _build_vmm_create_request(virt_engine, command_params):
    """Construct a ``VmmCreateRequest`` + autoinstall flag.

    ``password_hash`` in command_params is the per-user password hash;
    map it to ``user_password_hash`` for the engine.  Autoinstall fires
    only when both user + root password hashes are present.

    Forward ``cloud_image_url`` so the engine's legacy
    (non-autoinstall) path can download a Linux cloud image (Ubuntu /
    Debian / Alpine / etc.) and use it as the VM's disk.  Only forwarded
    when autoinstall is False — autoinstall builds its disk from the
    OpenBSD installer.
    """
    vm_name = command_params["vm_name"]
    user_pw_hash = _first_param_or(
        command_params, ("user_password_hash", "password_hash"), ""
    )
    root_pw_hash = _param_or(command_params, "root_password_hash", "")
    engine_fields = getattr(virt_engine.VmmCreateRequest, "model_fields", None) or {}
    linux_autoinstall_distro, linux_autoinstall_version, linux_autoinstall_iso_url = (
        _resolve_vmm_linux_autoinstall(engine_fields, command_params)
    )
    autoinstall = bool(user_pw_hash and root_pw_hash) and not linux_autoinstall_distro
    cloud_image_url = ""
    if (
        not autoinstall
        and not linux_autoinstall_distro
        and "cloud_image_url" in engine_fields
    ):
        cloud_image_url = _param_or(command_params, "cloud_image_url", "")
    kwargs = {
        "vm_name": vm_name,
        "hostname": _param_or(command_params, "hostname", vm_name),
        "memory": _param_or(command_params, "memory", "1G"),
        "disk_size": _param_or(command_params, "disk_size", "20G"),
        "cpus": int(_param_or(command_params, "cpus", 1)),
        "iso_path": _param_or(command_params, "iso_path", ""),
        "disk_path": _param_or(command_params, "disk_path", ""),
        "network_switch": _param_or(command_params, "network_switch", "default"),
        "autoinstall": autoinstall,
        "openbsd_version": _param_or(command_params, "openbsd_version", "7.7"),
        "username": _param_or(command_params, "username", ""),
        "user_password_hash": user_pw_hash,
        "root_password_hash": root_pw_hash,
        "gateway_ip": _param_or(command_params, "gateway_ip", _VMM_DEFAULT_GATEWAY_IP),
        "vm_ip": _param_or(command_params, "vm_ip", _VMM_DEFAULT_VM_IP),
        "server_url": _param_or(command_params, "server_url", ""),
        "server_port": int(_param_or(command_params, "server_port", 8080)),
        "use_https": bool(command_params.get("use_https")),
        "auto_approve_token": _param_or(command_params, "auto_approve_token", ""),
    }
    if cloud_image_url:
        kwargs["cloud_image_url"] = cloud_image_url
    if linux_autoinstall_distro:
        kwargs["linux_autoinstall_distro"] = linux_autoinstall_distro
        if linux_autoinstall_version:
            kwargs["linux_autoinstall_version"] = linux_autoinstall_version
        if linux_autoinstall_iso_url:
            kwargs["linux_autoinstall_iso_url"] = linux_autoinstall_iso_url
    return virt_engine.VmmCreateRequest(**kwargs)


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
            sanitize_log(host_id),
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
            sanitize_log(host_id),
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def try_plan_based_creation(request, command_params, host_id, _session):
    """Attempt plan-based creation via the matching Pro+ engine.

    Each ``child_type`` routes to its engine-specific ``_try_*`` helper
    which builds an apply_deployment_plan and enqueues it.  Returns True
    when a plan was queued, False when the engine declined (caller
    surfaces a 502 to the user).
    """
    if request.child_type == "kvm":
        return _try_kvm_plan_based_creation(command_params, host_id)
    if request.child_type == "bhyve":
        return _try_bhyve_plan_based_creation(command_params, host_id)
    if request.child_type == "vmm":
        return _try_vmm_plan_based_creation(command_params, host_id)
    if request.child_type == "lxd":
        return _try_lxd_plan_based_creation(command_params, host_id)
    if request.child_type == "wsl":
        return _try_wsl_plan_based_creation(command_params, host_id)
    return False
