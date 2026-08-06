# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Virtualization management API endpoints.
Handles WSL, LXD, VMM, and KVM status, enabling, and creating child hosts.

This module is the main router that includes sub-routers for:
- Status endpoints (child_host_virtualization_status)
- Enable/Initialize endpoints (child_host_virtualization_enable)
"""

import json
import uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.child_host_creation_dispatch import try_plan_based_creation
from backend.api.child_host_models import CreateWslChildHostRequest
from backend.api.child_host_utils import (
    audit_log,
    authorize_on_main,
    get_host_or_404,
    raise_engine_declined,
    verify_host_active,
)
from backend.api.child_host_virtualization_enable import router as enable_router
from backend.api.child_host_virtualization_status import router as status_router
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config.config import get_config
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import db, models
from backend.persistence.models import ChildHostDistribution
from backend.persistence.partitions import request_sessionmaker
from backend.security.roles import SecurityRoles
from backend.services.vault_service import VaultService
from backend.utils.password_hash import hash_password_for_os

# Main router that includes sub-routers
router = APIRouter()

# Include status endpoints router
router.include_router(status_router)

# Include enable/initialize endpoints router
router.include_router(enable_router)


# Secret type label for Windows licence keys, so they group in the Secrets UI.
WINDOWS_LICENSE_KEY_TYPE = "windows_license"  # nosec B105  # label, not a password


def _check_container_module():
    """Check if container_engine Pro+ module is available."""
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Container/VM management requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )


def _parse_agent_install_commands(distribution):
    """Resolve the per-distro agent-install command list.

    Phase 11.8 sets the architectural rule that ``virtualization_engine``
    is the single source of truth for these commands — the engine's
    ``_AGENT_INSTALL`` dispatch table emits the canonical PPA / Copr /
    OBS / winget / brew recipes per distro, version-templated where
    relevant.  This function calls into the engine first and falls
    back to the ``ChildHostDistribution.agent_install_commands`` DB
    column only when the engine is unavailable (OSS-only deployment)
    or returns nothing (unknown distro).

    Why bypass the DB row when the engine has an answer?  Because
    seeded DB rows drift — they get populated once and then quietly
    fall behind when the install recipe changes (Phase 11.8 PPA
    migration is the example: the table seed still carried the
    legacy direct-download path months after the engine was wired
    for PPA install).  Routing reads through the engine first makes
    the engine's dispatch table authoritative; the DB column becomes
    a back-compat fallback that engine-aware deployments never touch.
    """
    if not distribution:
        return []

    # Preferred path: engine-resolved commands.  ``distribution_name``
    # and ``distribution_version`` on the row hold the canonical strings
    # (e.g. "Ubuntu" + "24.04" or "openSUSE Leap" + "15.6") that the
    # engine's ``_normalize_distro_id`` helper consumes.
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is not None:
        try:
            engine_cmds = virt_engine.get_agent_install_commands(
                getattr(distribution, "distribution_name", "") or "",
                getattr(distribution, "distribution_version", "") or "",
            )
        except Exception:  # pylint: disable=broad-exception-caught
            engine_cmds = []
        if engine_cmds:
            return list(engine_cmds)

    # Fallback: DB-seeded commands.  Same parsing as before — string
    # JSON or already-decoded list, anything else → empty.
    if not distribution.agent_install_commands:
        return []
    if isinstance(distribution.agent_install_commands, str):
        try:
            return json.loads(distribution.agent_install_commands)
        except json.JSONDecodeError:
            return []
    if isinstance(distribution.agent_install_commands, list):
        return distribution.agent_install_commands
    return []


def _distribution_to_dict(distribution):
    """Convert a ``ChildHostDistribution`` row into a plain dict for the engine."""
    if distribution is None:
        return None
    return {
        "cloud_image_url": getattr(distribution, "cloud_image_url", None),
        "install_identifier": getattr(distribution, "install_identifier", None),
        "distribution_name": getattr(distribution, "distribution_name", None),
        "distribution_version": getattr(distribution, "distribution_version", None),
    }


def _get_cloud_image_url(distribution):
    """Resolve the cloud image URL for a distribution row.

    Delegates to the Pro+ ``virtualization_engine.get_cloud_image_url`` so the
    interpretation of distribution-row fields lives with the (proprietary)
    seed data those rows hold.  Falls back to inline logic when the engine
    isn't loaded — this branch only exists defensively; route-level guards
    elsewhere already ensure Pro+ is loaded before reaching this code path.
    """
    if distribution is None:
        return None
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is not None:
        try:
            return (
                virt_engine.get_cloud_image_url(_distribution_to_dict(distribution))
                or None
            )
        except Exception:  # pylint: disable=broad-exception-caught
            # Engine raised — fall through to inline fallback below.
            pass  # nosec B110 - engine optional; OSS fallback below
    if distribution.cloud_image_url:
        return distribution.cloud_image_url
    if distribution.install_identifier:
        if distribution.install_identifier.startswith("https://"):
            return distribution.install_identifier
    return None


def _validate_platform_for_child_type(host, child_type):
    """Validate that the host platform supports the requested child type."""
    if child_type == "wsl":
        if not host.platform or "Windows" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("WSL is only supported on Windows hosts"),
            )
    elif child_type == "kvm":
        if not host.platform or "Linux" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("KVM is only supported on Linux hosts"),
            )


def _determine_child_name(request):
    """Determine the child host name based on child type and request fields."""
    name_configs = {
        "lxd": (
            "container_name",
            _("Container name is required for LXD containers"),
        ),
        "vmm": (
            "vm_name",
            _("VM name is required for VMM virtual machines"),
        ),
        "kvm": (
            "vm_name",
            _("VM name is required for KVM virtual machines"),
        ),
        "bhyve": (
            "vm_name",
            _("VM name is required for bhyve virtual machines"),
        ),
    }

    config = name_configs.get(request.child_type)
    if config:
        field_name, error_message = config
        child_name = getattr(request, field_name, None)
        if not child_name:
            raise HTTPException(status_code=400, detail=error_message)
        return child_name

    # WSL uses distribution as the name
    return request.distribution


def _resolve_server_url(api_host):
    """Resolve a routable server URL for child host agent configuration.

    If the API host is a listen-all or loopback address, determine the
    actual routable IP so child hosts (e.g. LXD containers) can connect
    back to the server.
    """
    if api_host not in (
        "0.0.0.0",  # nosec B104  # string comparison, not binding
        "localhost",
        "127.0.0.1",
    ):
        return api_host

    import socket

    server_url = "localhost"
    try:
        fqdn = socket.getfqdn()
        resolved_ip = socket.gethostbyname(fqdn)
        if not resolved_ip.startswith("127."):
            return resolved_ip
        # FQDN resolves to loopback; detect actual outbound IP using a
        # UDP socket.  connect() on SOCK_DGRAM merely selects the route
        # — no packet is sent, so the destination address is irrelevant.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))  # NOSONAR  # nosec B104
            server_url = sock.getsockname()[0]
        finally:
            sock.close()
    except Exception:  # nosec B110
        pass

    return server_url


def _hash_child_password(request):
    """Hash the password using the appropriate format for the child type."""
    # VMM/KVM/bhyve use OS-specific hash format (SHA-512 crypt or bcrypt)
    if request.child_type in ("vmm", "kvm", "bhyve"):
        return hash_password_for_os(request.password, request.distribution or "")
    # WSL and LXD use bcrypt
    return bcrypt.hashpw(
        request.password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def _add_vmm_params(params, request):
    """Add VMM-specific parameters (vm_name, iso_url, root_password_hash)."""
    params["vm_name"] = request.vm_name
    if request.iso_url:
        params["iso_url"] = request.iso_url
    root_pwd = request.root_password or request.password
    params["root_password_hash"] = hash_password_for_os(
        root_pwd, request.distribution or ""
    )


def _detect_autoinstall_mode(distribution):
    """Determine which engine autoinstall mode applies to a distribution.

    Delegates to ``virtualization_engine.detect_autoinstall_mode`` (Pro+),
    with an inline fallback for safety when Pro+ isn't loaded.
    """
    if distribution is None:
        return ""
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is not None:
        try:
            return (
                virt_engine.detect_autoinstall_mode(_distribution_to_dict(distribution))
                or ""
            )
        except Exception:  # pylint: disable=broad-exception-caught
            pass  # nosec B110 - engine optional; OSS heuristic below
    if not distribution.install_identifier:
        return ""
    install_id = distribution.install_identifier.lower()
    if not install_id.endswith(".iso"):
        return ""
    name = (distribution.distribution_name or "").lower()
    if "debian" in name:
        return "preseed"
    if "ubuntu" in name:
        return "ubuntu_autoinstall"
    if "alpine" in name:
        return "alpine_apkovl"
    return ""


def _request_attr(request, name: str) -> str:
    """Safely read an optional string attr off the request, defaulting to ''."""
    return getattr(request, name, "") or ""


def _populate_autoinstall_params(params, request, distribution) -> None:
    """Forward autoinstall-mode + ISO URL + network triple defaults.

    Only fires when the distribution's ``install_identifier`` looks like an
    .iso (Debian netinst / Ubuntu Server / Alpine).  Network triple
    defaults are pulled off the request when present; the engine fills in
    its own fallbacks otherwise.
    """
    autoinstall_mode = _detect_autoinstall_mode(distribution)
    if not autoinstall_mode:
        return
    params["autoinstall_mode"] = autoinstall_mode
    params["install_iso_url"] = distribution.install_identifier
    params.setdefault("vm_ip", _request_attr(request, "vm_ip"))
    params.setdefault("gateway_ip", _request_attr(request, "gateway_ip"))
    params.setdefault("dns_server", _request_attr(request, "dns_server"))


def _add_cloud_vm_params(params, request, distribution, mem, disk, cpus):
    """Add cloud VM parameters for KVM/bhyve."""
    params["vm_name"] = request.vm_name
    params["memory"] = request.memory or mem
    params["disk_size"] = request.disk_size or disk
    params["cpus"] = request.cpus or cpus
    cloud_image_url = _get_cloud_image_url(distribution)
    if cloud_image_url:
        params["cloud_image_url"] = cloud_image_url
    # The Pro+ virtualization_engine cloud-init renderer branches on the
    # distribution string (FreeBSD vs Linux) to pick shell, package
    # names, and service-control commands.  Forward the human-readable
    # distribution name so it can detect FreeBSD/etc.
    if distribution and distribution.distribution_name:
        params["distribution_label"] = distribution.distribution_name

    _populate_autoinstall_params(params, request, distribution)


def _is_windows_distribution(install_identifier) -> bool:
    """True for the Windows Server catalog entries.

    Mirrors ``virtualization_engine.is_windows_distribution``.  The check lives
    here too rather than calling the engine because the OSS server must decide
    which fields to forward even when the Pro+ engine is not loaded — otherwise
    a Windows request silently degrades into a Linux one.
    """
    return (install_identifier or "").strip().lower().startswith("windows-server")


def _add_windows_params(params, request) -> None:
    """Forward the Windows Server fields to the engine.

    Only the fields the operator actually set are forwarded; the engine already
    carries sane defaults, and sending an explicit empty string would override
    them (an empty edition is not "use the default", it is "no edition").
    """
    params["windows_edition"] = request.windows_edition or "standard-core"
    params["windows_timezone"] = request.windows_timezone or "UTC"
    params["windows_locale"] = request.windows_locale or "en-US"
    if request.windows_admin_password:
        params["windows_admin_password"] = request.windows_admin_password
    if request.windows_product_key:
        params["windows_product_key"] = request.windows_product_key
    if request.windows_iso_path:
        params["windows_iso_path"] = request.windows_iso_path
    # Domain join: opt-in, and the whole group only travels when a domain is
    # named.  Forwarding a user/password with no domain would put credentials
    # on the config ISO for a join that is never attempted.
    if request.windows_join_domain:
        params["windows_join_domain"] = request.windows_join_domain
        if request.windows_domain_ou:
            params["windows_domain_ou"] = request.windows_domain_ou
        if request.windows_domain_user:
            params["windows_domain_user"] = request.windows_domain_user
        if request.windows_domain_password:
            params["windows_domain_password"] = request.windows_domain_password


def _store_windows_product_key(session, request, child_name):
    """Put the licence key in OpenBAO and return the Secret row's id.

    The key is NEVER written to ``host_child`` — only this id is, so the key
    cannot be read out of the database.  It goes through the same Secret table
    as every other managed secret, which means it shows up in the Secrets
    screen and can be rotated or revoked there like anything else.

    Returns ``None`` when there is no key, which is the normal path: evaluation
    media installs without one.
    """
    key = (request.windows_product_key or "").strip()
    if not key:
        return None
    vault_service = VaultService()
    stored = vault_service.store_secret(
        secret_name=f"windows-key-{child_name}",  # nosec B106  # name, not a password
        secret_data=key,
        secret_type=WINDOWS_LICENSE_KEY_TYPE,  # nosec B106  # type label
        secret_subtype="windows_product_key",  # nosec B106  # subtype label
    )
    secret = models.Secret(
        name=f"windows-key-{child_name}",  # nosec B106  # name, not a password
        secret_type=WINDOWS_LICENSE_KEY_TYPE,  # nosec B106  # type label
        secret_subtype="windows_product_key",  # nosec B106  # subtype label
        vault_token=stored["vault_token"],
        vault_path=stored["vault_path"],
    )
    session.add(secret)
    session.flush()
    return secret.id


def _build_command_params(
    request,
    password_hash,
    agent_install_commands,
    server_url,
    api_port,
    use_https,
    new_child_id,
    auto_approve_token,
    distribution,
):
    """Build the command parameters dict for child host creation."""
    params = {
        "child_type": request.child_type,
        "distribution": request.distribution,
        "hostname": request.hostname,
        "username": request.username,
        "password_hash": password_hash,
        "agent_install_commands": agent_install_commands,
        "server_url": server_url,
        "server_port": api_port,
        "use_https": use_https,
        "child_host_id": str(new_child_id),
    }

    if request.child_type == "lxd":
        params["container_name"] = request.container_name
    elif request.child_type == "vmm":
        _add_vmm_params(params, request)
    elif request.child_type == "kvm":
        _add_cloud_vm_params(params, request, distribution, "2G", "20G", 2)
        # Windows installs from its retail/eval ISO rather than a cloud image,
        # so the cloud-init fields above are inert on this path and the engine
        # branches on the distribution.  Both sets are sent; the engine picks.
        if _is_windows_distribution(request.distribution):
            _add_windows_params(params, request)
    elif request.child_type == "bhyve":
        _add_cloud_vm_params(params, request, distribution, "1G", "20G", 1)

    if auto_approve_token:
        params["auto_approve_token"] = auto_approve_token

    return params


@router.post(
    "/host/{host_id}/virtualization/create-child",
    dependencies=[Depends(JWTBearer())],
)
async def create_child_host_request(
    host_id: str,
    request: CreateWslChildHostRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Request creation of a new child host (WSL instance).
    Requires CREATE_CHILD_HOST permission.
    """
    _check_container_module()

    # Authz is server-global; child-host data + audit are tenant-scoped.  The
    # ref session serves ChildHostDistribution, which is server-global reference
    # data with no copy in the tenant database; keep it open for the whole
    # handler so the loaded distribution row stays attached.
    user = authorize_on_main(current_user, SecurityRoles.CREATE_CHILD_HOST)
    session_local = request_sessionmaker()
    ref_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session, ref_local() as ref_session:
        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify platform compatibility for child type
        _validate_platform_for_child_type(host, request.child_type)

        # Verify the agent is privileged
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with administrator privileges "
                    "to create child hosts"
                ),
            )

        # Determine the child name based on type
        child_name = _determine_child_name(request)

        # Check for existing child host with same name
        existing = (
            session.query(models.HostChild)
            .filter(
                models.HostChild.parent_host_id == host_id,
                models.HostChild.child_name == child_name,
                models.HostChild.child_type == request.child_type,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail=_("A child host named '%s' already exists on this host")
                % child_name,
            )

        # Look up the distribution to get agent install commands (server-global
        # reference data — read on the bootstrap engine via ref_session).
        distribution = (
            ref_session.query(ChildHostDistribution)
            .filter(
                ChildHostDistribution.child_type == request.child_type,
                ChildHostDistribution.install_identifier == request.distribution,
                ChildHostDistribution.is_active == True,  # noqa: E712
            )
            .first()
        )

        agent_install_commands = _parse_agent_install_commands(distribution)

        # Get server URL from config for agent configuration
        config = get_config()
        api_host = config["api"].get("host", "localhost")
        api_port = config["api"].get("port", 8443)
        key_file = config["api"].get("keyFile")
        cert_file = config["api"].get("certFile")
        use_https = bool(key_file and cert_file)
        server_url = _resolve_server_url(api_host)

        # Generate auto-approve token if requested
        auto_approve_token = None
        if request.auto_approve:
            auto_approve_token = str(uuid.uuid4())

        # Create a placeholder HostChild record with "creating" status
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        new_child = models.HostChild(
            parent_host_id=host_id,
            child_name=child_name,
            child_type=request.child_type,
            hostname=request.hostname,
            default_username=request.username,
            status="creating",
            distribution=distribution.distribution_name if distribution else None,
            distribution_version=(
                distribution.distribution_version if distribution else None
            ),
            auto_approve_token=auto_approve_token,
            created_at=now,
            updated_at=now,
        )
        session.add(new_child)
        session.flush()

        # Licence key -> OpenBAO.  Done after the flush so the Secret can be
        # named for the child, and inside the same transaction so a failure
        # here rolls the child row back rather than leaving an orphan whose
        # key was never stored.
        if _is_windows_distribution(request.distribution):
            new_child.windows_key_secret_id = _store_windows_product_key(
                session, request, child_name
            )

        password_hash = _hash_child_password(request)
        command_params = _build_command_params(
            request,
            password_hash,
            agent_install_commands,
            server_url,
            api_port,
            use_https,
            new_child.id,
            auto_approve_token,
            distribution,
        )

        if not try_plan_based_creation(request, command_params, host_id, session):
            raise_engine_declined()

        audit_log(
            user,
            current_user,
            "CREATE",
            str(host.id),
            host.fqdn,
            _("Child host creation requested: %(child_name)s (%(distribution)s)")
            % {"child_name": child_name, "distribution": request.distribution},
            details={
                "child_name": child_name,
                "child_type": request.child_type,
                "distribution": request.distribution,
                "hostname": request.hostname,
                "vm_name": (
                    request.vm_name if request.child_type in ("vmm", "kvm") else None
                ),
                "container_name": (
                    request.container_name if request.child_type == "lxd" else None
                ),
                "memory": request.memory if request.child_type == "kvm" else None,
                "disk_size": request.disk_size if request.child_type == "kvm" else None,
                "cpus": request.cpus if request.child_type == "kvm" else None,
            },
        )

        session.commit()

        if auto_approve_token:
            response_message = _(
                "Child host creation requested. This may take several minutes. "
                "The host will be automatically approved when it connects."
            )
        else:
            response_message = _(
                "Child host creation requested. This may take several minutes."
            )

        return {
            "result": True,
            "success": True,
            "message": response_message,
            "child_host_id": str(new_child.id),
            "auto_approve": bool(auto_approve_token),
        }
