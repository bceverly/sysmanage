"""
Parser for the section-delimited stdout produced by
``virtualization_engine.build_check_virtualization_support_plan``.

Split out of ``proplus_dispatch`` so ``proplus_dispatch`` stays under the
1000-line module cap pylint enforces.  The functions here are pure —
they take a string and return a dict — and have no SQLAlchemy / queue /
network dependencies, which also makes them trivially unit-testable.

The result dict shape matches what the legacy
``handle_virtualization_support_update`` consumes, so the host-row
capability cache stays consistent regardless of which path produced the
update.
"""

from typing import Any, Dict


def split_capability_sections(stdout: str) -> Dict[str, list]:
    """Split section-delimited stdout (``===KVM===`` etc.) into a dict of
    section_name → list of body lines."""
    sections: Dict[str, list] = {}
    current = None
    for raw in stdout.splitlines():
        line = raw.strip()
        if line.startswith("===") and line.endswith("==="):
            current = line.strip("=").strip().lower()
            sections[current] = []
            continue
        if current is not None and line:
            sections[current].append(line)
    return sections


def section_flag(sections: Dict[str, list], section: str, prefix: str) -> str:
    """Return the value (after ``prefix:``) for the first matching line in
    ``section``, or ``""`` if not present."""
    for entry in sections.get(section, []):
        if entry.startswith(prefix + ":"):
            return entry.split(":", 1)[1].strip()
    return ""


def _kvm_capability(sections: Dict[str, list]):
    cpu = section_flag(sections, "kvm", "cpu")
    devkvm = section_flag(sections, "kvm", "devkvm") == "yes"
    virsh = section_flag(sections, "kvm", "virsh") == "yes"
    libvirtd = section_flag(sections, "kvm", "libvirtd") == "yes"
    if not (cpu in ("vmx", "svm") or virsh or libvirtd or devkvm):
        return None
    return {
        "available": cpu in ("vmx", "svm"),
        "installed": virsh or libvirtd,
        "enabled": devkvm,
        "running": devkvm and libvirtd,
        "initialized": devkvm and libvirtd,
        "needs_install": not (virsh or libvirtd),
        "needs_enable": cpu in ("vmx", "svm") and not devkvm,
        "needs_init": (virsh or libvirtd) and not (devkvm and libvirtd),
    }


def _lxd_capability(sections: Dict[str, list]):
    lxc = section_flag(sections, "lxd", "lxc") == "yes"
    snap_lxd = section_flag(sections, "lxd", "snap_lxd") == "yes"
    lxd_init = section_flag(sections, "lxd", "initialized") == "yes"
    if not (lxc or snap_lxd):
        return None
    return {
        "available": True,
        "installed": lxc,
        "initialized": lxd_init,
        "needs_install": not lxc,
        "needs_init": lxc and not lxd_init,
    }


def _bhyve_capability(sections: Dict[str, list]):
    vmm_loaded = section_flag(sections, "bhyve", "vmm") == "loaded"
    vmbhyve = section_flag(sections, "bhyve", "vmbhyve") == "yes"
    if not (vmm_loaded or vmbhyve):
        return None
    return {
        "available": True,
        "enabled": vmm_loaded,
        "installed": vmbhyve,
        "needs_enable": not vmm_loaded,
        "needs_install": not vmbhyve,
    }


def _vmm_capability(sections: Dict[str, list]):
    vmctl = section_flag(sections, "vmm", "vmctl") == "yes"
    devvmm = section_flag(sections, "vmm", "devvmm") == "yes"
    vmd_running = section_flag(sections, "vmm", "vmd") == "running"
    if not (vmctl or devvmm):
        return None
    return {
        "available": vmctl,
        "kernel_supported": devvmm,
        "running": vmd_running,
        "initialized": vmd_running,
        "enabled": vmd_running,
        "needs_enable": vmctl and not vmd_running,
    }


def _wsl_capability(sections: Dict[str, list]):
    wsl_lines = sections.get("wsl", [])
    if not any(ln and ln != "wsl:none" for ln in wsl_lines):
        return None
    return {"available": True, "enabled": True, "needs_enable": False}


_CAPABILITY_BUILDERS = (
    ("kvm", _kvm_capability),
    ("lxd", _lxd_capability),
    ("bhyve", _bhyve_capability),
    ("vmm", _vmm_capability),
    ("wsl", _wsl_capability),
)


def parse_capability_probe_stdout(stdout: str) -> Dict[str, Any]:
    """Parse the sectioned output of ``build_check_virtualization_support_plan``.

    Translates the section-delimited stdout (===KVM=== / ===LXD=== /
    ===BHYVE=== / ===VMM=== / ===WSL===) into the same capabilities-dict
    shape the legacy ``handle_virtualization_support_update`` consumes.
    """
    sections = split_capability_sections(stdout)
    capabilities: Dict[str, Any] = {}
    supported: list = []
    for name, builder in _CAPABILITY_BUILDERS:
        cap = builder(sections)
        if cap is not None:
            capabilities[name] = cap
            supported.append(name)
    return {"supported_types": supported, "capabilities": capabilities}
