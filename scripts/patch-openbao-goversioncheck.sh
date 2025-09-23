#!/bin/sh
#
# Patch OpenBAO goversioncheck.sh for OpenBSD compatibility
# Fixes regex pattern that doesn't work with OpenBSD's basic grep
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OPENBAO_DIR="$PROJECT_DIR/.build/openbao"
GOVERSIONCHECK_FILE="$OPENBAO_DIR/scripts/goversioncheck.sh"

echo "Patching OpenBAO goversioncheck.sh for OpenBSD compatibility..."

# Check if the file exists
if [ ! -f "$GOVERSIONCHECK_FILE" ]; then
    echo "Warning: goversioncheck.sh not found at $GOVERSIONCHECK_FILE"
    echo "Skipping patch (OpenBAO source may not be downloaded yet)"
    exit 0
fi

# Check if already patched (look for escaped dots)
if grep -q 'go\[0-9\]\*\\' "$GOVERSIONCHECK_FILE"; then
    echo "goversioncheck.sh already patched for OpenBSD"
    exit 0
fi

echo "Applying OpenBSD grep compatibility patch..."

# Create backup
cp "$GOVERSIONCHECK_FILE" "$GOVERSIONCHECK_FILE.backup"

# Apply the patch - fix the regex pattern for OpenBSD grep
# Replace: go[0-9]*.[0-9]*.[0-9]*
# With:    go[0-9]*\.[0-9]*\.[0-9]*
sed -i.tmp \
    "s/go\[0-9\]\*\.\[0-9\]\*\.\[0-9\]\*/go[0-9]*\\\\.[0-9]*\\\\.[0-9]*/g" \
    "$GOVERSIONCHECK_FILE"

# Also handle the extended regex version if present
sed -i.tmp \
    "s/go\[0-9\]\\\\+\\\\.\[0-9\]\\\\+\\\\(\\\\\.\[0-9\]\\\\+\\\\)\\\\?/go[0-9]*\\\\.[0-9]*\\\\.[0-9]*/g" \
    "$GOVERSIONCHECK_FILE"

# Remove sed backup file
rm -f "$GOVERSIONCHECK_FILE.tmp"

echo "✅ OpenBAO goversioncheck.sh patched successfully"
echo "Original file backed up as: $GOVERSIONCHECK_FILE.backup"

# Verify the change (look for escaped dots)
echo "Verifying patch..."
if grep -q 'go\[0-9\]\*\\' "$GOVERSIONCHECK_FILE"; then
    echo "✅ Patch verification successful"
else
    echo "❌ Patch verification failed - restoring backup"
    mv "$GOVERSIONCHECK_FILE.backup" "$GOVERSIONCHECK_FILE"
    exit 1
fi