# proxyDHCP on real hardware — test plan

**Status:** the last open non-hardware-blocked checkbox in Phase 19
(`ROADMAP.md` → *"proxyDHCP validated on REAL HARDWARE"*).
**Written:** 2026-08-21. **Run it on:** a Windows 11 machine with Hyper-V
(the T480), or any rig meeting the constraints in [The rig](#the-rig).

Read this instead of re-deriving it. Everything below is either quoted from
the engine source or was measured on a dated run; nothing here is a guess.

---

## 1. What is actually being proven

Our dnsmasq **proxyDHCP** config is believed correct and has never been
executed by a non-iPXE PXE client. proxyDHCP is the mode that lets SysManage
provision machines on a network whose DHCP server we do not own — the normal
corporate case — so "believed correct" is not good enough to ship.

The claim under test, in one sentence:

> A stock vendor PXE ROM, on a segment where **someone else** owns DHCP, will
> take our proxy offer, TFTP our first-stage iPXE, and that iPXE will chain to
> the per-MAC boot script over HTTP.

Two legs, because the config serves two client architectures:

| Leg | Client | dnsmasq entry exercised | Status before this test |
| :-- | :----- | :---------------------- | :---------------------- |
| A | BIOS / legacy | `pxe-service=tag:!ipxe,x86PC,...,sysmanage-ipxe.kpxe` | never executed by a non-iPXE ROM |
| B | UEFI x86-64 | `pxe-service=tag:!ipxe,x86-64_EFI,...,sysmanage-ipxe.efi` | never executed at all |

Leg B is a bonus that closes a second ROADMAP note ("UEFI + proxyDHCP is
unproven"). Do leg A first — it is the one the config was designed around.

## 2. Why the VM harness cannot do this

Do not try to shortcut this on QEMU/KVM. It has been measured twice and the
harness is the problem, not our config:

* **QEMU's boot ROM *is* iPXE** (`efi-virtio.rom` / `efi-e1000.rom` are iPXE
  compiled as EFI drivers), so the guest runs the full PXE flow itself and
  never takes the vendor-ROM path our config is written for. Measured
  2026-08-03 with an iPXE `DEBUG=dhcp:3` build narrating its own state machine:
  * with a `pxe-service` for the iPXE tag → the offer becomes a **menu**
    (`DHCPOFFER ... pxe`), the client runs PXEBS, and PXEBS times out no matter
    how correctly dnsmasq answers;
  * without one → the client stays in plain ProxyDHCP (`DHCPOFFER ... proxy`)
    and accepts our 4011 ACK, but that ACK carries no filename, so it halts
    with `Nothing to boot`.
* **UEFI does not rescue it.** Verified 2026-08-14 from *inside* the firmware
  (UEFI Shell `drivers` + `ifconfig -l`) on three independent OVMF builds:
  `VirtioNetDxe` present and bound in all three; `MnpDxe` / `Ip4Dxe` /
  `Dhcp4Dxe` / `UefiPxeBcDxe` absent in all three; no `UEFI PXEv4` boot option
  ever written to NVRAM. A SeaBIOS control on the same rig netbooted fine, so
  the harness was never the variable.

Hence: a physical x86 box in CSM mode, a **Hyper-V Generation 1 VM**, or VMware
with BIOS firmware. **Not VirtualBox** (ships iPXE — same dead end) and **not**
an ARM machine (ARM64 guests are UEFI-only, Hyper-V has no Gen 1 on ARM, and
`build-embedded-ipxe.sh` produces an x86_64 image only).

Hyper-V is the recommendation because its Gen 1 PXE ROM is Microsoft's own, not
iPXE — which is precisely the missing client.

## 3. The rig

Three things must be true at once, and only the third is fiddly:

1. **Someone else owns DHCP on the segment.** The home router is ideal — that
   IS the scenario. Do not disable it; proxyDHCP coexisting with it is the
   point.
2. **A PXE client whose ROM is not iPXE** (see above).
3. **Our dnsmasq must sit on the same L2 broadcast domain as the client.**

### Where to run the dnsmasq/TFTP side

| Option | Verdict |
| :----- | :------ |
| **Linux VM on Hyper-V, External vSwitch** | **Recommended.** Self-contained on the laptop, real L2 presence on the LAN, and the client VM sits on the same switch. |
| The existing Linux box (gdr-t14) on the LAN | Also fine, and reuses a working environment. Costs you two machines and two sessions. |
| **WSL2** | **Avoid.** WSL2 is NAT'd, so DHCP broadcast and TFTP from the LAN do not reach it. Mirrored networking mode may change this; it is unproven here and this test is not the place to find out. |

Use **wired Ethernet**. A Hyper-V External switch over Wi-Fi is a known source
of bridging weirdness and would make a failure ambiguous.

Firewall on the dnsmasq host must pass **UDP 67, 68, 4011** (proxyDHCP) and
**UDP 69** (TFTP).

## 4. Server-side setup

### 4.1 Stage the boot artifacts

Both are committed in the Pro+ repo at `storage/ipxe/`:

| File | Size | Used by |
| :--- | ---: | :------ |
| `sysmanage-ipxe.kpxe` | 72,728 | leg A (BIOS) |
| `sysmanage-ipxe.efi` | 1,165,824 | leg B (UEFI) |

Copy both into the TFTP root (`/var/lib/sysmanage/tftp` by default). If
`sysmanage-ipxe.efi` is missing or a different size, rebuild it with
`scripts/build-embedded-ipxe.sh` — it pins iPXE at SHA
`e6d0a97c05d238c17eeae5116cb6e9c0fc9fdb56` and now asserts `HEAD == IPXE_REF`
before building. (It once built against a stale tree and *succeeded*, which is
the worst way to be wrong.)

### 4.2 Render the config with the product, not by hand

The artifact under test is what the engine emits. Get it from
Provisioning → readiness/config advisor in the UI, or directly:

```bash
cd sysmanage-professional-plus
.venv/bin/python -c "
import sys; sys.path.insert(0,'tests')
from _engine_loader import load_engine
eng = load_engine('provisioning_engine')
class R: pass
r = R()
r.mode='proxy'; r.server='dnsmasq'; r.interface='eth0'; r.subnet='192.168.1.0'
r.netmask='255.255.255.0'; r.range_start=None; r.range_end=None; r.router=None; r.dns=None
r.tftp_root='/var/lib/sysmanage/tftp'; r.boot_file='pxelinux.0'; r.server_ip='192.168.1.50'
r.ipxe_boot_url='http://192.168.1.50:8080/api/v1/provisioning/boot.ipxe'
r.ipxe_image='undionly.kpxe'; r.ipxe_chain_file='sysmanage.ipxe'
r.ipxe_embedded_image='sysmanage-ipxe.kpxe'; r.ipxe_efi_image='sysmanage-ipxe.efi'
print(eng.render_dnsmasq_config(r))
"
```

Substitute your interface, subnet and server IP. That command produced exactly
this on 2026-08-21, which is what a correct run should look like:

```
# Managed by SysManage provisioning (Phase 18.2).  Do not edit by hand.
# Mode: proxy-DHCP
interface=eth0
bind-interfaces
dhcp-range=192.168.1.0,proxy
enable-tftp
tftp-root=/var/lib/sysmanage/tftp
dhcp-match=set:ipxe,175
dhcp-match=set:efi-x86-64,option:client-arch,7
dhcp-match=set:efi-x86-64,option:client-arch,9
dhcp-option-pxe=tag:ipxe,67,http://192.168.1.50:8080/api/v1/provisioning/boot.ipxe
dhcp-boot=tag:ipxe,http://192.168.1.50:8080/api/v1/provisioning/boot.ipxe
pxe-service=tag:!ipxe,x86PC,"SysManage provisioning",sysmanage-ipxe.kpxe
pxe-service=tag:!ipxe,x86-64_EFI,"SysManage provisioning",sysmanage-ipxe.efi
pxe-service=tag:!ipxe,BC_EFI,"SysManage provisioning",sysmanage-ipxe.efi
pxe-prompt=tag:!ipxe,"SysManage provisioning",0
```

Two lines carry the whole design and are worth understanding before you debug
anything:

* `dhcp-match=set:ipxe,175` tags clients that are **already iPXE**. Those get
  option 67 / `dhcp-boot` (the HTTP boot script) and **no** `pxe-service` —
  deliberately, because a boot item turns the offer into a PXEBS menu that
  times out. A vendor ROM is untagged, takes the `tag:!ipxe` menu path, and
  TFTPs the first stage.
* There is intentionally **no** `pxe-service` for the iPXE tag. That is a
  genuine fork with no third option; both sides were measured (see §2).

### 4.3 Run it

Foreground, with the rendered file and nothing else, so the artifact under test
stays pristine:

```bash
sudo dnsmasq --no-daemon --log-dhcp --port=0 --conf-file=/path/to/sysmanage-provisioning.conf
```

`--port=0` disables dnsmasq's DNS listener for the test run. It is a
command-line flag on purpose: the rendered file is the thing being validated
and should not be edited to make the test convenient.

### 4.4 Arm a per-MAC assignment

The point is per-MAC selection *through* proxyDHCP, so drive the real path:
Provisioning → Bare Metal → create an install assignment pinned to the client
VM's MAC, and arm netboot. `boot.ipxe` is served by the sysmanage server, so it
must be running and reachable from the segment at the `ipxe_boot_url` above.

If the server genuinely cannot be stood up, a static iPXE script served over
HTTP still proves the boot chain — but it does **not** prove per-MAC selection,
so label the result accordingly rather than ticking the box.

## 5. Client-side setup (Hyper-V)

### Leg A — Generation 1 (BIOS, `x86PC`)

* Create a **Generation 1** VM.
* Add a **Legacy Network Adapter** and attach it to the External switch. This
  matters: a Gen 1 VM cannot PXE boot from the synthetic adapter.
* Set a **static MAC** and use it for the assignment in §4.4.
* Boot order: network first.

### Leg B — Generation 2 (UEFI, `x86-64_EFI`)

* Create a **Generation 2** VM, standard network adapter, External switch.
* **Disable Secure Boot** — `Set-VMFirmware -VMName <name> -EnableSecureBoot Off`.
  Our `sysmanage-ipxe.efi` is not signed by the Microsoft UEFI CA, so Secure
  Boot will refuse it. A refusal here is a signing fact, not a config defect;
  do not chase it as one.
* Static MAC, network first in the firmware boot order.

### Negative control (do not skip)

Boot a **second** VM whose MAC has **no** assignment. Without it, "the client
booted our installer" does not prove per-MAC selection — a config that served
every machine the same thing would look identical to success. This mirrors what
`pxe_provision_spike.py` does on the virtual rig.

## 6. Pass criteria

Leg A passes when **all** of these hold:

1. The client gets its **address from the router**, and a **separate proxy
   offer** from us — dnsmasq logs `DHCPOFFER ... proxy`, not a lease.
2. The client TFTPs **`sysmanage-ipxe.kpxe`** from our TFTP root (visible in
   `--log-dhcp` output and in the tcpdump on UDP 69).
3. That iPXE performs an **ordinary DHCP** — no ProxyDHCP, no PXEBS — and
   `dhcp-boot=tag:ipxe` hands it the HTTP boot URL.
4. It fetches `boot.ipxe` and boots the assigned installer.
5. The **negative control** does not boot our installer.

Leg B is the same with `sysmanage-ipxe.efi` at step 2.

Anything short of step 3 means the proxy hand-off failed, which is the thing
being tested. Steps 4–5 then tell you whether per-MAC selection survived it.

## 7. Evidence to capture

Screenshots alone are not enough; capture the wire.

```bash
sudo tcpdump -i eth0 -n -vv 'port 67 or port 68 or port 4011 or port 69' -w proxydhcp.pcap
```

Keep: the pcap, the full `dnsmasq --log-dhcp` output, and the client console for
both the assigned and the control MAC. The 2026-08-03 QEMU measurement is only
citable today because its capture was kept.

## 8. Known failure modes and what each one means

| Symptom | Meaning |
| :------ | :------ |
| `PXEBS ... Connection timed out` | The client took the PXE **menu** path. On a vendor ROM this should not happen — check that the client really is not iPXE. |
| `Nothing to boot` | Client stayed in plain ProxyDHCP and got an ACK with no filename. Expected on QEMU (§2); on real hardware it means the `tag:!ipxe` `pxe-service` did not match — check DHCP option 93 in the pcap against the arch entries. |
| Client boots the router's own PXE, or nothing | Another PXE responder on the segment, or our `interface=` / `bind-interfaces` is pointed at the wrong NIC. |
| Secure Boot rejects the image (leg B) | Expected with Secure Boot on. Turn it off; see §5. |
| dnsmasq exits at startup | Port 53 already held (use `--port=0`), or the interface name is wrong. |
| UEFI client gets no answer at all | `ipxe_efi_image` was `None` when the config was rendered, so only `x86PC` was advertised. Re-render with it set. |

## 9. When it passes

1. Tick **"proxyDHCP validated on REAL HARDWARE"** in `ROADMAP.md` (Phase 19)
   with a dated note recording: the rig, which legs passed, and where the pcap
   and logs live.
2. If leg B passed, also retire the *"UEFI + proxyDHCP is unproven"* language in
   the UEFI first-stage item above it.
3. Update this document with anything that turned out to be wrong. The point of
   it is that the next person does not re-derive what we already learned.
