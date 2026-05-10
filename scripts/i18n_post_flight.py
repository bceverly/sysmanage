#!/usr/bin/env python3
"""Post-flight verification for the autonomous i18n translation pass.

Reports per-locale stats so we can see at a glance whether the work
landed cleanly:

  * placeholders remaining ([TODO] / [MISSING:] markers)
  * English-passthrough leaves remaining (locale value == en value)
  * keys with format-spec mismatches between en and locale (would
    crash at runtime if used in printf-style formatting)

Run from any cwd; uses absolute paths to all four repos.
"""
import json
import re
import sys
from pathlib import Path

LOCALES = {
    "OSS frontend": Path(
        "/home/bceverly/dev/sysmanage/frontend/public/locales"
    ),
    "Pro+ frontend": Path(
        "/home/bceverly/dev/sysmanage-professional-plus/frontend/public/locales"
    ),
    "Docs": Path("/home/bceverly/dev/sysmanage-docs/assets/locales"),
}
PRINTF = re.compile(
    # Drop the SPACE modifier from the flag class so non-English number
    # formatting like "100 %", "20 %", "70 %" doesn't match as " %d" /
    # " %s" / " %fmt".  Real printf code in this repo never uses the
    # ``% d`` (leading-space) flag.  Negative lookbehind on a digit also
    # rejects ``20%`` (no flag, just a literal percent immediately after
    # a digit) which the d-conversion path would otherwise flag.
    r"(?<!\d)%[#0\-+]?\d*\.?\d*[diouxXeEfFgGcrsa%]|%\([^)]+\)[diouxXeEfFgGcrsa]"
)


def flatten(d, prefix=""):
    out = {}
    for key, value in d.items():
        joined = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, joined))
        else:
            out[joined] = value
    return out


def specs(s):
    return tuple(sorted(m for m in PRINTF.findall(s) if m != "%%"))


def report_json_repo(label, dir_path, en_filename="en/translation.json"):
    print(f"\n=== {label} ===")
    en_path = dir_path / en_filename if "/" in en_filename else dir_path / en_filename
    if not en_path.exists():
        # Docs uses flat <lang>.json
        en_path = dir_path / "en.json"
    en = flatten(json.loads(en_path.read_text(encoding="utf-8")))
    total_placeholders = total_passthrough = total_spec_mismatch = 0

    for path in sorted(dir_path.rglob("*.json")):
        # Skip the en file itself + any non-locale json (analyses, etc.)
        if path == en_path:
            continue
        if path.stem == "missing_keys_analysis":
            continue
        # Find the language code: parent dir for OSS/Pro+, stem for docs
        lang = path.parent.name if path.parent != dir_path else path.stem
        if lang == "en":
            continue
        try:
            data = flatten(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        placeholders = sum(
            1
            for v in data.values()
            if isinstance(v, str) and (v.startswith("[TODO]") or v.startswith("[MISSING:"))
        )
        passthrough = sum(
            1
            for k in en
            if isinstance(en[k], str)
            and isinstance(data.get(k), str)
            and en[k] == data[k]
            and len(en[k]) > 4
        )
        spec_mismatch = sum(
            1
            for k in en
            if isinstance(en[k], str)
            and isinstance(data.get(k), str)
            and specs(en[k]) != specs(data[k])
        )
        print(
            f"  {lang:8s}  placeholders={placeholders:4d}  "
            f"passthrough={passthrough:5d}  "
            f"spec_mismatch={spec_mismatch:4d}"
        )
        total_placeholders += placeholders
        total_passthrough += passthrough
        total_spec_mismatch += spec_mismatch
    print(f"  TOTAL     {total_placeholders=}  {total_passthrough=}  {total_spec_mismatch=}")


def _resolve_multiline(block, key):
    """Resolve a key's multi-line value in a PO block.

    PO format allows ``msgstr ""`` followed by continuation lines like
    ``"actual text"``.  A naive regex against just ``msgstr "(.*)"``
    sees the empty initial line and reports the entry as untranslated
    even when the next lines have real content.  This walker correctly
    accumulates continuations.
    """
    out = []
    found = False
    for line in block.splitlines():
        stripped = line.strip()
        if found:
            cont = re.match(r'^"(.*)"$', stripped)
            if cont:
                out.append(cont.group(1))
                continue
            break
        match = re.match(rf'^{key}\s+"(.*)"$', stripped)
        if match:
            out.append(match.group(1))
            found = True
    return "".join(out) if found else None


def report_po_repo():
    print("\n=== Agent .po ===")
    AGENT = Path("/home/bceverly/dev/sysmanage-agent/src/i18n/locales")
    total_untranslated = total_spec_mismatch = 0
    for po in sorted(AGENT.rglob("messages.po")):
        text = po.read_text(encoding="utf-8")
        blocks = [b for b in re.split(r"\n\n+", text) if b.strip()]
        untranslated = spec_mismatch = 0
        for block in blocks:
            msgid = _resolve_multiline(block, "msgid")
            msgstr = _resolve_multiline(block, "msgstr")
            if not msgid:  # skip header (empty msgid)
                continue
            if not msgstr:
                untranslated += 1
                continue
            if specs(msgid) != specs(msgstr):
                spec_mismatch += 1
        lang = po.parts[-3]
        print(
            f"  {lang:8s}  untranslated={untranslated:4d}  "
            f"spec_mismatch={spec_mismatch:4d}"
        )
        total_untranslated += untranslated
        total_spec_mismatch += spec_mismatch
    print(f"  TOTAL     {total_untranslated=}  {total_spec_mismatch=}")
    if total_spec_mismatch:
        print("  ❗ format-spec mismatches WILL crash at runtime — investigate before shipping")
    else:
        print("  ✓ no format-spec mismatches")


def main():
    for label, path in LOCALES.items():
        if path.exists():
            report_json_repo(label, path)
        else:
            print(f"\n=== {label} === (path not found: {path})")
    report_po_repo()


if __name__ == "__main__":
    main()
