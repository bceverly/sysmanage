# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Simulated agent fleet (Phase 22).

Each SimAgent behaves like the REAL agent today -- including the behavior
Phase 22 sets out to change -- so a baseline run shows the server what a
real fleet does to it.  Sources (sysmanage-agent): main.py run() /
_connection_loop, registration/client_registration.py, core/auth_helper.py,
communication/message_handler*.py, data_collector.py, transport_fallback.py,
http_polling.py.

  * registers over HTTP on every start (no backoff: fixed 30 s retries);
  * every connection: GET / health check, POST /api/agent/auth, WebSocket;
  * on connect: system_info, then the 14-step collection IMMEDIATELY;
  * registration_success(approved) triggers the initial burst again;
  * heartbeat every 30 s, collection every 300 s, child hosts every 60 s,
    update check every 3600 s -- all anchored to the connect, no jitter;
  * outbound pacing: 10 messages a pass, then a 1 s sleep;
  * reconnect backoff min(5 * 2^min(f, 6), 300) * U(0.5, 1.5);
  * two "structural" WebSocket failures (an HTTP status on the upgrade)
    demote the agent to HTTP polling for 900 s.

``time_scale`` divides the agent's timers (not its backoff) so a short run
covers many collection cycles.  Each agent can come from its own loopback
address (127.20.x.y) or all from one -- the NAT case.
"""

import asyncio
import json
import random
import time
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import aiohttp
import websockets

from tests.load import payloads

HEARTBEAT_S = 30
COLLECTION_S = 300
CHILD_HOSTS_S = 60
UPDATE_CHECK_S = 3600
FALLBACK_S = 900
POLL_S = 5
REGISTRATION_RETRY_S = 30
REGISTRATION_TRIES = 10
SEND_BATCH = 10
# Send-on-change (agent Phase 22.1): see SimAgent._wanted.
SAMPLE_S = 15 * 60
RESEND_S = 24 * 3600
CONNECT_SPLAY_S = 60
SNAPSHOT_TYPES = frozenset(
    {
        "software_inventory_update", "user_access_update", "hardware_update",
        "host_certificates_update", "role_data", "os_version_update",
        "reboot_status_update", "third_party_repository_update",
        "antivirus_status_update", "firewall_status_update", "graylog_status_update",
        "child_host_list_update", "fips_compliance_update", "package_updates_update",
        "process_status_update", "host_metrics",
    }
)  # fmt: skip

_STRUCTURAL = ("invalidstatus", "invalidupgrade", "invalidhandshake", "invalidmessage")


def source_ip(index: int) -> str:
    """The index-th loopback source address: 127.20.x.y (y never 0)."""
    return f"127.20.{index // 250}.{index % 250 + 1}"


@dataclass
class FleetStats:
    """Everything the agents saw, for the report.  Single-threaded asyncio,
    so plain counters are safe."""

    counts: Counter = field(default_factory=Counter)
    sent: Counter = field(default_factory=Counter)
    errors_received: Counter = field(default_factory=Counter)
    heartbeat_rtt_ms: List[float] = field(default_factory=list)
    # (monotonic time, command_type, agent index) of every command received:
    # the wave scenarios read the delivery rate from it.
    command_arrivals: List[tuple] = field(default_factory=list)
    # initial_report_window_seconds from each registration_success (22.2)
    report_windows: List[float] = field(default_factory=list)
    connected: int = 0
    connected_at_end: int = 0
    polling: int = 0
    bytes_sent: int = 0
    timeline: List[dict] = field(default_factory=list)
    _window_sent: int = 0

    def snapshot(self, t: float) -> dict:
        row = {"t": round(t, 1), "connected": self.connected, "polling": self.polling,
               "sent_since_last": self._window_sent,
               "auth_429_total": self.counts["auth_429"],
               "connect_ok_total": self.counts["connect_ok"]}  # fmt: skip
        self._window_sent = 0
        self.timeline.append(row)
        return row


class SimAgent:  # pylint: disable=too-many-instance-attributes
    """One simulated agent."""

    def __init__(self, fleet: "Fleet", index: int):
        self.fleet = fleet
        self.index = index
        self.hostname = f"load-{index:06d}.sim.test"
        ip_index = index % fleet.source_ips
        self.local_ip = source_ip(ip_index)
        self.ipv4 = self.local_ip
        self.host_id: Optional[str] = None
        self.host_token: Optional[str] = None
        # Like the agent (server Phase 22): one random value, sent with every
        # registration attempt, so a retry whose reply was lost gets the
        # credential back.
        self.registration_nonce = uuid.uuid4().hex + uuid.uuid4().hex
        self.not_before = 0.0  # a 429's Retry-After, with --identity-auth
        self.approved = False
        self.failures = 0
        self.structural = 0
        self.fallback_until = 0.0
        self.out: Dict[str, deque] = {
            "urgent": deque(),
            "high": deque(),
            "normal": deque(),
        }
        self.ws = None
        self.hb_sent_at: Optional[float] = None
        self.sent_at: Dict[str, float] = {}  # send-on-change memory, per report type
        self.reports_at = 0.0  # a busy server's held first-report moment (22.2)
        self._rng = random.Random(index)

    # -- identity -----------------------------------------------------------

    def identify(self, data: dict) -> dict:
        """Add host_id/host_token the way create_message does (only once
        approved, and host_token only when host_id was not already there)."""
        if self.approved and self.host_id and "host_id" not in data:
            data["host_id"] = self.host_id
            if self.host_token:
                data["host_token"] = self.host_token
        return data

    # -- HTTP ---------------------------------------------------------------

    def _http(self) -> aiohttp.ClientSession:
        return self.fleet.http_session(self.local_ip)

    async def register(self) -> bool:
        """POST /api/host/register, retried like the agent: fixed 30 s, 10 tries."""
        body = payloads.registration_body(self)
        body["registration_nonce"] = self.registration_nonce
        tokens = self.fleet.enrollment_tokens
        if tokens:  # multi-tenant stack: agents spread round-robin over tenants
            body["enrollment_token"] = tokens[self.index % len(tokens)]
        stats = self.fleet.stats
        for attempt in range(REGISTRATION_TRIES):
            if self.fleet.stopping:
                return False
            try:
                async with self._http().post(f"{self.fleet.base}/api/host/register", json=body,
                                             timeout=aiohttp.ClientTimeout(total=30)) as resp:  # fmt: skip
                    if resp.status in (200, 201):
                        reply = await resp.json()
                        self.host_id = reply.get("id") or self.host_id
                        self.host_token = reply.get("host_token") or self.host_token
                        # Like the agent's _store_auth_data: a stored identity
                        # counts as approved, so the FIRST system_info already
                        # carries host_id (+ token).  Waiting for
                        # registration_success made the simulator send a bare
                        # hostname, which a 22.0 server rightly refuses.
                        if self.host_id:
                            self.approved = True
                        stats.counts["register_ok"] += 1
                        return True
                    if resp.status == 409:
                        stats.counts["register_conflict"] += 1
                        return True
                    stats.counts[f"register_http_{resp.status}"] += 1
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                stats.counts["register_error"] += 1
            if attempt < REGISTRATION_TRIES - 1:
                await self.fleet.sleep(REGISTRATION_RETRY_S, scaled=False)
        stats.counts["register_gave_up"] += 1
        return False

    async def _health(self) -> bool:
        try:
            async with self._http().get(f"{self.fleet.base}/",
                                        timeout=aiohttp.ClientTimeout(total=5)) as resp:  # fmt: skip
                return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return False

    async def _auth(self) -> Optional[str]:
        stats = self.fleet.stats
        try:
            headers = {"x-agent-hostname": self.hostname}
            if self.fleet.identity_auth and self.host_id and self.host_token:
                # Agent 22.2: say who we are, so the limit is per host, not
                # per (NAT) address.
                headers.update(
                    {"x-host-id": self.host_id, "x-host-token": self.host_token}
                )
            async with self._http().post(f"{self.fleet.base}/api/agent/auth",
                                         headers=headers,
                                         timeout=aiohttp.ClientTimeout(total=30)) as resp:  # fmt: skip
                if resp.status == 429:
                    stats.counts["auth_429"] += 1
                    if self.fleet.identity_auth:  # agent 22.2 honors Retry-After
                        try:
                            wait = float(resp.headers.get("Retry-After", 60))
                        except ValueError:
                            wait = 60.0
                        self.not_before = time.monotonic() + wait * self._rng.uniform(
                            1.0, 1.2
                        )
                    return None
                if resp.status != 200:
                    stats.counts[f"auth_http_{resp.status}"] += 1
                    return None
                token = (await resp.json()).get("connection_token")
                if not token:
                    stats.counts["auth_no_token"] += 1
                return token
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            stats.counts["auth_error"] += 1
            return None

    # -- lifecycle ----------------------------------------------------------

    async def run(self, register: bool = True):
        """The agent's main loop, until the fleet stops.  A real agent
        registers on every start (main.py run()), so ``register`` is only
        False when the caller has just done it."""
        if register and not await self.register():
            return
        while not self.fleet.stopping:
            if time.monotonic() < self.fallback_until:
                await self._poll_once()
                continue
            connected = await self._connect_once()
            if connected:
                self.failures = 0
            else:
                self.failures += 1
            # Every pass -- a clean close too -- goes through the backoff.
            if self.fleet.jitter:
                # Agent 22.1 (core/backoff.py): full jitter in [1, min(300,
                # 5 x 2^n)]; after a clean close (the agent counts it as its
                # first failure) the first wait is up to 60 s.
                if connected:
                    delay = self._rng.uniform(1.0, 60.0)
                else:
                    top = min(300.0, 5.0 * 2 ** min(self.failures + 1, 16))
                    delay = self._rng.uniform(1.0, top)
            else:
                delay = min(5 * 2 ** min(self.failures, 6), 300) * self._rng.uniform(
                    0.5, 1.5
                )
            delay = max(delay, self.not_before - time.monotonic())
            await self.fleet.sleep(delay, scaled=False)

    async def _connect_once(self) -> bool:
        stats = self.fleet.stats
        if not await self._health():
            stats.counts["health_fail"] += 1
            return False
        token = await self._auth()
        if not token:
            return False
        stats.counts["connect_attempt"] += 1
        try:
            async with websockets.connect(
                f"{self.fleet.ws_base}/api/agent/connect?token={token}",
                local_addr=self.fleet.local_addr(self.local_ip), open_timeout=30, close_timeout=10,
                ping_interval=HEARTBEAT_S, ping_timeout=HEARTBEAT_S / 2, max_size=2**24,
            ) as ws:  # fmt: skip
                self.structural = 0
                stats.counts["connect_ok"] += 1
                stats.connected += 1
                try:
                    await self._session(ws)
                finally:
                    stats.connected -= 1
            stats.counts["closed_clean"] += 1
            return True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            name = f"{type(exc).__name__} {exc}".lower()
            stats.counts[f"ws_{type(exc).__name__}"] += 1
            # Agent 22.1: a 429 / 5xx on the upgrade is the server saying "not
            # now", never "this network blocks WebSockets".
            busy = self.fleet.jitter and any(f"http {c}" in name for c in
                                             ("429", "500", "502", "503", "504"))  # fmt: skip
            if any(p in name for p in _STRUCTURAL) and not busy:
                self.structural += 1
                if self.structural >= 2:
                    stats.counts["fallback_to_polling"] += 1
                    self.fallback_until = (
                        time.monotonic() + FALLBACK_S / self.fleet.time_scale
                    )
                    self.structural = 0
            return False

    async def _session(self, ws):
        self.ws = ws
        for queue in self.out.values():
            queue.clear()
        self.out["urgent"].append(payloads.system_info(self))
        tasks = [
            asyncio.create_task(self._first_collection()),
            asyncio.create_task(self._sender()),
            asyncio.create_task(self._every(HEARTBEAT_S, self._heartbeat, 0.1)),
            asyncio.create_task(self._every(COLLECTION_S, self._collection)),
            asyncio.create_task(self._every(CHILD_HOSTS_S, self._child_hosts)),
            asyncio.create_task(self._every(UPDATE_CHECK_S, self._update_check)),
        ]
        try:
            async for raw in ws:
                self._on_message(raw)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.ws = None

    async def _first_collection(self):
        """Today's agent collects the moment it connects; with ``--jitter``
        it waits up to a minute first (agent core/schedule_jitter.py)."""
        if self.fleet.jitter:
            await self.fleet.sleep(self._rng.uniform(0, CONNECT_SPLAY_S))
        held = self.reports_at - time.monotonic()
        if held > 0:  # the agent waits for the server's window here too
            await asyncio.sleep(held)
        self._queue_reports(payloads.periodic_set(self, self.fleet.payloads))

    async def _every(self, interval: float, action, spread: float = 0.2):
        """A periodic sender: first run one interval after connect, then every
        interval -- anchored to the connect and never varied (today's agent),
        or varied by +/-``spread`` each time (``--jitter``)."""
        while True:
            pause = interval
            if self.fleet.jitter:
                pause *= self._rng.uniform(1 - spread, 1 + spread)
            await self.fleet.sleep(pause)
            action()

    def _heartbeat(self):
        self.hb_sent_at = time.monotonic()
        self.out["high"].append(payloads.heartbeat(self))

    def _collection(self):
        self._queue_reports(payloads.periodic_set(self, self.fleet.payloads))

    def _child_hosts(self):
        self._queue_reports([payloads.child_hosts(self)])

    def _update_check(self):
        self._queue_reports([payloads.package_updates(self, self.fleet.payloads)])

    def _queue_reports(self, messages):
        """Queue snapshot reports -- all of them (today's agent), or only the
        ones a send-on-change agent would send (``--send-on-change``)."""
        for message in messages:
            if self._wanted(message):
                self.out["normal"].append(message)

    def _wanted(self, message) -> bool:
        """The agent's send-on-change rule (sysmanage-agent
        communication/send_on_change.py) for content that never changes, as
        here: each report once, processes and metrics every 15 minutes,
        everything again after 24 hours -- scaled with the run's timers."""
        if not self.fleet.send_on_change:
            return True
        kind = message[18 : message.index('"', 18)]
        if kind not in SNAPSHOT_TYPES:
            return True
        now = time.monotonic()
        every = (
            SAMPLE_S if kind in ("process_status_update", "host_metrics") else RESEND_S
        )
        last = self.sent_at.get(kind)
        if last is not None and now - last < every / self.fleet.time_scale:
            return False
        self.sent_at[kind] = now
        return True

    async def _sender(self):
        """Up to 10 messages a pass, urgent first, then 1 s (the agent's queue)."""
        stats = self.fleet.stats
        while True:
            batch = []
            for level in ("urgent", "high", "normal"):
                queue = self.out[level]
                while queue and len(batch) < SEND_BATCH:
                    batch.append(queue.popleft())
            for message in batch:
                await self.ws.send(message)
                stats.bytes_sent += len(message)
                stats._window_sent += 1  # pylint: disable=protected-access
                stats.sent[message[18 : message.index('"', 18)]] += 1
            await asyncio.sleep(1)

    async def _burst(self, window: float = 0.0):
        """The initial inventory after registration_success.  With
        ``--report-window`` it starts at a random moment in the server's
        ``initial_report_window_seconds`` (agent 22.2; real seconds), and the
        first post-connect collection waits for the same moment."""
        if self.fleet.report_window and window > 0:
            delay = self._rng.uniform(0, min(window, 3600.0))
            self.reports_at = time.monotonic() + delay
            await asyncio.sleep(delay)
        for message, pause in payloads.initial_burst(self, self.fleet.payloads):
            self._queue_reports([message])
            if pause:
                await asyncio.sleep(pause)

    def _on_message(self, raw):
        stats = self.fleet.stats
        try:
            message = json.loads(raw)
        except ValueError:
            stats.counts["recv_bad_json"] += 1
            return
        kind = message.get("message_type")
        stats.counts[f"recv_{kind}"] += 1
        if kind == "ack" and self.hb_sent_at is not None:
            stats.heartbeat_rtt_ms.append((time.monotonic() - self.hb_sent_at) * 1000)
            self.hb_sent_at = None
        elif kind == "registration_success":
            self.approved = bool(message.get("approved"))
            self.host_id = message.get("host_id") or self.host_id
            self.host_token = message.get("host_token") or self.host_token
            if self.approved:
                window = message.get("initial_report_window_seconds") or 0
                stats.report_windows.append(window)
                asyncio.ensure_future(self._burst(float(window)))
        elif kind == "command":
            ack_id = message.get("queue_message_id") or message.get("message_id")
            self.out["high"].append(payloads.command_ack(ack_id))
            command_type = (message.get("data") or {}).get("command_type", "unknown")
            stats.command_arrivals.append((time.monotonic(), command_type, self.index))
            self.out["high"].append(
                payloads.command_result(self, message.get("message_id"), command_type)
            )
        elif kind == "ping":
            self.out["high"].append(payloads.pong(message.get("message_id")))
        elif kind == "error":
            stats.errors_received[message.get("error_type", "unknown")] += 1

    async def _poll_once(self):
        """HTTP polling while demoted.  Today's agent sends nothing here (its
        outbound queue lookup is broken), so neither do we."""
        stats = self.fleet.stats
        stats.polling += 1
        try:
            token = await self._auth()
            headers = {
                "Authorization": f"Bearer {token or ''}",
                "X-Host-Token": self.host_token or "",
            }
            async with self._http().post(f"{self.fleet.base}/api/agent/poll", headers=headers,
                                         json={"host_id": self.host_id, "messages": []},
                                         timeout=aiohttp.ClientTimeout(total=30)) as resp:  # fmt: skip
                stats.counts[f"poll_http_{resp.status}"] += 1
                ok = resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            stats.counts["poll_error"] += 1
            ok = False
        finally:
            stats.polling -= 1
        await self.fleet.sleep(POLL_S if ok else 15, scaled=False)


class Fleet:
    """N agents, their shared payloads, HTTP sessions and stats."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        base_url: str,
        agents: int,
        source_ips: int,
        time_scale: float = 1.0,
        packages: int = 600,
        send_on_change: bool = False,
        jitter: bool = False,
        identity_auth: bool = False,
        bind_source: bool = True,
        report_window: bool = False,
        enrollment_tokens=(),
        first_index: int = 0,
    ):
        self.base = base_url.rstrip("/")
        self.ws_base = self.base.replace("http" + "://", "ws" + "://", 1).replace(
            "https" + "://", "wss" + "://", 1
        )
        self.source_ips = max(1, min(source_ips, agents))
        self.time_scale = time_scale
        self.send_on_change = send_on_change
        self.jitter = jitter
        self.identity_auth = identity_auth
        # False on a REMOTE load machine: the 127.20.x.y loopback addresses
        # only reach a server on the same machine; there every agent shares
        # the machine's address -- the large-NAT case.
        self.bind_source = bind_source
        self.report_window = report_window
        self.enrollment_tokens = list(enrollment_tokens)
        self.payloads = payloads.Payloads(packages=packages)
        self.stats = FleetStats()
        self.stopping = False
        # first_index: this fleet is one shard of a larger one (several
        # processes and machines); names and ids must not collide.
        self.agents = [SimAgent(self, first_index + i) for i in range(agents)]
        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._tasks: List[asyncio.Task] = []

    def local_addr(self, local_ip: str):
        """The source address to bind, or None to let the OS choose."""
        return (local_ip, 0) if self.bind_source else None

    def http_session(self, local_ip: str) -> aiohttp.ClientSession:
        """One session per source address; force_close like the agent's
        per-call sessions (no idle keep-alive sockets)."""
        session = self._sessions.get(local_ip)
        if session is None:
            connector = aiohttp.TCPConnector(
                local_addr=self.local_addr(local_ip), force_close=True, limit=0
            )
            session = aiohttp.ClientSession(connector=connector)
            self._sessions[local_ip] = session
        return session

    async def sleep(self, seconds: float, scaled: bool = True):
        await asyncio.sleep(seconds / self.time_scale if scaled else seconds)

    async def register_all(self, concurrency: int = 200):
        """Phase 1: every agent registers (bounded, so enrollment itself is
        not the storm being measured)."""
        gate = asyncio.Semaphore(concurrency)

        async def one(agent):
            async with gate:
                await agent.register()

        await asyncio.gather(*(one(a) for a in self.agents))

    def start(self, ramp_seconds: float = 0.0, register: bool = False):
        """Phase 2: start every agent's loop.  ramp_seconds spreads the
        starts (0 = all at once).  register=True re-registers first, as a
        real agent PROCESS start does; a server restart does not."""
        for agent in self.agents:
            delay = random.uniform(0, ramp_seconds) if ramp_seconds else 0.0
            self._tasks.append(
                asyncio.create_task(self._start_one(agent, delay, register))
            )

    async def _start_one(self, agent, delay, register):
        if delay:
            await asyncio.sleep(delay)
        await agent.run(register=register)

    async def restart_agents(self, forget: bool = False):
        """Every agent PROCESS restarts at once (a fleet-wide upgrade): its
        connection drops, it registers again and reconnects.  ``forget``: the
        agent before 22.2, whose send-on-change memory died with the process;
        otherwise it is kept, as the agent's on-disk record now does."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if forget:
            for agent in self.agents:
                agent.sent_at.clear()
        self.start(register=True)

    async def stop(self):
        self.stopping = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for session in self._sessions.values():
            await session.close()
