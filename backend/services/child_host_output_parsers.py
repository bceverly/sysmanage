# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
VM / child-host ``list_child_hosts`` stdout parsers.

Extracted from ``backend.services.proplus_dispatch`` to keep that module under
pylint's max-module-lines cap.  Every function here is re-imported back into
``proplus_dispatch`` under its original private name, so callers (and the
sister test module ``test_proplus_dispatch_parsers``) see no change.

These parsers turn the sectioned ``build_list_child_hosts_plan`` stdout — one
``===SECTION===`` block per hypervisor (lxd / kvm / bhyve / bhyve_meta / vmm /
wsl) — into the flat ``child_hosts`` list shape the listing handler consumes.
They are pure string/JSON parsing with no DB or engine dependencies.
"""

import json
from typing import Any, Dict, List, Tuple


def _normalize_status(state: str) -> str:
    """Map per-hypervisor state text to the canonical status the legacy
    handler uses (running / stopped / paused / unknown)."""
    s = state.lower().strip()
    if "run" in s or s in ("locked", "active"):
        return "running"
    if "stop" in s or "shut off" in s or "off" in s or s == "exited":
        return "stopped"
    if "paus" in s or "frozen" in s:
        return "paused"
    if not s:
        return "unknown"
    return s


def _split_section_blocks(stdout: str) -> Dict[str, str]:
    """Split sectioned engine plan stdout into ``{section_name: block_text}``."""
    blocks: Dict[str, str] = {}
    current = None
    buf: list = []
    for raw in stdout.splitlines():
        if raw.startswith("===") and raw.rstrip().endswith("==="):
            if current is not None:
                blocks[current] = "\n".join(buf)
            current = raw.strip("=").strip().lower()
            buf = []
            continue
        if current is not None:
            buf.append(raw)
    if current is not None:
        blocks[current] = "\n".join(buf)
    return blocks


def _parse_lxd_section(text: str) -> list:
    """LXD section is JSON from ``lxc list --format json``."""
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    out = []
    for item in data:
        name = item.get("name") or ""
        if not name:
            continue
        out.append(
            {
                "child_name": name,
                "child_type": "lxd",
                "status": _normalize_status(item.get("status") or ""),
                "hostname": name,
                "type": item.get("type") or "container",
                "architecture": item.get("architecture"),
            }
        )
    return out


def _parse_kvm_section(text: str) -> list:
    """``virsh list --all`` returns a table:

     Id   Name      State
    -----------------------
     1    name1     running
     -    name2     shut off
    """
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Id") or line.startswith("---"):
            continue
        # Split into at most 3 fields: Id (number or '-'), Name, State.
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        out.append(
            {
                "child_name": parts[1],
                "child_type": "kvm",
                "status": _normalize_status(parts[2]),
            }
        )
    return out


def _parse_bhyve_section(text: str) -> list:
    """``vm list`` table:

    NAME  DATASTORE  LOADER  CPU  MEMORY  VNC  AUTO  STATE
    myvm  default    uefi    2    2G      -    Yes   Running (12345)
    """
    out = []
    seen_header = False
    for line in text.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if not seen_header:
            if s.lstrip().startswith("NAME"):
                seen_header = True
            continue
        parts = s.split()
        if not parts:
            continue
        # State is the trailing column(s); take the last 1–2 tokens that
        # form a recognizable state word.
        state = parts[-1] if parts else ""
        # vm-bhyve emits "Running (PID)" — the (PID) is parts[-1] if present.
        if state.startswith("(") and len(parts) >= 2:
            state = parts[-2]
        out.append(
            {
                "child_name": parts[0],
                "child_type": "bhyve",
                "status": _normalize_status(state),
            }
        )
    return out


def _find_top_level_brace_spans(text: str) -> List[Tuple[int, int]]:
    """Inclusive ``(start, end)`` index pairs for each balanced top-level ``{...}``."""
    spans: List[Tuple[int, int]] = []
    depth = 0
    start = -1
    for idx, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                spans.append((start, idx))
    return spans


def _iter_top_level_json_chunks(text: str):
    """Yield top-level ``{...}`` substrings; splits concatenated JSON documents."""
    for start, end in _find_top_level_brace_spans(text):
        chunk = text[start : end + 1].strip()
        if chunk:
            yield chunk


def _try_load_json_object(chunk: str):
    """Return the parsed dict for ``chunk`` or None on any failure."""
    try:
        obj = json.loads(chunk)
    except (TypeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _parse_bhyve_meta_section(text: str) -> Dict[str, Dict[str, Any]]:
    """Parse the ``===BHYVE_META===`` block.

    Each /vm/metadata/<name>.json file is concatenated into the block,
    one JSON document per file separated by newlines.  We split on the
    document boundary (``}\\n{``-style) by attempting to load each
    JSON object as we encounter ``{ ... }`` blocks.

    Returns a dict keyed by ``vm_name`` with whatever metadata fields
    were present (typically ``hostname``, ``distribution``, ``vm_ip``).
    Malformed entries are silently skipped — listing enrichment is
    best-effort.
    """
    if not text or not text.strip():
        return {}
    metas: Dict[str, Dict[str, Any]] = {}
    for chunk in _iter_top_level_json_chunks(text):
        obj = _try_load_json_object(chunk)
        if obj is None:
            continue
        name = obj.get("vm_name") or ""
        if name:
            metas[name] = obj
    return metas


def _parse_vmm_section(text: str) -> list:
    """``vmctl status`` table:

    ID   PID VCPUS  MAXMEM  CURMEM     TTY        OWNER NAME
     1 12345     2   2.0G   1.0G    /dev/ttyp0     root  myvm
    """
    out = []
    seen_header = False
    for line in text.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if not seen_header:
            if s.lstrip().startswith("ID"):
                seen_header = True
            continue
        parts = s.split()
        if len(parts) < 2:
            continue
        # NAME is the last column; presence in vmctl status implies running.
        name = parts[-1]
        out.append(
            {
                "child_name": name,
                "child_type": "vmm",
                "status": "running",
            }
        )
    return out


def _parse_wsl_section(text: str) -> list:
    """``wsl --list --verbose`` output (UTF-16LE on Windows; agent decodes
    before placing into stdout):

          NAME            STATE           VERSION
        * Ubuntu          Running         2
          Ubuntu-22.04    Stopped         2
    """
    out = []
    seen_header = False
    for line in text.splitlines():
        # WSL output may have BOM / leading whitespace; normalize.
        s = line.strip("﻿").rstrip()
        if not s.strip():
            continue
        if not seen_header:
            if "NAME" in s and "STATE" in s:
                seen_header = True
            continue
        # Strip a leading '*' marker for the default distro
        if s.lstrip().startswith("*"):
            s = s.lstrip().lstrip("*").lstrip()
        parts = s.split()
        if len(parts) < 2:
            continue
        out.append(
            {
                "child_name": parts[0],
                "child_type": "wsl",
                "status": _normalize_status(parts[1]),
            }
        )
    return out


def _enrich_bhyve_child_with_meta(child: dict, meta: dict) -> None:
    """Apply hostname / vm_ip / distribution from a metadata blob to a child row."""
    if meta.get("hostname"):
        child["hostname"] = meta["hostname"]
    if meta.get("vm_ip"):
        child["vm_ip"] = meta["vm_ip"]
    distribution = meta.get("distribution")
    if not distribution:
        return
    child.setdefault("distribution", {})
    if isinstance(child["distribution"], dict):
        child["distribution"]["distribution_name"] = distribution


def _parse_list_child_hosts_stdout(stdout: str) -> list:
    """Parse the sectioned ``build_list_child_hosts_plan`` output into the
    same ``child_hosts`` list shape ``handle_child_hosts_list_update``
    consumes.

    Audit gap fix #2: the ``BHYVE_META`` section enriches bhyve listing
    rows with hostname / distribution / vm_ip read from
    ``/vm/metadata/<name>.json``.  vm-bhyve's ``vm list`` only reports
    name + state; without this, the UI listing for bhyve VMs has no
    hostname or IP columns.
    """
    blocks = _split_section_blocks(stdout)
    children: list = []
    children.extend(_parse_lxd_section(blocks.get("lxd", "")))
    children.extend(_parse_kvm_section(blocks.get("kvm", "")))
    bhyve_children = _parse_bhyve_section(blocks.get("bhyve", ""))
    bhyve_metas = _parse_bhyve_meta_section(blocks.get("bhyve_meta", ""))
    for child in bhyve_children:
        meta = bhyve_metas.get(child["child_name"])
        if meta:
            _enrich_bhyve_child_with_meta(child, meta)
    children.extend(bhyve_children)
    children.extend(_parse_vmm_section(blocks.get("vmm", "")))
    children.extend(_parse_wsl_section(blocks.get("wsl", "")))
    return children
