#!/usr/bin/env bash
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# buildTieredNetwork.sh — Provision a 5-VM federated sysmanage test fabric
# on libvirt/KVM.
#
# Topology (all five VMs also get a NAT NIC for internet access — no
# air gap here):
#
#   sysmanage-enterprise        — coordinator / "tier 0" server.  Has one
#     vCPU/RAM/disk: 2/2GiB/16GiB    interface on every private tier so it
#                                    can reach every site directly.
#     NICs: NAT + tier0 (10.70.0.1)
#                + tier1 (10.70.1.254)
#                + tier2 (10.70.2.254)
#
#   sysmanage-site-1            — subordinate sysmanage server for site 1.
#     NICs: NAT + tier1 (10.70.1.1)
#   sysmanage-site-1-agent      — agent on the site-1 fabric.
#     NICs: NAT + tier1 (10.70.1.2)
#
#   sysmanage-site-2            — subordinate sysmanage server for site 2.
#     NICs: NAT + tier2 (10.70.2.1)
#   sysmanage-site-2-agent      — agent on the site-2 fabric.
#     NICs: NAT + tier2 (10.70.2.2)
#
# The tier1 / tier2 libvirt networks are isolated — site-1 cannot see
# site-2 (and vice versa) over those segments.  Both can still reach the
# internet via their NAT NIC, and the enterprise VM can reach every
# tier because it is multi-homed.
#
# Usage:
#   scripts/buildTieredNetwork.sh start    # create + start (idempotent)
#   scripts/buildTieredNetwork.sh stop     # destroy + undefine + delete disks
#   scripts/buildTieredNetwork.sh status   # show VM/network state + IPs
#
# Does NOT install sysmanage on the VMs.  Default ubuntu/Ubuntu123$ user.
#
# Requirements:
#   sudo apt install libvirt-clients libvirt-daemon-system virtinst \
#                    qemu-utils qemu-system-x86 cloud-image-utils curl

set -euo pipefail

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

UBUNTU_VERSION="${UBUNTU_VERSION:-26.04}"
CLOUD_IMG_URL="${CLOUD_IMG_URL:-https://cloud-images.ubuntu.com/releases/${UBUNTU_VERSION}/release/ubuntu-${UBUNTU_VERSION}-server-cloudimg-amd64.img}"
IMG_POOL="${IMG_POOL:-/var/lib/libvirt/images}"
BASE_IMG="${IMG_POOL}/ubuntu-${UBUNTU_VERSION}-server-cloudimg-amd64.img"
LIBVIRT_URI="${LIBVIRT_URI:-qemu:///system}"
OS_VARIANT="${OS_VARIANT:-ubuntu24.04}"

USERNAME="ubuntu"
PASSWORD='Ubuntu123$'

# Isolated tier networks.  No <forward>, no host IP — pure VM-to-VM
# segments.  Inter-tier reachability is provided by enterprise being
# multi-homed across all three.
TIER0_NET="sysmanage-tier0"; TIER0_BRIDGE="virbr70"
TIER1_NET="sysmanage-tier1"; TIER1_BRIDGE="virbr71"
TIER2_NET="sysmanage-tier2"; TIER2_BRIDGE="virbr72"

# VM specs — kept as small as Ubuntu 26.04 server will actually run.
# Enterprise + subordinate servers need to host postgres + sysmanage,
# so 2 vCPU / 2 GiB.  Agents are lighter (1 vCPU / 1 GiB).
ENTERPRISE_NAME="sysmanage-enterprise"
ENT_VCPUS=2; ENT_RAM=2048; ENT_DISK_GB=16
ENT_MAC_NAT="52:54:00:70:00:fe"
ENT_MAC_TIER0="52:54:00:70:00:01"
ENT_MAC_TIER1="52:54:00:70:01:fe"
ENT_MAC_TIER2="52:54:00:70:02:fe"
ENT_IP_TIER0="10.70.0.1"
ENT_IP_TIER1="10.70.1.254"
ENT_IP_TIER2="10.70.2.254"

SITE1_NAME="sysmanage-site-1"
S1_VCPUS=2; S1_RAM=2048; S1_DISK_GB=16
S1_MAC_NAT="52:54:00:70:01:fa"
S1_MAC_TIER1="52:54:00:70:01:01"
S1_IP="10.70.1.1"

SITE1_AGENT_NAME="sysmanage-site-1-agent"
S1A_VCPUS=1; S1A_RAM=1024; S1A_DISK_GB=10
S1A_MAC_NAT="52:54:00:70:01:fb"
S1A_MAC_TIER1="52:54:00:70:01:02"
S1A_IP="10.70.1.2"

SITE2_NAME="sysmanage-site-2"
S2_VCPUS=2; S2_RAM=2048; S2_DISK_GB=16
S2_MAC_NAT="52:54:00:70:02:fa"
S2_MAC_TIER2="52:54:00:70:02:01"
S2_IP="10.70.2.1"

SITE2_AGENT_NAME="sysmanage-site-2-agent"
S2A_VCPUS=1; S2A_RAM=1024; S2A_DISK_GB=10
S2A_MAC_NAT="52:54:00:70:02:fb"
S2A_MAC_TIER2="52:54:00:70:02:02"
S2A_IP="10.70.2.2"

VM_NAMES=(
  "$ENTERPRISE_NAME"
  "$SITE1_NAME" "$SITE1_AGENT_NAME"
  "$SITE2_NAME" "$SITE2_AGENT_NAME"
)
TIER_NETS=("$TIER0_NET" "$TIER1_NET" "$TIER2_NET")
TIER_NET_BRIDGES=(
  "${TIER0_NET}:${TIER0_BRIDGE}"
  "${TIER1_NET}:${TIER1_BRIDGE}"
  "${TIER2_NET}:${TIER2_BRIDGE}"
)

WORKDIR="$(mktemp -d -t sysmanage-tiered-XXXXXX)"
trap 'rm -rf "$WORKDIR"' EXIT

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

# Force C locale so we can grep virsh output for English strings ("yes",
# "running", etc.) regardless of the user's $LANG.
virsh_() { LC_ALL=C virsh -c "$LIBVIRT_URI" "$@"; }

net_is_active()    { virsh_ net-list --name 2>/dev/null | grep -qFx "$1"; }
net_is_autostart() { virsh_ net-info "$1" 2>/dev/null | grep -qE '^Autostart:[[:space:]]+yes$'; }

# virt-install ships with `#!/usr/bin/env python3`, which inside an active
# venv resolves to the venv's gi-less interpreter.  Invoke through the
# system Python explicitly so the shebang's PATH lookup is bypassed.
SYS_PYTHON3="${SYS_PYTHON3:-/usr/bin/python3}"
virt_install_() {
  local vi
  vi="$(command -v virt-install)" \
    || die "virt-install not found on PATH"
  "$SYS_PYTHON3" "$vi" "$@"
}

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

check_deps() {
  local missing=()
  for cmd in virsh virt-install qemu-img cloud-localds curl; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if (( ${#missing[@]} > 0 )); then
    die "Missing required tools: ${missing[*]}
Install with:
  sudo apt install libvirt-clients libvirt-daemon-system virtinst \\
                   qemu-utils qemu-system-x86 cloud-image-utils curl python3-gi"
  fi
  virsh_ list >/dev/null 2>&1 || die "Cannot talk to libvirt at $LIBVIRT_URI.
Add yourself to the libvirt group and re-login:  sudo usermod -aG libvirt \$USER"

  # virt-install's virtinst package imports gi (PyGObject) at module load,
  # even in CLI mode.  We invoke virt-install through $SYS_PYTHON3 below
  # to dodge the venv issue (virt-install's shebang is
  # `#!/usr/bin/env python3`, which inside a venv resolves to a gi-less
  # interpreter), so test gi against the same system interpreter here.
  if [[ ! -x "$SYS_PYTHON3" ]]; then
    die "System Python not found at $SYS_PYTHON3.  Override with SYS_PYTHON3=<path>."
  fi
  if ! "$SYS_PYTHON3" -c 'import gi' >/dev/null 2>&1; then
    die "$SYS_PYTHON3 can't import the 'gi' (PyGObject) module.
Install it with:  sudo apt install python3-gi"
  fi
}

# ---------------------------------------------------------------------------
# Network + image setup
# ---------------------------------------------------------------------------

ensure_default_network() {
  virsh_ net-info default >/dev/null 2>&1 \
    || die "libvirt 'default' NAT network is missing.  Define it or restore it from /usr/share/libvirt/networks/default.xml."
  if net_is_active default; then
    log "network default: already active"
  else
    log "network default: starting"
    virsh_ net-start default >/dev/null
  fi
}

ensure_isolated_network() {
  local name="$1" bridge="$2"
  if virsh_ net-info "$name" >/dev/null 2>&1; then
    log "network $name: already defined"
  else
    log "network $name: defining isolated bridge $bridge"
    local xml="$WORKDIR/${name}.xml"
    cat > "$xml" <<EOF
<network>
  <name>${name}</name>
  <bridge name='${bridge}' stp='on' delay='0'/>
</network>
EOF
    virsh_ net-define "$xml" >/dev/null
  fi
  net_is_active    "$name" || virsh_ net-start     "$name" >/dev/null
  net_is_autostart "$name" || virsh_ net-autostart "$name" >/dev/null
}

ensure_base_image() {
  if [[ -f "$BASE_IMG" ]]; then
    log "base image: $BASE_IMG (already present)"
    return
  fi
  log "Downloading Ubuntu ${UBUNTU_VERSION} cloud image..."
  log "  -> $CLOUD_IMG_URL"
  sudo mkdir -p "$IMG_POOL"
  sudo curl -fL --output "$BASE_IMG" "$CLOUD_IMG_URL"
  sudo chmod 644 "$BASE_IMG"
}

# ---------------------------------------------------------------------------
# cloud-init authoring
# ---------------------------------------------------------------------------

write_user_data() {
  local host="$1" out="$2"
  cat > "$out" <<EOF
#cloud-config
hostname: ${host}
fqdn: ${host}
manage_etc_hosts: true
ssh_pwauth: true
disable_root: false
package_update: false
package_upgrade: false
users:
  - default
  - name: ${USERNAME}
    lock_passwd: false
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    groups: [adm, sudo]
chpasswd:
  expire: false
  users:
    - name: ${USERNAME}
      password: '${PASSWORD}'
      type: text
runcmd:
  - systemctl enable --now ssh
EOF
}

write_meta_data() {
  local host="$1" out="$2"
  cat > "$out" <<EOF
instance-id: iid-${host}
local-hostname: ${host}
EOF
}

# write_network_config <out> <nic_spec> [<nic_spec> ...]
#   nic_spec is "<libvirt_net>:<mode>:<mac>" where mode is "dhcp" or a
#   /24 IPv4 like "10.70.1.1".  The label assigned to each NIC in the
#   cloud-init file is nic0/nic1/... and they're forced to eth0/eth1/...
#   so the user sees stable names regardless of the kernel's
#   predictable-naming output.
write_network_config() {
  local out="$1"; shift
  {
    echo "version: 2"
    echo "ethernets:"
    local idx=0
    for spec in "$@"; do
      IFS=':' read -r _lvnet mode mac <<< "$spec"
      echo "  nic${idx}:"
      echo "    match:"
      echo "      macaddress: \"${mac}\""
      echo "    set-name: eth${idx}"
      if [[ "$mode" == "dhcp" ]]; then
        echo "    dhcp4: true"
      else
        echo "    dhcp4: false"
        echo "    addresses:"
        echo "      - ${mode}/24"
      fi
      idx=$((idx+1))
    done
  } > "$out"
}

build_seed_iso() {
  local user_data="$1" meta_data="$2" network_config="$3" out="$4"
  local tmp="$WORKDIR/$(basename "$out")"
  cloud-localds --network-config "$network_config" "$tmp" "$user_data" "$meta_data"
  sudo cp "$tmp" "$out"
  sudo chmod 644 "$out"
}

create_disk() {
  local out="$1" size_gb="$2"
  sudo qemu-img create -f qcow2 -F qcow2 \
       -b "$BASE_IMG" "$out" "${size_gb}G" >/dev/null
  sudo chmod 644 "$out"
}

# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------

# provision_vm <name> <vcpus> <ram> <disk_gb> <nic_spec>...
provision_vm() {
  local name="$1" vcpus="$2" ram="$3" disk_gb="$4"
  shift 4
  local nics=("$@")

  local ud="$WORKDIR/${name}-user-data"
  local md="$WORKDIR/${name}-meta-data"
  local nc="$WORKDIR/${name}-network-config"
  write_user_data    "$name" "$ud"
  write_meta_data    "$name" "$md"
  write_network_config "$nc" "${nics[@]}"

  local seed_path="${IMG_POOL}/${name}-seed.iso"
  build_seed_iso "$ud" "$md" "$nc" "$seed_path"

  local disk_path="${IMG_POOL}/${name}.qcow2"
  create_disk "$disk_path" "$disk_gb"

  local net_args=()
  for spec in "${nics[@]}"; do
    IFS=':' read -r lvnet _mode mac <<< "$spec"
    net_args+=( --network "network=${lvnet},model=virtio,mac=${mac}" )
  done

  log "Defining $name (vcpus=$vcpus ram=${ram}M disk=${disk_gb}G nics=${#nics[@]})"
  virt_install_ --connect "$LIBVIRT_URI" \
    --name "$name" \
    --vcpus "$vcpus" \
    --memory "$ram" \
    --osinfo "$OS_VARIANT" \
    --disk "path=${disk_path},format=qcow2,bus=virtio" \
    --disk "path=${seed_path},device=cdrom,bus=sata" \
    "${net_args[@]}" \
    --graphics none \
    --console pty,target_type=serial \
    --noautoconsole \
    --import
}

create_enterprise() {
  provision_vm "$ENTERPRISE_NAME" "$ENT_VCPUS" "$ENT_RAM" "$ENT_DISK_GB" \
    "default:dhcp:${ENT_MAC_NAT}" \
    "${TIER0_NET}:${ENT_IP_TIER0}:${ENT_MAC_TIER0}" \
    "${TIER1_NET}:${ENT_IP_TIER1}:${ENT_MAC_TIER1}" \
    "${TIER2_NET}:${ENT_IP_TIER2}:${ENT_MAC_TIER2}"
}
create_site1() {
  provision_vm "$SITE1_NAME" "$S1_VCPUS" "$S1_RAM" "$S1_DISK_GB" \
    "default:dhcp:${S1_MAC_NAT}" \
    "${TIER1_NET}:${S1_IP}:${S1_MAC_TIER1}"
}
create_site1_agent() {
  provision_vm "$SITE1_AGENT_NAME" "$S1A_VCPUS" "$S1A_RAM" "$S1A_DISK_GB" \
    "default:dhcp:${S1A_MAC_NAT}" \
    "${TIER1_NET}:${S1A_IP}:${S1A_MAC_TIER1}"
}
create_site2() {
  provision_vm "$SITE2_NAME" "$S2_VCPUS" "$S2_RAM" "$S2_DISK_GB" \
    "default:dhcp:${S2_MAC_NAT}" \
    "${TIER2_NET}:${S2_IP}:${S2_MAC_TIER2}"
}
create_site2_agent() {
  provision_vm "$SITE2_AGENT_NAME" "$S2A_VCPUS" "$S2A_RAM" "$S2A_DISK_GB" \
    "default:dhcp:${S2A_MAC_NAT}" \
    "${TIER2_NET}:${S2A_IP}:${S2A_MAC_TIER2}"
}

# ---------------------------------------------------------------------------
# Idempotent VM lifecycle
# ---------------------------------------------------------------------------

vm_exists()  { virsh_ dominfo "$1" >/dev/null 2>&1; }
vm_state()   { virsh_ domstate "$1" 2>/dev/null || echo "absent"; }
vm_running() { [[ "$(vm_state "$1")" == "running" ]]; }

CREATED_COUNT=0

ensure_vm() {
  local name="$1" create_fn="$2"
  if vm_exists "$name"; then
    if vm_running "$name"; then
      log "$name: already running"
    else
      log "$name: defined but stopped — starting"
      virsh_ start "$name" >/dev/null
      CREATED_COUNT=$((CREATED_COUNT + 1))
    fi
  else
    log "$name: not defined — creating"
    "$create_fn"
    CREATED_COUNT=$((CREATED_COUNT + 1))
  fi
}

# Look up the DHCP-assigned IP on the NAT NIC; empty if not (yet) known.
get_nat_ip() {
  local name="$1"
  virsh_ domifaddr "$name" --source lease 2>/dev/null \
    | awk '/ipv4/ {print $4}' | head -1 | sed 's|/.*||'
}

# print_vm_summary <name> <role> [<label:ip> ...]
#   role is one of: server | agent
print_vm_summary() {
  local name="$1" role="$2"; shift 2
  echo "$name  (state: $(vm_state "$name"))"
  echo "  console : virsh -c ${LIBVIRT_URI} console ${name}    (Ctrl-] to exit)"
  local ip_spec label ip
  for ip_spec in "$@"; do
    IFS=':' read -r label ip <<< "$ip_spec"
    printf '  %-7s : %s\n' "$label" "$ip"
  done
  local nat
  nat="$(get_nat_ip "$name")"
  if [[ -n "$nat" ]]; then
    echo "  NAT     : $nat"
  else
    echo "  NAT     : (pending — re-run with the status subcommand once cloud-init finishes)"
  fi
  case "$role" in
    server)
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage"
      ;;
    agent)
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage-agent \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage-agent"
      ;;
  esac
  echo
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_start() {
  check_deps
  log "Workspace        : $WORKDIR"
  log "libvirt image pool: $IMG_POOL"
  log "libvirt URI       : $LIBVIRT_URI"

  ensure_default_network
  for pair in "${TIER_NET_BRIDGES[@]}"; do
    IFS=':' read -r net bridge <<< "$pair"
    ensure_isolated_network "$net" "$bridge"
  done

  ensure_base_image

  ensure_vm "$ENTERPRISE_NAME"   create_enterprise
  ensure_vm "$SITE1_NAME"        create_site1
  ensure_vm "$SITE1_AGENT_NAME"  create_site1_agent
  ensure_vm "$SITE2_NAME"        create_site2
  ensure_vm "$SITE2_AGENT_NAME"  create_site2_agent

  if (( CREATED_COUNT > 0 )); then
    log ""
    log "Waiting 30s for cloud-init + DHCP leases to settle..."
    sleep 30
  fi

  echo
  echo "=========================================="
  echo "  Post-start summary"
  echo "=========================================="
  echo
  print_vm_summary "$ENTERPRISE_NAME"   "server" \
    "tier0:${ENT_IP_TIER0}" "tier1:${ENT_IP_TIER1}" "tier2:${ENT_IP_TIER2}"
  print_vm_summary "$SITE1_NAME"        "server" "tier1:${S1_IP}"
  print_vm_summary "$SITE1_AGENT_NAME"  "agent"  "tier1:${S1A_IP}"
  print_vm_summary "$SITE2_NAME"        "server" "tier2:${S2_IP}"
  print_vm_summary "$SITE2_AGENT_NAME"  "agent"  "tier2:${S2A_IP}"

  echo "Default login (all VMs):"
  echo "  user     = ${USERNAME}"
  echo "  password = ${PASSWORD}"
  echo
  echo "sysmanage UI login — when you configure /etc/sysmanage.yaml on the server(s):"
  echo "  - security.admin_userid MUST be a valid EMAIL (login validates EmailStr;"
  echo "    a bare 'admin' -> HTTP 422, not 401). e.g. admin@example.com / admin"
  echo "  - email.enabled: true  (just the flag — no SMTP server/password needed)."
  echo
  echo "Re-check status :  $0 status"
  echo "Tear everything :  $0 stop"
}

cmd_stop() {
  check_deps
  for name in "${VM_NAMES[@]}"; do
    if vm_exists "$name"; then
      if vm_running "$name"; then
        log "$name: destroying"
        virsh_ destroy "$name" >/dev/null || true
      fi
      log "$name: undefining (removing disks)"
      # --nvram is only valid when an NVRAM file exists; ignore if not.
      virsh_ undefine "$name" --remove-all-storage --nvram >/dev/null 2>&1 \
        || virsh_ undefine "$name" --remove-all-storage >/dev/null 2>&1 \
        || true
    else
      log "$name: not defined — skipping"
    fi
  done

  for net in "${TIER_NETS[@]}"; do
    if virsh_ net-info "$net" >/dev/null 2>&1; then
      if net_is_active "$net"; then
        virsh_ net-destroy "$net" >/dev/null 2>&1 || true
      fi
      virsh_ net-undefine "$net" >/dev/null 2>&1 || true
      log "network $net: removed"
    fi
  done

  log ""
  log "Base cloud image kept at $BASE_IMG (re-used by 'start')."
  log "Delete it manually with:  sudo rm $BASE_IMG"
}

# print_vm_status <name> <label1:ip1> [<label2:ip2> ...]
print_vm_status() {
  local name="$1"; shift
  if ! vm_exists "$name"; then
    printf "  %-30s %s\n" "$name" "(not defined)"
    return
  fi
  local state
  state="$(vm_state "$name")"
  printf "  %-30s %s\n" "$name" "$state"
  for sp in "$@"; do
    IFS=':' read -r label ip <<< "$sp"
    printf "    %-14s %s\n" "${label}:" "$ip"
  done
  if [[ "$state" == "running" ]]; then
    local nat_ip
    nat_ip="$(virsh_ domifaddr "$name" --source lease 2>/dev/null \
              | awk '/ipv4/ {print $4}' | head -1)"
    if [[ -n "$nat_ip" ]]; then
      printf "    %-14s %s\n" "NAT (DHCP):" "$nat_ip"
    fi
  fi
}

cmd_status() {
  check_deps
  echo "=== Networks ==="
  for net in default "${TIER_NETS[@]}"; do
    if virsh_ net-info "$net" >/dev/null 2>&1; then
      if net_is_active "$net"; then
        printf "  %-30s %s\n" "$net" "active"
      else
        printf "  %-30s %s\n" "$net" "inactive"
      fi
    else
      printf "  %-30s %s\n" "$net" "(not defined)"
    fi
  done

  echo
  echo "=== VMs ==="
  print_vm_status "$ENTERPRISE_NAME" \
    "tier0:${ENT_IP_TIER0}" \
    "tier1:${ENT_IP_TIER1}" \
    "tier2:${ENT_IP_TIER2}"
  print_vm_status "$SITE1_NAME"        "tier1:${S1_IP}"
  print_vm_status "$SITE1_AGENT_NAME"  "tier1:${S1A_IP}"
  print_vm_status "$SITE2_NAME"        "tier2:${S2_IP}"
  print_vm_status "$SITE2_AGENT_NAME"  "tier2:${S2A_IP}"

  echo
  echo "Credentials: user=${USERNAME}  password=${PASSWORD}"
}

usage() {
  cat <<EOF
Usage: $0 {start|stop|status}

  start   Create and start the 5-VM tiered fabric (idempotent — already-
          running VMs are reported, not re-created).
  stop    Destroy all five VMs, delete their disks and seed ISOs, and
          tear down the tier0/tier1/tier2 isolated networks.  The Ubuntu
          base cloud image is kept so a subsequent 'start' is fast.
  status  Show network state and per-VM state + configured static IPs +
          DHCP-assigned NAT IPs.
EOF
}

main() {
  case "${1:-}" in
    start)  cmd_start ;;
    stop)   cmd_stop ;;
    status) cmd_status ;;
    -h|--help|help|"") usage ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
