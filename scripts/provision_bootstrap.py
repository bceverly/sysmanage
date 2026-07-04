#!/usr/bin/env python3
"""
One-time provisioning bootstrap for SysManage multi-tenancy (Phase 13.1).

Run ONCE by an operator who legitimately holds Postgres-superuser and
OpenBAO-admin credentials.  It mints the *least-privilege* identity the running
server then uses for self-service tenant provisioning, so the long-running web
process never holds superuser/root:

  1. Enables OpenBAO's ``database`` secrets engine (idempotent).
  2. Creates a Postgres ``provisioner`` role with ONLY ``CREATEDB`` +
     ``CREATEROLE`` (not superuser, not the app's data-runtime user).
  3. Stores the provisioner credential in OpenBAO at
     ``<mount>/data/sysmanage/provisioner`` so the server can read it
     just-in-time.
  4. Writes a scoped OpenBAO policy (``sysmanage-provisioner``) limited to the
     paths self-service provisioning needs — attach it to the server's token /
     AppRole rather than handing the server a root token.

Idempotent: safe to re-run.  Secrets are never printed.

Example:
    python scripts/provision_bootstrap.py \\
        --bao-addr http://127.0.0.1:8200 --bao-token "$ROOT_TOKEN" \\
        --pg-host localhost --pg-port 5432 \\
        --pg-superuser postgres --pg-superuser-password secret
"""

import argparse
import json
import os
import re
import secrets
import sys
import tempfile
import urllib.error
import urllib.request


def _bao(addr, token, method, path, payload=None):
    """Minimal OpenBAO API call; returns (status, parsed_json|None)."""
    url = f"{addr.rstrip('/')}/v1/{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Vault-Token", token)
    req.add_header("Content-Type", "application/json")
    try:
        # URL is the operator-configured OpenBAO address (trusted config, not
        # user input) — no SSRF surface; this is an operator-run bootstrap CLI.
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
            body = resp.read().decode() or "{}"
            return resp.status, json.loads(body) if body.strip() else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body) if body.strip() else None
        except json.JSONDecodeError:
            return exc.code, None


def _enable_database_engine(addr, token, db_mount):
    """Enable the database secrets engine at db_mount if not already mounted."""
    status, mounts = _bao(addr, token, "GET", "sys/mounts")
    if status == 200 and isinstance(mounts, dict):
        # KV-style response: the mount appears as "<db_mount>/".
        data = mounts.get("data", mounts)
        if f"{db_mount}/" in data:
            print(f"[ok] database secrets engine already enabled at '{db_mount}'")
            return
    status, _ = _bao(
        addr, token, "POST", f"sys/mounts/{db_mount}", {"type": "database"}
    )
    if status in (200, 204):
        print(f"[ok] enabled database secrets engine at '{db_mount}'")
    else:
        raise SystemExit(f"[fail] could not enable database engine (HTTP {status})")


def _create_pg_provisioner_direct(args, provisioner_password):
    """Create/ensure the provisioner role by connecting as a superuser (password auth)."""
    import psycopg  # noqa: PLC0415
    from psycopg import sql  # noqa: PLC0415

    conn = psycopg.connect(
        host=args.pg_host,
        port=args.pg_port,
        user=args.pg_superuser,
        password=args.pg_superuser_password,
        dbname=args.pg_db,
        connect_timeout=10,
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (args.provisioner_user,)
            )
            exists = cur.fetchone() is not None
            role = sql.Identifier(args.provisioner_user)
            verb = "ALTER" if exists else "CREATE"
            # psycopg: ``verb`` is a fixed literal, the role name goes through
            # sql.Identifier (safe quoting), and the password is a %s bind param.
            cur.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                sql.SQL(
                    verb + " ROLE {} WITH LOGIN CREATEDB CREATEROLE PASSWORD %s"
                ).format(role),
                (provisioner_password,),
            )
            print(
                f"[ok] {'updated' if exists else 'created'} provisioner role "
                f"'{args.provisioner_user}'"
            )
    finally:
        conn.close()


def _emit_pg_provisioner_sql(args, provisioner_password):
    """Write idempotent role-creation SQL to a 0600 file for peer-auth setups.

    Returns the file path.  The password is URL-safe (no quotes), so embedding
    it in a single-quoted SQL literal is safe.  The file is mode 0600 so the
    generated provisioner password isn't world-readable.
    """
    role = args.provisioner_user
    # Validate the identifier so it can't break out of the SQL — this file is
    # applied by a superuser, so we never want surprises in it.
    if not re.match(r"^[a-z_][a-z0-9_]*$", role):
        raise SystemExit(f"[fail] invalid --provisioner-user identifier: {role!r}")
    # role is identifier-validated above; password is URL-safe (no quotes);
    # file is 0600 and applied by the operator themselves — not a runtime query.
    sql_text = (  # nosec B608
        "DO $$\nBEGIN\n"
        f"  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN\n"
        f'    ALTER ROLE "{role}" WITH LOGIN CREATEDB CREATEROLE '
        f"PASSWORD '{provisioner_password}';\n"
        "  ELSE\n"
        f'    CREATE ROLE "{role}" WITH LOGIN CREATEDB CREATEROLE '
        f"PASSWORD '{provisioner_password}';\n"
        "  END IF;\nEND\n$$;\n"
    )
    fd, path = tempfile.mkstemp(prefix="sysmanage_provisioner_", suffix=".sql")
    with os.fdopen(fd, "w") as handle:
        handle.write(sql_text)
    os.chmod(path, 0o600)
    return path


def _store_provisioner_secret(addr, token, vault_mount, args, provisioner_password):
    """Store the provisioner credential in OpenBAO (KV v2)."""
    path = f"{vault_mount}/data/sysmanage/provisioner"
    payload = {
        "data": {
            "host": args.pg_host,
            "port": str(args.pg_port),
            "user": args.provisioner_user,
            "password": provisioner_password,
            "sslmode": args.pg_sslmode,
        }
    }
    status, _ = _bao(addr, token, "POST", path, payload)
    if status in (200, 204):
        print("[ok] stored provisioner credential in OpenBAO (sysmanage/provisioner)")
    else:
        raise SystemExit(f"[fail] could not store provisioner secret (HTTP {status})")


def _write_scoped_policy(addr, token, vault_mount, db_mount):
    """Write the least-privilege policy for the server's provisioning identity."""
    policy = f"""
# SysManage self-service provisioning — least privilege.
path "sys/mounts/{db_mount}" {{ capabilities = ["create", "update", "read"] }}
path "{db_mount}/config/*"   {{ capabilities = ["create", "update", "read"] }}
path "{db_mount}/roles/*"    {{ capabilities = ["create", "update", "read"] }}
path "{db_mount}/creds/*"    {{ capabilities = ["read"] }}
path "{vault_mount}/data/sysmanage/provisioner" {{ capabilities = ["read"] }}
""".strip()
    status, _ = _bao(
        addr,
        token,
        "PUT",
        "sys/policies/acl/sysmanage-provisioner",
        {"policy": policy},
    )
    if status in (200, 204):
        print("[ok] wrote OpenBAO policy 'sysmanage-provisioner'")
        print(
            "     attach it to the server's token/AppRole — do NOT give the "
            "server a root token."
        )
    else:
        raise SystemExit(f"[fail] could not write policy (HTTP {status})")


def _write_server_policy(addr, token, vault_mount, db_mount):
    """Write the base policy for the server's *runtime* identity.

    Covers exactly what the data plane needs: KV read/write on its own mount,
    dynamic DB credential leasing, and the lease lifecycle.  Combined with
    ``sysmanage-provisioner``, this lets the server run on a least-privilege
    token instead of a root token.
    """
    policy = f"""
# SysManage server runtime — least privilege.
# KV v2 secrets the app stores/reads (config bag, per-tenant secrets, secrets engine).
path "{vault_mount}/data/*"     {{ capabilities = ["create", "read", "update", "delete", "list"] }}
path "{vault_mount}/metadata/*" {{ capabilities = ["read", "list", "delete"] }}
# Dynamic per-tenant database credentials + their lease lifecycle.
path "{db_mount}/creds/*"           {{ capabilities = ["read"] }}
path "sys/leases/renew"             {{ capabilities = ["update"] }}
path "sys/leases/revoke"            {{ capabilities = ["update"] }}
path "sys/leases/revoke-prefix/*"   {{ capabilities = ["update"] }}
""".strip()
    status, _ = _bao(
        addr, token, "PUT", "sys/policies/acl/sysmanage-server", {"policy": policy}
    )
    if status in (200, 204):
        print("[ok] wrote OpenBAO policy 'sysmanage-server'")
    else:
        raise SystemExit(f"[fail] could not write server policy (HTTP {status})")


def _issue_server_token(addr, token):
    """Create a renewable, periodic, least-privilege token for the server.

    Carries ``sysmanage-server`` + ``sysmanage-provisioner`` — everything the
    runtime + self-service provisioning need, and nothing else.  Printed (not
    auto-installed) so the operator adopts it deliberately and can verify
    before pointing the server at it.
    """
    status, body = _bao(
        addr,
        token,
        "POST",
        "auth/token/create",
        {
            "policies": ["sysmanage-server", "sysmanage-provisioner"],
            "period": "768h",  # periodic → renewable indefinitely by the server
            "renewable": True,
            "display_name": "sysmanage-server",
            "no_parent": True,
        },
    )
    if status not in (200, 204) or not isinstance(body, dict):
        raise SystemExit(f"[fail] could not issue server token (HTTP {status})")
    client_token = (body.get("auth") or {}).get("client_token")
    if not client_token:
        raise SystemExit("[fail] token create returned no client_token")
    print("[ok] issued least-privilege server token (sysmanage-server + provisioner)")
    print(
        "     Install it where the server reads its token, then restart:\n"
        "       sudo install -m 0640 -o sysmanage /dev/stdin "
        "/etc/sysmanage/openbao-token <<'EOF'\n"
        f"       {client_token}\n"
        "       EOF\n"
        "     Verify the server can still read/write its secrets before retiring "
        "the root token."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bao-addr", default="http://127.0.0.1:8200")
    parser.add_argument("--bao-token", required=True, help="OpenBAO admin/root token")
    parser.add_argument("--vault-mount", default="secret", help="KV v2 mount path")
    parser.add_argument("--db-mount", default="database", help="DB secrets mount path")
    parser.add_argument("--pg-host", default="localhost")
    parser.add_argument("--pg-port", type=int, default=5432)
    parser.add_argument("--pg-db", default="postgres")
    parser.add_argument("--pg-superuser", default="postgres")
    parser.add_argument("--pg-superuser-password", default="")
    parser.add_argument("--pg-sslmode", default="prefer")
    parser.add_argument("--provisioner-user", default="sysmanage_provisioner")
    parser.add_argument(
        "--provisioner-password",
        default="",
        help="Provisioner role password; a strong one is generated if omitted.",
    )
    parser.add_argument(
        "--issue-server-token",
        action="store_true",
        help="Also issue a least-privilege, renewable server token (printed, "
        "not installed) so the server can stop using a root token.",
    )
    args = parser.parse_args(argv)

    provisioner_password = args.provisioner_password or secrets.token_urlsafe(32)

    print("=== SysManage provisioning bootstrap ===")
    # OpenBAO setup + store the provisioner credential (same password the PG
    # role gets) so the server can read it.  Done first so it's consistent
    # whether PG is created directly or via the emitted SQL.
    _enable_database_engine(args.bao_addr, args.bao_token, args.db_mount)
    _store_provisioner_secret(
        args.bao_addr, args.bao_token, args.vault_mount, args, provisioner_password
    )
    _write_scoped_policy(args.bao_addr, args.bao_token, args.vault_mount, args.db_mount)
    _write_server_policy(args.bao_addr, args.bao_token, args.vault_mount, args.db_mount)
    if args.issue_server_token:
        _issue_server_token(args.bao_addr, args.bao_token)

    # Postgres provisioner role.  If a superuser password is supplied, do it
    # directly; otherwise (peer auth, the Ubuntu default) emit a 0600 SQL file
    # for the operator to apply via `sudo -u postgres psql`.
    pending_sql = None
    if args.pg_superuser_password:
        _create_pg_provisioner_direct(args, provisioner_password)
    else:
        pending_sql = _emit_pg_provisioner_sql(args, provisioner_password)

    print("=== bootstrap complete ===")
    if pending_sql:
        print(
            "[action required] No Postgres superuser password given (peer auth).\n"
            "Apply the provisioner role with your superuser.  Use a stdin "
            "redirect (NOT -f) so your shell reads the 0600 file — the postgres "
            "user can't open it directly:\n"
            f"  sudo -u postgres psql -d postgres < {pending_sql}\n"
            f"then delete it:  rm {pending_sql}\n"
        )
    print(
        "Then enable self-service in sysmanage.yaml:\n"
        "  multitenancy:\n    enabled: true\n    self_service_provisioning: true\n"
        "and restart the server."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
