# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Agent impersonation check: does the server trust a hostname, or a secret?

An agent's real credential is its host_token (issued at registration, kept by
the agent).  A hostname is public -- it is in DNS, certificates, inventories.
This scenario runs one legitimate VICTIM agent and one ATTACKER that knows only
the victim's hostname, against the disposable server from stack.py, and checks
every way the attacker could act as the victim:

  E  re-register the victim's hostname over HTTP  -> is host_token returned?
  A  ask /api/agent/auth for a connection token    -> informational
  B  WebSocket SYSTEM_INFO naming the victim       -> is host_token returned?
                                                      is the session accepted?
  C1 send data with no credential                  -> does it land on the victim?
  C2 send data with the victim's host_id and a
     WRONG host_token                              -> does it land on the victim?
  D  an admin asks the victim for fresh data       -> does the command reach
                                                      the attacker instead?

A positive CONTROL runs first: the victim's own update, with its real token,
must reach the database -- otherwise "nothing was injected" could just mean
nothing was processed, and the run is inconclusive (exit 1).

Run only against the harness's own server.  It writes to that database (the
victim's approval) and nowhere else.
"""

import asyncio
import json
import time
import uuid

import aiohttp
import websockets
import yaml
from sqlalchemy import create_engine, text

from tests.load import payloads, stack

VICTIM = "victim.sim.test"
VICTIM_IP = "127.31.0.1"
ATTACKER_IP = "127.32.0.1"
PROCESS_WAIT_S = 120


class Probe:
    """A minimal agent identity for payloads.envelope()/identify()."""

    def __init__(self, hostname, ip, host_id=None, host_token=None):
        self.hostname, self.ipv4 = hostname, ip
        self.host_id, self.host_token = host_id, host_token

    def identify(self, data):
        if self.host_id and "host_id" not in data:
            data["host_id"] = self.host_id
            if self.host_token:
                data["host_token"] = self.host_token
        return data


def _db(db_url):
    return create_engine(db_url.replace("postgresql://", "postgresql+psycopg://", 1))


def _db_one(engine, sql, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params).first()


def _session(ip):
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(local_addr=(ip, 0)))


async def _connect(base, ws_base, ip, hostname, outcome):
    """auth + WebSocket; returns (ws, inbox list, reader task)."""
    async with _session(ip) as http:
        async with http.post(
            f"{base}/api/agent/auth", headers={"x-agent-hostname": hostname}
        ) as r:
            outcome["auth_status"] = r.status
            token = (
                (await r.json()).get("connection_token") if r.status == 200 else None
            )
    if not token:
        return None, [], None
    ws = await websockets.connect(f"{ws_base}/api/agent/connect?token={token}",
                                  local_addr=(ip, 0), open_timeout=15, max_size=2**24)  # fmt: skip
    inbox = []

    async def reader():
        try:
            async for raw in ws:
                inbox.append(json.loads(raw))
        except websockets.ConnectionClosed:
            pass

    return ws, inbox, asyncio.create_task(reader())


async def _await_message(inbox, kinds, timeout=15.0, start=0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for message in inbox[start:]:
            if message.get("message_type") in kinds:
                return message
        await asyncio.sleep(0.2)
    return None


async def _wait_for_release(engine, host_id, marker, timeout=PROCESS_WAIT_S):
    """True once the victim's platform_release equals ``marker``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = await asyncio.to_thread(
            _db_one,
            engine,
            "SELECT platform_release FROM host WHERE id = :id",
            id=host_id,
        )
        if row and row[0] == marker:
            return True
        await asyncio.sleep(2)
    return False


async def _queue_settled(engine, timeout=PROCESS_WAIT_S):
    """Wait until no inbound message is pending (so a 'no change' is final)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = await asyncio.to_thread(
            _db_one, engine,
            "SELECT count(*) FROM message_queue WHERE direction = 'inbound' "
            "AND status IN ('pending', 'processing')",
        )  # fmt: skip
        if row and row[0] == 0:
            return True
        await asyncio.sleep(2)
    return False


def _os_update(probe, marker):
    data = dict(payloads.PLATFORM, platform_release=marker, hostname=probe.hostname)
    return payloads.envelope("os_version_update", probe.identify(data))


async def _admin_token(base, config_path):
    with open(config_path, encoding="utf-8") as fh:
        security = yaml.safe_load(fh)["security"]
    async with aiohttp.ClientSession() as http:
        async with http.post(f"{base}/api/v1/login", json={
                "userid": security["admin_userid"], "password": security["admin_password"]}) as r:  # fmt: skip
            if r.status != 200:
                return None, f"HTTP {r.status}: {(await r.text())[:200]}"
            return (await r.json()).get("Authorization"), None


async def _current_token(engine, fqdn):
    row = await asyncio.to_thread(
        _db_one, engine, "SELECT host_token FROM host WHERE fqdn = :f", f=fqdn
    )
    return row[0] if row else None


async def _inject(engine, ws, probe, marker, host_id):
    """Send one os_version_update and report whether it reached the host."""
    await ws.send(_os_update(probe, marker))
    await _queue_settled(engine)
    await asyncio.sleep(3)
    row = await asyncio.to_thread(_db_one, engine,
                                  "SELECT platform_release FROM host WHERE id = :id", id=host_id)  # fmt: skip
    return row[0] == marker, row[0]


def _finding(results, check, failed, detail):
    results.append(
        {"check": check, "result": "FAIL" if failed else "pass", "detail": detail}
    )


async def run_impersonation(
    args,
) -> dict:  # pylint: disable=too-many-locals,too-many-statements
    if not args.reuse_stack:
        await asyncio.to_thread(stack.reset)
    state = stack.load_state()
    base = f"http://127.0.0.1:{state['port']}"
    ws_base = base.replace("http" + "://", "ws" + "://", 1)
    engine = _db(state["db_url"])
    results, info = [], {}

    # --- the victim: registers, is approved, connects with its token -------
    victim = Probe(VICTIM, VICTIM_IP)
    async with _session(VICTIM_IP) as http:
        async with http.post(
            f"{base}/api/host/register", json=payloads.registration_body(victim)
        ) as r:
            info["victim_register_status"] = r.status
            first = await r.json()
    await asyncio.to_thread(
        _db_one, engine,
        "UPDATE host SET approval_status = 'approved' WHERE fqdn = :f RETURNING id", f=VICTIM,
    )  # fmt: skip
    # Like the real agent: the credential comes from the registration that
    # created the host (Phase 22.0).  A pre-22.0 server minted it on the first
    # SYSTEM_INFO instead -- then it arrives in registration_success.
    victim.host_id, victim.host_token = first.get("id"), first.get("host_token")
    info["victim_token_from_registration"] = bool(victim.host_token)
    if not victim.host_id:
        row = await asyncio.to_thread(_db_one, engine,
                                      "SELECT id FROM host WHERE fqdn = :f", f=VICTIM)  # fmt: skip
        victim.host_id = str(row[0])
    v_out = {}
    v_ws, v_inbox, v_reader = await _connect(base, ws_base, VICTIM_IP, VICTIM, v_out)
    await v_ws.send(payloads.system_info(victim))
    welcome = await _await_message(v_inbox, {"registration_success"})
    victim.host_token = victim.host_token or (welcome or {}).get("host_token")

    # --- CONTROL: the victim's own update must land ------------------------
    control = f"CONTROL-{uuid.uuid4().hex[:8]}"
    await v_ws.send(_os_update(victim, control))
    if not await _wait_for_release(engine, victim.host_id, control):
        return {"scenario": "agent-impersonation", "inconclusive":
                "the victim's own os_version_update never reached the database",
                "results": results, "info": info}  # fmt: skip
    _finding(results, "control", False, "the victim's own update reached the database")

    # --- E: HTTP re-registration of the victim's hostname ------------------
    attacker = Probe(VICTIM, ATTACKER_IP)
    async with _session(ATTACKER_IP) as http:
        async with http.post(
            f"{base}/api/host/register", json=payloads.registration_body(attacker)
        ) as r:
            body = await r.json()
            info["reregister_status"] = r.status
            info["reregister_fields"] = sorted(body) if isinstance(body, dict) else None
    # Compare with the token the database holds NOW: if re-registering
    # rotated it, the attacker holds the only valid token.
    current = await _current_token(engine, VICTIM)
    info["token_rotated_by_reregister"] = current != victim.host_token
    leaked = (
        isinstance(body, dict)
        and bool(body.get("host_token"))
        and body.get("host_token") == current
    )
    _finding(results, "E: HTTP re-register returns a valid token for the host", leaked,
             f"HTTP {info['reregister_status']}; token in response: "
             f"{isinstance(body, dict) and 'host_token' in body}; rotated: {current != victim.host_token}")  # fmt: skip
    _finding(results, "E2: HTTP re-register by hostname changes the host's token",
             current != victim.host_token, "the real agent's token no longer works" if current != victim.host_token
             else "token unchanged")  # fmt: skip

    # --- A + B: connection token and the SYSTEM_INFO handshake --------------
    a_out = {}
    a_ws, a_inbox, a_reader = await _connect(base, ws_base, ATTACKER_IP, VICTIM, a_out)
    info["attacker_auth_status"] = a_out.get("auth_status")
    _finding(results, "A: connection token issued for another host's name (informational)",
             False, f"HTTP {a_out.get('auth_status')}")  # fmt: skip
    if a_ws is None:
        _finding(
            results,
            "B: SYSTEM_INFO handshake",
            False,
            "no connection: nothing further possible",
        )
    else:
        await a_ws.send(payloads.system_info(attacker))  # hostname only, no credential
        reply = await _await_message(
            a_inbox, {"registration_success", "registration_pending", "error"}
        )
        info["attacker_system_info_reply"] = {
            k: v for k, v in (reply or {}).items() if k != "host_token"
        }
        current = await _current_token(engine, VICTIM)
        disclosed = (
            bool(reply)
            and bool(reply.get("host_token"))
            and reply.get("host_token") == current
        )
        _finding(results, "B1: SYSTEM_INFO by hostname returns the host's token", disclosed,
                 f"reply type {reply and reply.get('message_type')}")  # fmt: skip
        accepted = bool(reply) and reply.get("message_type") == "registration_success"
        _finding(results, "B2: session accepted as the approved host without a credential",
                 accepted, f"reply type {reply and reply.get('message_type')}")  # fmt: skip

        # --- C1/C2: data injection ------------------------------------------
        # One at a time, so a later write cannot hide an earlier one.
        landed, now = await _inject(engine, a_ws, Probe(VICTIM, ATTACKER_IP),
                                    f"ATTACK-NOCRED-{uuid.uuid4().hex[:6]}", victim.host_id)  # fmt: skip
        _finding(results, "C1: data with NO credential written to the host", landed,
                 f"host's platform_release is {now!r}")  # fmt: skip
        landed, now = await _inject(engine, a_ws,
                                    Probe(VICTIM, ATTACKER_IP, victim.host_id, "not-the-token"),
                                    f"ATTACK-WRONGTOKEN-{uuid.uuid4().hex[:6]}", victim.host_id)  # fmt: skip
        _finding(results, "C2: data with a WRONG host_token written to the host", landed,
                 f"host's platform_release is {now!r}")  # fmt: skip

        # --- D: whose connection gets the host's commands? -------------------
        jwt, login_error = await _admin_token(base, state["config"])
        if login_error:
            info["admin_login_error"] = login_error
        start_a, start_v = len(a_inbox), len(v_inbox)
        if jwt:
            async with aiohttp.ClientSession() as http:
                async with http.post(f"{base}/api/v1/host/{victim.host_id}/request-system-info",
                                     headers={"Authorization": f"Bearer {jwt}"}) as r:  # fmt: skip
                    info["request_system_info_status"] = r.status
            got_a = await _await_message(
                a_inbox, {"command"}, timeout=30, start=start_a
            )
            got_v = await _await_message(v_inbox, {"command"}, timeout=5, start=start_v)
            _finding(results, "D: the host's commands delivered to the impersonator", bool(got_a),
                     f"attacker got {got_a and got_a.get('data', {}).get('command_type')}; "
                     f"victim got {got_v and got_v.get('data', {}).get('command_type')}")  # fmt: skip
        else:
            info["admin_login"] = "failed -- check D skipped"
        await a_ws.close()
        a_reader.cancel()

    # --- L: a pre-22.0 agent (host id, no token) must still connect ----------
    # A control in the other direction: hardening that locked out the agents
    # already deployed would be an outage of its own.
    l_ws, l_inbox, l_reader = await _connect(base, ws_base, VICTIM_IP, VICTIM, {})
    if l_ws is not None:
        await l_ws.send(payloads.system_info(Probe(VICTIM, VICTIM_IP, victim.host_id)))
        reply = await _await_message(l_inbox, {"registration_success", "error"})
        refused = not reply or reply.get("message_type") != "registration_success"
        _finding(results, "L (control): a pre-22.0 agent with its host id still connects",
                 refused, f"reply type {reply and reply.get('message_type')}")  # fmt: skip
        await l_ws.close()
        l_reader.cancel()

    # --- R: the ratchet -- once an updated agent proves its token, the
    # id-only identity is refused for that host from then on ---------------
    r_ws, r_inbox, r_reader = await _connect(base, ws_base, VICTIM_IP, VICTIM, {})
    if r_ws is not None:
        updated = payloads.system_info(victim)
        envelope = json.loads(updated)
        envelope["data"]["agent_capabilities"] = {
            "schema_version": 1, "capabilities": ["persistent_host_token"],
            "commands": ["get_system_info"],
        }  # fmt: skip
        await r_ws.send(json.dumps(envelope))
        await _await_message(r_inbox, {"registration_success", "error"})
        await r_ws.close()
        r_reader.cancel()
        r_ws, r_inbox, r_reader = await _connect(base, ws_base, VICTIM_IP, VICTIM, {})
        await r_ws.send(payloads.system_info(Probe(VICTIM, VICTIM_IP, victim.host_id)))
        reply = await _await_message(r_inbox, {"registration_success", "error"})
        _finding(results, "R: id-only identity still accepted after the agent proved its token",
                 bool(reply) and reply.get("message_type") == "registration_success",
                 f"reply type {reply and reply.get('message_type')}")  # fmt: skip
        await r_ws.close()
        r_reader.cancel()

    await v_ws.close()
    v_reader.cancel()
    engine.dispose()
    return {"scenario": "agent-impersonation", "results": results, "info": info}


def main_security(args) -> int:
    report = asyncio.run(run_impersonation(args))
    with open(args.output_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    if report.get("inconclusive"):
        print(f"INCONCLUSIVE: {report['inconclusive']}")
        return 1
    for row in report["results"]:
        print(f"  [{row['result']:>4}] {row['check']} -- {row['detail']}")
    print(json.dumps(report["info"], indent=2, default=str))
    failed = [r for r in report["results"] if r["result"] == "FAIL"]
    if failed:
        print(
            f"\n{len(failed)} impersonation check(s) FAILED: the server trusts a hostname."
        )
        return 0 if args.report_only else 2
    print("\nNo impersonation path found.")
    return 0
