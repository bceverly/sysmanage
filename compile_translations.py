#!/usr/bin/env python3
"""
Script to compile .po files to .mo files for backend translations
"""

import os
import sys

def simple_po_to_mo(po_file, mo_file):
    """
    Simple conversion from .po to .mo file format
    """
    import struct

    entries = {}

    # Read .po file
    with open(po_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse .po content
    lines = content.split('\n')
    msgid = None
    msgstr = None
    current_type = None

    for line in lines:
        line = line.strip()
        if line.startswith('msgid "'):
            if msgid is not None and msgstr is not None and msgid != "":
                entries[msgid] = msgstr
            msgid = line[7:-1]  # Remove 'msgid "' and '"'
            current_type = 'id'
        elif line.startswith('msgstr "'):
            msgstr = line[8:-1]  # Remove 'msgstr "' and '"'
            current_type = 'str'
        elif line.startswith('"') and line.endswith('"') and current_type:
            text = line[1:-1]  # Remove quotes
            if current_type == 'id':
                msgid += text
            elif current_type == 'str':
                msgstr += text
        elif line == "" or line.startswith('#'):
            if msgid is not None and msgstr is not None and msgid != "":
                entries[msgid] = msgstr
            msgid = None
            msgstr = None
            current_type = None

    # Add final entry
    if msgid is not None and msgstr is not None and msgid != "":
        entries[msgid] = msgstr

    # Create .mo file
    keys = list(entries.keys())
    values = list(entries.values())

    # Encode strings
    kencoded = [k.encode('utf-8') for k in keys]
    vencoded = [v.encode('utf-8') for v in values]

    # Sort by keys for binary search
    pairs = list(zip(kencoded, vencoded))
    pairs.sort()

    # Create binary format
    keystart = 7 * 4 + 16 * len(pairs)
    valuestart = keystart
    for k, v in pairs:
        valuestart += len(k) + 1

    output = []

    # Header
    output.append(struct.pack("I", 0x950412de))  # Magic number
    output.append(struct.pack("I", 0))           # Version
    output.append(struct.pack("I", len(pairs)))  # Number of entries
    output.append(struct.pack("I", 7 * 4))      # Offset of key table
    output.append(struct.pack("I", 7 * 4 + 8 * len(pairs)))  # Offset of value table
    output.append(struct.pack("I", 0))           # Hash table size
    output.append(struct.pack("I", 0))           # Hash table offset

    # Key table
    offset = keystart
    for k, v in pairs:
        output.append(struct.pack("I", len(k)))
        output.append(struct.pack("I", offset))
        offset += len(k) + 1

    # Value table
    offset = valuestart
    for k, v in pairs:
        output.append(struct.pack("I", len(v)))
        output.append(struct.pack("I", offset))
        offset += len(v) + 1

    # Keys
    for k, v in pairs:
        output.append(k)
        output.append(b'\0')

    # Values
    for k, v in pairs:
        output.append(v)
        output.append(b'\0')

    # Write .mo file
    with open(mo_file, 'wb') as f:
        for item in output:
            f.write(item)

def main():
    """Main function to compile all translations"""
    base_dir = "/home/bceverly/dev/sysmanage/backend/i18n/locales"
    languages = ['ar', 'de', 'es', 'fr', 'hi', 'it', 'ja', 'ko', 'nl', 'pt', 'ru', 'zh_CN', 'zh_TW']

    os.chdir(base_dir)

    for lang in languages:
        po_file = f"{lang}/LC_MESSAGES/messages.po"
        mo_file = f"{lang}/LC_MESSAGES/messages.mo"

        if os.path.exists(po_file):
            print(f"Compiling {lang}...")
            try:
                simple_po_to_mo(po_file, mo_file)
                print(f"  ✓ Successfully compiled {mo_file}")
            except Exception as e:
                print(f"  ✗ Error compiling {lang}: {e}")
        else:
            print(f"  ⚠ Warning: {po_file} not found")

if __name__ == "__main__":
    main()