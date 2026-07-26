#!/usr/bin/env bash
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# buildImageModeTestVM.sh — Provision an IMAGE-MODE Linux VM (bootc or
# rpm-ostree) on libvirt/KVM so Phase 17.3 (image-mode host management) can be
# validated end to end against a REAL host: detection, then stage / apply /
# rollback of the booted image.
#
# Two backends (image-mode distros do NOT use cloud-init — bootc/OSTree systems
# are provisioned by Ignition or a bootc container install; this harness uses
# the native mechanism for each):
#
#   rpm-ostree  — Fedora CoreOS (FCOS).  Provisioned by Ignition (Butane ->
#                 Ignition).  `rpm-ostree status`, `rpm-ostree upgrade`,
#                 `rpm-ostree rollback`.  This is the default (well-documented,
#                 fully scriptable).
#   bootc       — Fedora bootc.  A qcow2 built from the fedora-bootc container
#                 with bootc-image-builder (needs podman on THIS host).  `bootc
#                 status --json`, `bootc upgrade [--apply]`, `bootc rollback`.
#
# Usage:
#   scripts/buildImageModeTestVM.sh start [rpm-ostree|bootc]   # create + boot
#   scripts/buildImageModeTestVM.sh stop  [rpm-ostree|bootc]   # destroy + clean
#   scripts/buildImageModeTestVM.sh status [rpm-ostree|bootc]  # state + IP
#   scripts/buildImageModeTestVM.sh ssh   [rpm-ostree|bootc]   # ssh into it
#
# The VM gets the sysmanage-agent installed and pointed at a SysManage server
# (SYSMANAGE_SERVER env, default 10.90.0.10) so it registers as an image-mode
# host.  Because rpm-ostree/bootc roots are read-only, the agent is layered with
# `rpm-ostree install` (FCOS) or baked into the bootc image.
#
# Requirements on the host:
#   sudo dnf install libvirt virt-install qemu-img butane coreos-installer \
#                    podman   # (podman only for the bootc backend)
#   # (Debian/Ubuntu host: apt install libvirt-daemon-system virtinst qemu-utils;
#   #  butane/coreos-installer via their release binaries; podman for bootc.)
#
# Network: reuses the isolated 10.90.0.0/24 "sysmanage-ha" libvirt bridge if it
# exists (so the VM shares a subnet with a server started by another harness);
# otherwise it falls back to the default NAT network.  THIS host reaches the VM
# directly on that subnet — no tunnel needed.
#
# Credentials:  user = core (FCOS) / cloud-user (bootc);  SSH key = ~/.ssh/id_*.
set -euo pipefail

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
BACKEND="${2:-rpm-ostree}"
SYSMANAGE_SERVER="${SYSMANAGE_SERVER:-10.90.0.10}"
NET_BRIDGE="sysmanage-ha"          # shared with the other test harnesses
NET_FALLBACK="default"
WORKDIR="${WORKDIR:-/var/lib/libvirt/images}"
SSH_PUBKEY="$(cat "${HOME}"/.ssh/id_ed25519.pub 2>/dev/null || cat "${HOME}"/.ssh/id_rsa.pub 2>/dev/null || true)"

FCOS_STREAM="${FCOS_STREAM:-stable}"
BOOTC_IMAGE="${BOOTC_IMAGE:-quay.io/fedora/fedora-bootc:41}"

case "${BACKEND}" in
  rpm-ostree) VM_NAME="sysmanage-imgmode-fcos"  ; VM_USER="core" ;;
  bootc)      VM_NAME="sysmanage-imgmode-bootc" ; VM_USER="cloud-user" ;;
  *) echo "unknown backend: ${BACKEND} (use rpm-ostree|bootc)" >&2; exit 2 ;;
esac
DISK="${WORKDIR}/${VM_NAME}.qcow2"
IGN="${WORKDIR}/${VM_NAME}.ign"

log() { printf '\033[1;34m[img-mode]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[img-mode] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

net_arg() {
  if virsh net-info "${NET_BRIDGE}" >/dev/null 2>&1; then
    echo "network=${NET_BRIDGE}"
  else
    echo "network=${NET_FALLBACK}"
  fi
}

# --------------------------------------------------------------------------
# Provisioning payloads
# --------------------------------------------------------------------------

# Butane config for Fedora CoreOS: SSH key, hostname, and a systemd unit that
# layers the sysmanage-agent with `rpm-ostree install` on first boot then points
# it at the server.  (rpm-ostree install triggers a staged deployment + reboot;
# the agent starts on the next boot.)
write_butane() {
  [ -n "${SSH_PUBKEY}" ] || die "no SSH public key found in ~/.ssh"
  cat > "${WORKDIR}/${VM_NAME}.bu" <<EOF
variant: fcos
version: 1.5.0
passwd:
  users:
    - name: core
      ssh_authorized_keys:
        - ${SSH_PUBKEY}
storage:
  files:
    - path: /etc/hostname
      mode: 0644
      contents:
        inline: ${VM_NAME}
    - path: /etc/sysmanage-agent/sysmanage-agent.yaml
      mode: 0644
      contents:
        inline: |
          server:
            hostname: ${SYSMANAGE_SERVER}
            port: 8443
            use_https: true
systemd:
  units:
    - name: sysmanage-agent-layer.service
      enabled: true
      contents: |
        [Unit]
        Description=Layer sysmanage-agent onto the image-mode host (once)
        After=network-online.target
        Wants=network-online.target
        ConditionPathExists=!/var/lib/sysmanage-agent-layered
        [Service]
        Type=oneshot
        RemainAfterExit=yes
        # rpm-ostree install layers the package into a NEW deployment; the agent
        # comes up after the reboot this triggers.
        ExecStart=/usr/bin/rpm-ostree install --idempotent --allow-inactive sysmanage-agent
        ExecStart=/usr/bin/touch /var/lib/sysmanage-agent-layered
        ExecStart=/usr/bin/systemctl reboot
        [Install]
        WantedBy=multi-user.target
EOF
  command -v butane >/dev/null || die "butane not installed"
  butane --pretty --strict "${WORKDIR}/${VM_NAME}.bu" > "${IGN}"
  log "wrote Ignition config ${IGN}"
}

download_fcos() {
  [ -f "${DISK}" ] && { log "disk ${DISK} exists, reusing"; return; }
  command -v coreos-installer >/dev/null || die "coreos-installer not installed"
  log "downloading Fedora CoreOS (${FCOS_STREAM}) qcow2..."
  coreos-installer download -s "${FCOS_STREAM}" -p qemu -f qcow2.xz \
    --decompress -C "${WORKDIR}" >/tmp/fcos-dl.txt
  mv "$(tail -1 /tmp/fcos-dl.txt)" "${DISK}"
  qemu-img resize "${DISK}" 20G
}

build_bootc_disk() {
  [ -f "${DISK}" ] && { log "disk ${DISK} exists, reusing"; return; }
  command -v podman >/dev/null || die "podman not installed (needed for bootc)"
  [ -n "${SSH_PUBKEY}" ] || die "no SSH public key found in ~/.ssh"
  log "building bootc qcow2 from ${BOOTC_IMAGE} via bootc-image-builder..."
  local cfg="${WORKDIR}/${VM_NAME}-bib.toml"
  cat > "${cfg}" <<EOF
[[customizations.user]]
name = "${VM_USER}"
groups = ["wheel"]
key = "${SSH_PUBKEY}"
EOF
  sudo podman pull "${BOOTC_IMAGE}"
  sudo podman run --rm -it --privileged --pull=newer \
    --security-opt label=type:unconfined_t \
    -v "${WORKDIR}:/output" \
    -v "${cfg}:/config.toml:ro" \
    quay.io/centos-bootc/bootc-image-builder:latest \
    --type qcow2 --config /config.toml "${BOOTC_IMAGE}"
  mv "${WORKDIR}/qcow2/disk.qcow2" "${DISK}"
  qemu-img resize "${DISK}" 20G
  log "NOTE: for the bootc backend, bake sysmanage-agent into ${BOOTC_IMAGE}"
  log "      (Containerfile: RUN dnf -y install sysmanage-agent) before building."
}

# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------
do_start() {
  virsh dominfo "${VM_NAME}" >/dev/null 2>&1 && die "${VM_NAME} already defined (run stop first)"
  mkdir -p "${WORKDIR}"
  if [ "${BACKEND}" = "rpm-ostree" ]; then
    download_fcos
    write_butane
    log "creating FCOS VM ${VM_NAME} (Ignition)..."
    virt-install --name "${VM_NAME}" --vcpus 2 --memory 2048 \
      --os-variant fedora-coreos-stable \
      --import --disk "path=${DISK},format=qcow2" \
      --network "$(net_arg)" \
      --qemu-commandline="-fw_cfg name=opt/com.coreos/config,file=${IGN}" \
      --graphics none --noautoconsole
  else
    build_bootc_disk
    log "creating bootc VM ${VM_NAME}..."
    virt-install --name "${VM_NAME}" --vcpus 2 --memory 2048 \
      --os-variant fedora-eln \
      --import --disk "path=${DISK},format=qcow2" \
      --network "$(net_arg)" \
      --graphics none --noautoconsole
  fi
  log "started. Watch it boot:  virsh console ${VM_NAME}"
  log "Then:  scripts/buildImageModeTestVM.sh status ${BACKEND}"
}

do_stop() {
  virsh destroy "${VM_NAME}" >/dev/null 2>&1 || true
  virsh undefine "${VM_NAME}" --nvram >/dev/null 2>&1 || true
  rm -f "${DISK}" "${IGN}" "${WORKDIR}/${VM_NAME}.bu" "${WORKDIR}/${VM_NAME}-bib.toml"
  log "stopped + cleaned ${VM_NAME}"
}

vm_ip() {
  virsh domifaddr "${VM_NAME}" 2>/dev/null | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1
}

do_status() {
  virsh dominfo "${VM_NAME}" 2>/dev/null || { log "${VM_NAME} not defined"; return; }
  local ip; ip="$(vm_ip)"
  log "IP: ${ip:-<none yet>}"
  if [ -n "${ip}" ]; then
    log "Check image-mode state:"
    if [ "${BACKEND}" = "rpm-ostree" ]; then
      echo "    ssh ${VM_USER}@${ip} rpm-ostree status"
    else
      echo "    ssh ${VM_USER}@${ip} bootc status --json | jq .status.booted.image"
    fi
    log "Validate the spike parser against the live host:"
    echo "    ssh ${VM_USER}@${ip} python3 - < ../sysmanage-professional-plus/scripts/image_mode_spike.py --live"
  fi
}

do_ssh() {
  local ip; ip="$(vm_ip)"
  [ -n "${ip}" ] || die "no IP for ${VM_NAME} yet"
  exec ssh "${VM_USER}@${ip}"
}

case "${1:-}" in
  start)  do_start ;;
  stop)   do_stop ;;
  status) do_status ;;
  ssh)    do_ssh ;;
  *) echo "usage: $0 {start|stop|status|ssh} [rpm-ostree|bootc]" >&2; exit 2 ;;
esac
