#!/usr/bin/env bash
# force-user-password.sh — Reset a sysmanage user's password directly in
# the database when email-based reset isn't available (test VMs, lab
# instances, etc.).
#
# Usage:
#   sudo scripts/force-user-password.sh <userid> <new-password>
#
# Reads the postgres connection from /etc/sysmanage.yaml.  Uses argon2
# (the same hasher backend/api/user.py uses) so the new hash is in the
# format the login path expects.

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <userid> <new-password>" >&2
  exit 2
fi

USERID="$1"
NEWPW="$2"

VENV_PY=/opt/sysmanage/.venv/bin/python
CONFIG=/etc/sysmanage.yaml

if [ ! -x "$VENV_PY" ]; then
  echo "error: $VENV_PY not found.  Is sysmanage installed?" >&2
  exit 1
fi
if [ ! -r "$CONFIG" ]; then
  echo "error: cannot read $CONFIG (run with sudo?)" >&2
  exit 1
fi

export FORCE_USERID="$USERID"
export FORCE_NEWPW="$NEWPW"
export FORCE_CONFIG="$CONFIG"

"$VENV_PY" <<'PY'
import os, sys, yaml, psycopg2
from argon2 import PasswordHasher

with open(os.environ["FORCE_CONFIG"]) as f:
    cfg = yaml.safe_load(f)

db = cfg["database"]
dsn = (
    f"host={db['host']} port={db.get('port', 5432)} "
    f"dbname={db['name']} user={db['user']} password={db['password']}"
)

hashed = PasswordHasher().hash(os.environ["FORCE_NEWPW"])

with psycopg2.connect(dsn) as conn:
    with conn.cursor() as cur:
        # Columns per backend/persistence/models/core.py:277 (User model):
        #   hashed_password, failed_login_attempts, is_locked, locked_at,
        #   active.  Table is "user" (singular) — quoted because it's a
        #   postgres reserved word.
        cur.execute(
            'UPDATE "user" '
            'SET hashed_password = %s, '
            '    failed_login_attempts = 0, '
            '    is_locked = FALSE, '
            '    locked_at = NULL, '
            '    active = TRUE '
            'WHERE userid = %s',
            (hashed, os.environ["FORCE_USERID"]),
        )
        if cur.rowcount == 0:
            print(f"no user found with userid={os.environ['FORCE_USERID']!r}", file=sys.stderr)
            sys.exit(3)
        print(f"reset password for {os.environ['FORCE_USERID']} ({cur.rowcount} row updated)")
    conn.commit()
PY
