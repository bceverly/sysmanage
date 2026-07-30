#!/usr/bin/env bash
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# buildProxmoxTestVM.sh — Stand up a Proxmox VE hypervisor as a NESTED VM on
# libvirt/KVM so the Phase 18.1 (S5) provisioning "proxmox" compute-provider can
# be validated end to end against a REAL Proxmox API (create / status / destroy
# a guest, cloud-init, auto-enroll).
#
# Proxmox VE is its own bare-metal OS, so we DON'T install it on this host — we
# run it as a guest VM.  Its REST API (https://<vm-ip>:8006) is all the provider
# needs; the VM gets a NAT IP THIS host reaches directly.  Nested virtualization
# is enabled so the Proxmox VM can boot its own guests (needed for the full
# create -> boot -> auto-enroll test; not for API-only checks).
#
# Unlike a cloud image, Proxmox installs from an ISO via a GUI installer, so the
# FIRST `start` boots the installer and you finish it ONCE in a graphics console
# (`console` subcommand); after that `stop`/`start` just power the VM off/on and
# the install persists.  `destroy` wipes it.
#
# Usage:
#   scripts/buildProxmoxTestVM.sh start     # create+boot (installer 1st time) / power on
#   scripts/buildProxmoxTestVM.sh stop      # graceful shutdown (keeps the install)
#   scripts/buildProxmoxTestVM.sh status    # state + IP + API URL + token hint
#   scripts/buildProxmoxTestVM.sh console   # open a graphics console (do the install)
#   scripts/buildProxmoxTestVM.sh destroy   # undefine + delete the disk (full teardown)
#
# Requirements on this host:
#   sudo apt install libvirt-daemon-system virtinst qemu-utils virt-viewer wget
#   # + nested KVM enabled:  cat /sys/module/kvm_intel/parameters/nested  -> Y
#   #   (enable: echo 'options kvm_intel nested=1' | sudo tee /etc/modprobe.d/kvm.conf
#   #    && sudo modprobe -r kvm_intel && sudo modprobe kvm_intel   ; kvm_amd on AMD)
#
# Overridable via env:
#   PVE_VERSION (default 8.4-1)   PVE_ISO_URL   VM_NAME   VM_MEM_MB   VM_VCPUS
#   VM_DISK_GB   VM_OS_VARIANT (default debian12)   WORKDIR
set -euo pipefail

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
# 8.4-1 is the latest Debian-12-based release (matches --os-variant debian12
# below).  Proxmox 9.x is Debian-13-based — if you bump to it, also set
# VM_OS_VARIANT=debian13.  Current ISOs live at https://enterprise.proxmox.com/iso/
PVE_VERSION="${PVE_VERSION:-8.4-1}"
PVE_ISO_URL="${PVE_ISO_URL:-https://enterprise.proxmox.com/iso/proxmox-ve_${PVE_VERSION}.iso}"
VM_NAME="${VM_NAME:-sysmanage-proxmox}"
VM_MEM_MB="${VM_MEM_MB:-8192}"
VM_VCPUS="${VM_VCPUS:-4}"
VM_DISK_GB="${VM_DISK_GB:-32}"
VM_OS_VARIANT="${VM_OS_VARIANT:-debian12}"   # debian13 for Proxmox 9.x
WORKDIR="${WORKDIR:-/var/lib/libvirt/images}"
NET_BRIDGE="sysmanage-ha"          # shared with the other test harnesses, if up
NET_FALLBACK="default"

ISO="${WORKDIR}/proxmox-ve_${PVE_VERSION}.iso"
DISK="${WORKDIR}/${VM_NAME}.qcow2"

log() { printf '\033[1;34m[proxmox]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[proxmox] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

net_arg() {
  if virsh net-info "${NET_BRIDGE}" >/dev/null 2>&1; then
    echo "network=${NET_BRIDGE},model=virtio"
  else
    virsh net-info "${NET_FALLBACK}" >/dev/null 2>&1 || \
      die "no '${NET_FALLBACK}' libvirt network (start it: virsh net-start default)"
    echo "network=${NET_FALLBACK},model=virtio"
  fi
}

check_nested() {
  local f n
  for f in /sys/module/kvm_intel/parameters/nested \
           /sys/module/kvm_amd/parameters/nested; do
    [ -r "${f}" ] || continue
    n="$(cat "${f}")"
    case "${n}" in
      Y|1) return 0 ;;
      *) log "WARNING: nested virt is OFF (${f}=${n}). The Proxmox VM will run"
         log "         but CANNOT boot its own guests. See the header to enable." ;;
    esac
  done
}

# The libvirt system pool (/var/lib/libvirt/images) is root-owned and
# AppArmor-blessed for the qemu-guest user, so writing the ISO/disk there needs
# root even though VM create/start goes through your libvirt group.  We sudo
# only those file ops (you may be prompted); everything else runs as you.
SUDO=""
[ -w "${WORKDIR}" ] || SUDO="sudo"

download_iso() {
  [ -f "${ISO}" ] && { log "ISO ${ISO} present, reusing"; return; }
  command -v wget >/dev/null || die "wget not installed"
  if [ -n "${SUDO}" ]; then
    log "writing to ${WORKDIR} needs root — you may be prompted for sudo."
  fi
  log "downloading Proxmox VE ${PVE_VERSION} ISO (~1.3 GB)..."
  ${SUDO} wget -O "${ISO}.part" "${PVE_ISO_URL}" \
    || die "ISO download failed (set PVE_ISO_URL)"
  ${SUDO} mv "${ISO}.part" "${ISO}"
  ${SUDO} chmod 0644 "${ISO}"   # libvirt-qemu must be able to read it
}

# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------
do_start() {
  # Already defined -> just power it on.
  if virsh dominfo "${VM_NAME}" >/dev/null 2>&1; then
    virsh start "${VM_NAME}" >/dev/null 2>&1 && log "powered on ${VM_NAME}" \
      || log "${VM_NAME} already running"
    do_status
    return
  fi
  command -v virt-install >/dev/null || die "virt-install not installed"
  ${SUDO} mkdir -p "${WORKDIR}"
  check_nested
  download_iso
  log "creating Proxmox VM ${VM_NAME} (${VM_VCPUS} vCPU / ${VM_MEM_MB} MiB / ${VM_DISK_GB} GB)..."
  # host-passthrough exposes VT-x/AMD-V to the guest (nested); the graphical
  # installer needs a display, so VNC + no autoconsole (use the `console` cmd).
  virt-install --name "${VM_NAME}" \
    --vcpus "${VM_VCPUS}" --memory "${VM_MEM_MB}" \
    --cpu host-passthrough \
    --disk "path=${DISK},size=${VM_DISK_GB},format=qcow2,bus=virtio" \
    --cdrom "${ISO}" \
    --network "$(net_arg)" \
    --os-variant "${VM_OS_VARIANT}" \
    --graphics vnc --video virtio --noautoconsole
  log "installer booted.  Finish the ONE-TIME install now:"
  log "    scripts/buildProxmoxTestVM.sh console"
  log "During install pick a static IP on the NAT subnet (e.g. 192.168.122.50/24,"
  log "gateway 192.168.122.1) so this host can reach the API afterward."
}

do_stop() {
  virsh dominfo "${VM_NAME}" >/dev/null 2>&1 || { log "${VM_NAME} not defined"; return; }
  virsh shutdown "${VM_NAME}" >/dev/null 2>&1 || virsh destroy "${VM_NAME}" >/dev/null 2>&1 || true
  log "shutting down ${VM_NAME} (install preserved; 'start' to power back on)"
}

do_destroy() {
  virsh destroy "${VM_NAME}" >/dev/null 2>&1 || true
  virsh undefine "${VM_NAME}" --nvram >/dev/null 2>&1 || true
  ${SUDO} rm -f "${DISK}"
  log "destroyed + removed disk for ${VM_NAME} (ISO kept at ${ISO})"
}

vm_ip() {
  # Prefer the ARP source (the VM's ACTUAL current IP) over the DHCP lease — the
  # installer boots via DHCP, but the installed Proxmox uses the static IP you
  # set, so the stale lease would otherwise report the wrong address.
  local ip
  ip="$(virsh domifaddr "${VM_NAME}" --source arp 2>/dev/null \
        | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1)"
  [ -n "${ip}" ] || ip="$(virsh domifaddr "${VM_NAME}" 2>/dev/null \
        | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1)"
  echo "${ip}"
}

do_status() {
  virsh dominfo "${VM_NAME}" 2>/dev/null || { log "${VM_NAME} not defined (run: start)"; return; }
  local ip; ip="$(vm_ip)"
  log "IP: ${ip:-<none yet — finish the install / wait for boot>}"
  if [ -n "${ip}" ]; then
    log "Proxmox web UI + API:  https://${ip}:8006/"
    log "Create an API token:   web UI -> Datacenter -> Permissions -> API Tokens"
    log "Then register it as a compute resource (once S5 ships), e.g.:"
    echo "    POST /api/v1/provisioning/compute-resources"
    echo "      { name: 'beast-pmx', kind: 'proxmox',"
    echo "        connection_uri: 'https://${ip}:8006',"
    echo "        credential_ref: 'secret/data/prov/beast-pmx' }"
  fi
}

do_console() {
  virsh dominfo "${VM_NAME}" >/dev/null 2>&1 || die "${VM_NAME} not defined (run: start)"
  command -v virt-viewer >/dev/null || die "virt-viewer not installed (apt install virt-viewer)"
  exec virt-viewer "${VM_NAME}"
}

do_eject() {
  # After the install finishes, detach the ISO so the VM boots the installed
  # disk instead of the installer on the next reboot.
  virsh dominfo "${VM_NAME}" >/dev/null 2>&1 || die "${VM_NAME} not defined"
  local dev
  dev="$(virsh domblklist "${VM_NAME}" 2>/dev/null \
         | awk -v iso="${ISO##*/}" 'index($2, iso){print $1}' | head -1)"
  [ -n "${dev}" ] || { log "no install ISO attached (already ejected)"; return; }
  virsh change-media "${VM_NAME}" "${dev}" --eject --config --live 2>/dev/null \
    || virsh change-media "${VM_NAME}" "${dev}" --eject --config 2>/dev/null \
    || die "could not eject ${dev}"
  log "ejected the install ISO (${dev}); ${VM_NAME} now boots from disk"
}

case "${1:-}" in
  start)   do_start ;;
  stop)    do_stop ;;
  status)  do_status ;;
  console) do_console ;;
  eject)   do_eject ;;
  destroy) do_destroy ;;
  *) echo "usage: $0 {start|stop|status|console|eject|destroy}" >&2; exit 2 ;;
esac
