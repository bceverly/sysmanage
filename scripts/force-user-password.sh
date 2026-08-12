#!/usr/bin/env bash
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# force-user-password.sh — Reset a sysmanage user's password directly in
# the database AND grant the user every security role, when email-based
# reset / UI-based role assignment isn't available (test VMs, lab
# instances, recovering an air-gapped install, etc.).
#
# Usage:
#   sudo scripts/force-user-password.sh <userid> <new-password>
#
# Reads the postgres connection from /etc/sysmanage.yaml.  Uses argon2
# (the same hasher backend/api/user.py uses) so the new hash is in the
# format the login path expects.  After the password reset, every row
# from ``security_roles`` is mapped to the user via
# ``user_security_roles``, replacing any prior role assignments — so
# this user becomes a full administrator with access to every UI page.

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <userid> <new-password>" >&2
  exit 2
fi

USERID="$1"
NEWPW="$2"

# Interpreter and config are DISCOVERED, not hardcoded.  This used to insist on
# /opt/sysmanage/.venv/bin/python and /etc/sysmanage.yaml -- one Linux packaging
# layout -- so it could not run at all on the BSD ports, Homebrew or Windows,
# and on a host that had both a packaged install and a leftover dev config at
# /etc it would edit the wrong database.  SYSMANAGE_CONFIG_PATH is the variable
# backend/config and the rc.d scripts already honour.
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in \
    /opt/sysmanage/.venv/bin/python \
    /usr/local/libexec/sysmanage/.venv/bin/python \
    "$(command -v python3 2>/dev/null)" \
    "$(command -v python3.12 2>/dev/null)" \
    "$(command -v python3.11 2>/dev/null)"
  do
    [ -n "$candidate" ] && [ -x "$candidate" ] && PYTHON_BIN="$candidate" && break
  done
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "error: no usable python found; set PYTHON_BIN=/path/to/python" >&2
  exit 1
fi

CONFIG="${SYSMANAGE_CONFIG_PATH:-}"
if [ -z "$CONFIG" ]; then
  for candidate in /etc/sysmanage.yaml /usr/local/etc/sysmanage.yaml; do
    [ -r "$candidate" ] && CONFIG="$candidate" && break
  done
fi
if [ -z "$CONFIG" ] || [ ! -r "$CONFIG" ]; then
  echo "error: cannot read a sysmanage.yaml (tried SYSMANAGE_CONFIG_PATH," >&2
  echo "/etc/sysmanage.yaml, /usr/local/etc/sysmanage.yaml).  Run with sudo," >&2
  echo "or set SYSMANAGE_CONFIG_PATH=/path/to/sysmanage.yaml" >&2
  exit 1
fi
echo "using python : $PYTHON_BIN"
echo "using config : $CONFIG"

export FORCE_USERID="$USERID"
export FORCE_NEWPW="$NEWPW"
export FORCE_CONFIG="$CONFIG"

"$PYTHON_BIN" <<'PY'
import os, sys, yaml, psycopg
from argon2 import PasswordHasher

with open(os.environ["FORCE_CONFIG"]) as f:
    cfg = yaml.safe_load(f)

# v3.0 renamed database: -> registry:; honour whichever is present.
db = cfg.get("database") or cfg["registry"]
dsn = (
    f"host={db['host']} port={db.get('port', 5432)} "
    f"dbname={db['name']} user={db['user']} password={db['password']}"
)

hashed = PasswordHasher().hash(os.environ["FORCE_NEWPW"])

with psycopg.connect(dsn) as conn:
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
            'WHERE userid = %s '
            'RETURNING id',
            (hashed, os.environ["FORCE_USERID"]),
        )
        row = cur.fetchone()
        if row is None:
            print(f"no user found with userid={os.environ['FORCE_USERID']!r}", file=sys.stderr)
            sys.exit(3)
        user_id = row[0]
        print(f"reset password for {os.environ['FORCE_USERID']} (id={user_id})")

        # Grant every security role to the user.  Replaces any prior
        # role assignment so re-running yields an idempotent state of
        # "this user has every permission".  Mirrors what an
        # administrator would do via the Security Roles UI once their
        # account is wired up, but works without UI access.
        cur.execute(
            'DELETE FROM user_security_roles WHERE user_id = %s',
            (user_id,),
        )
        cur.execute(
            'INSERT INTO user_security_roles '
            '    (id, user_id, role_id, granted_at) '
            'SELECT gen_random_uuid(), %s, id, NOW() '
            '  FROM security_roles',
            (user_id,),
        )
        print(f"granted {cur.rowcount} security role(s)")
    conn.commit()
PY
