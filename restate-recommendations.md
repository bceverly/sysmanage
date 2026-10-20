# restate recommendations for Phase 24

Written from the restate project (`~/dev/restate`, version 1.5.0.1) for whoever
works on Phase 24 here ("Fleet Backup & Recovery with restate",
`ROADMAP.md`, the Phase 24 section). It reviews
`~/dev/restate/sysmanage-todo.md` (the restate-side list of items 1-21)
against restate's code as it is, and against this repository and
sysmanage-agent, and says what that changes for the plan.

Status at the time of writing: no restate code exists in sysmanage,
sysmanage-agent, sysmanage-docs or sysmanage-professional-plus. Phase 24
exists only as the ROADMAP section and the restate todo. ubiquiti has
already been captured by hand, so the 706-reallocated-sector urgency is
covered for now. The Phase 24 work should not be rushed on its account.

---

## 1. Corrections to the restate todo

These are places where the todo (and so the ROADMAP's "design constraints"
paragraph) is out of date or wrong about restate.

- **Item 13 (clones and agent identity) is done.** restate has an
  `identity` class, and `/var/lib/sysmanage-agent/agent.db` (plus the snap
  path) is in it. `restore --as NAME`:
  - leaves every identity file out of the restore;
  - keeps the machine's own where it differs from the image's (a fresh
    install made its own);
  - where it is the image's own (the same disk, or a copy of it), makes a
    new machine-id, D-Bus machine-id, random seed and, where sshd is
    installed, SSH host keys (`ssh-keygen -A`), and removes everything else,
    `agent.db` included, so the service makes it again;
  - sets `/etc/hostname` and rewrites the old name in `/etc/hosts`.

  A clone therefore registers as a new host. What remains is reporting
  this in the `--result` JSON (item 1).
- **Clones from one installer exist.** `restate autoinstall --clones
  FILE.csv` (columns `name,mac,serial,address,gateway,dns`) writes one
  Ubuntu autoinstall file. Its early-command picks the copy by MAC address
  or disk serial, and its late-command restores with `--as NAME`. Phase
  18 provisioning can use it as is.
- **`restate check REPO [--read-all]` exists.** It reads every pack and
  checks every chunk's SHA-256 against the pack's own index. It reports
  missing or truncated packs, leftovers and snapshots without an index,
  and names each damaged file. It exits 3 on damage. `--read-all` also
  reads every snapshot as a restore would (a dry run). `--syslog` is
  supported.
- **Item 14 (the man page) is right**, and there is a second problem. The
  BUGS section still says the repository stores each file whole, and that
  restore does not read the image first. FastCDC chunking and
  `--check-first` contradict both. In addition, the generated EXIT STATUS
  entry for 3 is malformed: a wrapped line became a stray `.TP`/`.B`. Both
  have to be fixed before the exit codes are called a contract.
- **Item 5, staging, is less of a problem than it says.** A repository
  capture does not stage the content in full: each pack streams to
  `packs/.NAME.tar.gz.tmp` in the repository and is renamed when complete.
  Only `-o FILE` images stage. restate's write cache is on local disk
  (`/var/cache/restate/repositories/<id>`). `--tmpdir` matters only for
  images, which Phase 24 does not use. The cache still needs the disk budget
  24.1 mentions.
- **Item 5, squashed ownership, should already work.** The repository code
  never checks who owns its files or directories. It creates them 0700/0600
  and ignores a failed `fchmod`. With `all_squash` the mapped `restate`
  user must be able to write to the export, and that is all. The 24.0 spike
  must still prove it.
- **Item 5, locking.** Locks are `flock(2)`. On Linux an NFSv4 client
  emulates `flock` with whole-file byte-range locks, which the server
  enforces, so it should hold across hosts. It does not on NFSv3 without
  lockd. Keep the 24.0 test exactly as planned: a second capture against
  the same repository must exit 5.
- **Item 6, a failed pause.** Today a hook whose pause fails is warned
  about and the files are copied as they are. The run can still end 0.
  Making that `incomplete` (exit 3) is a behavior change in restate. It is
  wanted, and it is part of item 1.
- **The shipped `mongodb` hook cannot pause UniFi.** It runs `systemctl stop
  mongod`, but UniFi's embedded mongod (port 27117) is started by the
  `unifi` service. Until a `unifi` hook exists, stop `unifi` around the
  capture, or rely on `/var/lib/unifi/backup/autobackup/*.unf`. Do not use
  `--quiesce` for it.

## 1a. The append-only, storage-side design (items 18-21)

The todo's later revision has hosts only append, with `prune`, `check` and
`copy` run by the NAS's own agent, and keys each repository by SysManage's
host id. Against restate's code as it is:

- **Keyless pruning on the NAS (item 19) is not possible today.** In an
  encrypted repository, the packs' `.idx` files and every snapshot's index
  are encrypted. A capture needs no secret key only because each host keeps
  plaintext copies of what it wrote in its own cache
  (`/var/cache/restate/repositories/<id>`). The NAS has no such cache, so it
  cannot tell which chunks or packs a snapshot uses. restate's own header
  says it: "Restoring, and pruning what the cache does not cover, need the
  secret key."

  The fix, in restate: two small plaintext records that reveal no content.
  - `snapshots/NAME/packs`: the pack names the snapshot references.
  - One record per pack holding the SHA-256 and size of the pack file as
    stored (encrypted bytes).

  With them, the NAS can, without the key:
  - prune at pack granularity, removing packs that no remaining snapshot
    references;
  - run a metadata check that every pack exists and is bit-for-bit what was
    written, which is item 18's "removed or changed since the previous
    check" and catches bit rot and tampering;
  - report usage (item 20).

  Repacking partly used packs, and `check --read-all`, still need the key
  for one run (item 10). Without the key, the result must say
  "metadata-only", never "passed".
- **Locks must work between a host and the NAS.** restate locks with
  `flock(2)`. On Linux, an NFSv4 client emulates `flock` with POSIX
  byte-range locks on the server. A process on the server itself that takes
  `flock` on the same file does not conflict with those, because Linux keeps
  `flock` and POSIX locks separate. So a prune run locally on the NAS would
  not see a host's capture in progress: the exact failure item 5 says must
  not happen. restate should switch to `fcntl` whole-file locks (OFD locks
  where available), which an NFS client and a local process on the server
  both see. The NFS spike must test this pairing directly: a capture from
  the host while the NAS runs prune, and the reverse.
- **Append-only (item 18) has to be enforced by the NAS, not by restate.**
  - A capture is already create-only in practice. Each pack, `.idx` and
    snapshot directory is written under a temporary name, then renamed to a
    new name. Nothing finished is rewritten or truncated, and the lock file
    is opened but never written.
  - The exceptions are small:
    - the one-time rewrite of a version-1 repository's marker;
    - writing `chunk-key` if it is missing;
    - unlinking the capture's own temporary files when it fails.
  - A flag on the host (`capture --append-only`) cannot protect anything.
    A compromised host is root, has the mount, and simply would not pass
    it. With `all_squash`, every file a host writes belongs to the same
    mapped user, so directory permissions cannot tell older files from
    newer ones either.
  - The protection has to come from the storage side. Either take a ZFS
    snapshot of the host's dataset after each capture, or have the NAS
    agent make each finished pack, `.idx` and snapshot immutable.
  - restate's part is to:
    - guarantee, and test, that a capture never modifies an existing file;
    - document the operations a capture needs: create, write, rename to a
      new name, unlink its own temporary files, and lock;
    - have `check` report anything changed since the last check, using the
      per-pack digests above.
  - Renaming a temporary file into place removes the temporary name, so a
    strictly create-only directory would break captures. NAS snapshots
    avoid that problem; immutable flags set after the run do too.
- **Item 20 (`du`)** is cheap with the per-pack records: per-snapshot sizes,
  the bytes each snapshot alone keeps alive, and growth, all at pack
  granularity, without the key. Without the records, the NAS can only report
  the total of the pack sizes.
- **Item 21 asks for more than restate has.** Only chunk boundaries are
  keyed (by `chunk-key`), and only in encrypted repositories. Chunk ids are
  the plain SHA-256 of the content. A store shared within a tenant would
  need keyed chunk ids (an HMAC with a per-store key), which changes the
  format. Settle this when item 17 is designed, not before.
- **Keying repositories by host id has a cost after a reinstall.** A
  reinstalled host has no cache. Its first capture into its old encrypted
  repository cannot read the existing `.idx` files or `chunk-key` without
  the secret key. It warns, uses a new chunking key, and stores everything
  again. That is one large capture after each reinstall, not a failure, but
  capacity planning should expect it. A restore before the reinstall's
  first capture avoids it, provided the cache is captured and restored.

## 2. What this repository and the agent should change

### 2.1 The privilege boundary is in the agent, not in restate

The Phase 24 boundary assumes the agent can only start one fixed unit.
`sysmanage-agent/installer/ubuntu/sysmanage-agent.sudoers` already grants
the agent user, with any arguments:

- `systemctl start *` (and stop, restart, enable, disable, daemon-reload)
- `/usr/bin/install`, `rm`, `sed`, `chmod`, `chown`, `rsync`, `mkdir`
- `mount` and `umount`
- `systemd-run`

The other OS variants (centos, opensuse, alpine, freebsd, netbsd) are
similar.

On top of that, the agent has an `execute_shell` command
(`core/agent_utils.py`, `operations/system_control.py`). Commands from the
server are type-checked but not signed, and `deploy_files` does not confine
destination paths.

So whoever controls the agent user, or the server's message stream, is
effectively root already. A root-owned job file and "one exact sudoers
form" protect nothing until those grants are narrowed.

Recommendations:

- Build the restate side anyway. Other restate users get the protection,
  and it is the right shape once the agent is tightened.
- Add a Phase 24 item, or a cross-cutting one ahead of it: replace the
  bare-binary grants that backup relies on with exact forms, starting
  with `systemctl start restate-job@*` (or `restate-backup@*` until restate
  ships its unit). Confine `deploy_files` destinations used for backup to
  `/etc/restate/sysmanage.d/`.
- Treat the policy-to-job-file path as the trust boundary. The agent
  validates every field against an allow-list:
  - the target must be under the NAS mount;
  - rules are chosen by name, never by file content;
  - no free-form flags.

  restate then re-validates when it reads the file.

### 2.2 The feature probe has to be a collected fact

`core/capability_probes.py` rule 3 forbids running a subprocess in a
capability probe (executable lookups only). So the `backup` capability
group is gated on `missing_tool` with an executable lookup for
`/usr/sbin/restate`.

`restate features --json` must be collected separately and cached, the way
`collection/fact_osquery.py` derives its table set: a fixed argv with no
shell, then `json.loads`. The server then refuses to send a job that this
host's restate cannot run.

### 2.3 Running restate and reading its output

Follow the existing patterns:

- `core/bounded_subprocess.run_bounded` for timeouts;
- `hardware_health.py`'s `smartctl -j` handling for JSON with an exit code;
- `operations/malware_scan_operations.py` for running work in an executor,
  never in the WebSocket loop.

Long captures should go through the systemd unit, not a subprocess, so they
survive an agent restart. The agent then reads the `--result` file the unit
left.

Exit-code mapping, which restate will document as stable:

| Exit | Meaning | SysManage |
|------|---------|-----------|
| 0 | success (diff/verify: no differences) | ok |
| 1 | differences found (diff/verify only) | ok, with drift |
| 2 | usage error, bad image or rules, I/O error | failure |
| 3 | incomplete: files unreadable or not put back; for check, the repository is damaged | warning |
| 4 | not signed by a trusted key; nothing used | failure ("not signed") |
| 5 | busy: another capture or prune holds the lock | retry later |

### 2.4 Housekeeping found on the way

- `ROADMAP.md` says "Current Version: v3.10.0.0", while the tags are at
  v3.11.0.x.
- The sudoers `SYSMANAGE_COMPLIANCE_READ` comment says "server ROADMAP 24.4".
  That is the old numbering, and now clashes with the backup phase's 24.4.
- The Phase 24 foundation paragraph lists restate's capabilities without
  `check`, the identity class, `--as` or `--clones`. Update it to match
  section 1 of this file.

## 3. The restate work, in the order to do it

restate's own project rules apply to all of it:

- 80% coverage overall and per file;
- every parser fuzzed (the job file and the JSON writers included);
- clean under lint, cppcheck, memcheck, the security scan and BSD
  portability;
- only `run.c` starts processes.

1. **The contract first:** fix the man page (BUGS and EXIT STATUS); add
   `--result FILE` (written atomically) for capture, prune, check, restore,
   status and verify. The result includes each hook's pause and resume
   outcome, unreadable paths with their reasons, and warnings. A failed
   pause makes the run `incomplete`. Then add `features --json`. These are
   todo items 1, 8 and 14.
2. **`restate run JOBFILE` and `restate-job@.service`/`.timer`:** root-owned,
   not group- or world-writable (the hooks.d rule), only known and typed
   keys, and no way to name a program. The unit sets `Nice=`,
   `IOSchedulingClass=idle`, a long `TimeoutStartSec=`, and `KillMode=mixed`
   so resume hooks still run. These are items 3 and 4.
3. **The NFS spike (24.0), by hand on one host:**
   - `init`, a capture, `check --read-all`;
   - two captures at once, where the second must exit 5;
   - a capture interrupted by unmounting, then `check`, which must report
     the leftover `.tmp` and then pass. Document `check` as the recovery
     step, and `prune` as what removes leftovers.

   - a capture from the host while the NAS prunes locally, and the
     reverse, after the switch to `fcntl` locks (section 1a).

   This is item 5. The result decides whether a lock file with a holder
   record is needed at all.
3a. **The storage side (items 18-20):**
   - the per-snapshot pack list and the per-pack digests;
   - keyless pack-level prune, and a metadata-only `check` with
     changed-since-last-check reporting;
   - `du --json`;
   - a test that a capture never modifies an existing file.

   On the NAS: a ZFS snapshot or immutable flags after each capture.
4. **Hooks:** `--quiesce-with NAME`, a `unifi` hook (`mongodump --port
   27117` into `$RESTATE_DUMP_DIR`, then stop and start `unifi`), and a
   `nextcloud` hook (`occ maintenance:mode --on/--off` as the web server
   user, around its database's existing hook). Confirm that Maildir is
   classed as state and copies safely without a stop. This is item 6.
5. **`--progress=json`** and **`restore --include PATTERN`** with a
   `--result` dry-run plan. These are items 2 and 7.
6. **Then:**
   - unattended snapshot signing (`sign REPO::NAME`), item 9;
   - private keys supplied for one restore, item 10;
   - `restate copy` between repositories, encrypted packs as they are,
     item 11;
   - `capture --estimate`, item 12.
7. **Later:**
   - rpm, apk, the BSDs' and macOS's package databases (item 15). The
     fleet's non-Ubuntu hosts depend on it.
   - filesystem-snapshot quiescing;
   - output stable for the bare-metal hand-off (item 16);
   - the shared store (items 17 and 21, with keyed chunk ids).

## 4. Until the integration exists

A manual nightly capture on any Ubuntu host, from root's crontab, gives
Phase 24 a baseline to measure against:

```sh
# once
restate init /mnt/nas/restate/$(hostname -f)
# nightly
restate capture --quiesce --syslog -o /mnt/nas/restate/$(hostname -f)
restate prune --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --syslog /mnt/nas/restate/$(hostname -f)
# weekly: the test restore
restate check --read-all --syslog /mnt/nas/restate/$(hostname -f)
```

Here the host prunes its own repository. Under the append-only design
(section 1a), `prune` and `check` move to the NAS once restate supports it.

On ubiquiti, leave out `--quiesce` and wrap the capture in `systemctl stop
unifi` / `systemctl start unifi` until the `unifi` hook exists.
