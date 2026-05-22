#!/usr/bin/env bash
# buildAirGapTestNetwork.sh — Provision three KVM VMs for sysmanage air-gap
# testing on libvirt/KVM.
#
#   sysmanage-online        — NAT'd, internet-accessible.  The "online"
#                             sysmanage server you point at the real
#                             internet to mirror upstream package repos
#                             or build ISOs for the air-gap side.
#   sysmanage-airgap        — Static 10.60.0.1 on an isolated private
#                             bridge.  No internet.  Carries an extra
#                             empty virtual DVD device so you can mount
#                             ISOs you build on the online VM and move
#                             data across the air gap.
#   sysmanage-private-agent — Static 10.60.0.2 on the same isolated
#                             bridge.  No internet.  For sysmanage-agent.
#
# Usage:
#   scripts/buildAirGapTestNetwork.sh start    # create + start (idempotent)
#   scripts/buildAirGapTestNetwork.sh stop     # destroy + undefine + delete disks
#   scripts/buildAirGapTestNetwork.sh status   # show VM/network state + IPs
#
# Uses the Ubuntu 26.04 server cloud image + cloud-init.  Does NOT install
# sysmanage or sysmanage-agent — that's your job after the VMs come up.
#
# All three VMs share credentials:
#   user     = ubuntu
#   password = Ubuntu123$
#
# Requirements on the host:
#   sudo apt install libvirt-clients libvirt-daemon-system virtinst \
#                    qemu-utils qemu-system-x86 cloud-image-utils curl
#
# Resource sizing is deliberately small:
#   online        : 2 vCPU / 2 GiB RAM / 16 GiB disk
#   airgap        : 2 vCPU / 2 GiB RAM / 24 GiB disk  (extra room for staged ISOs)
#   private-agent : 1 vCPU / 1 GiB RAM / 10 GiB disk
# Bump via environment variables (see top of script) if 2 GiB ends up
# tight when you run the full sysmanage stack with postgres + OpenBAO.

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

# Isolated bridge for the air-gap network.  The host gets an IP on this
# bridge so you can SSH from the host into the airgap/agent VMs even
# though they can't reach the outside world.
PRIVATE_NET_NAME="${PRIVATE_NET_NAME:-sysmanage-private}"
PRIVATE_NET_BRIDGE="${PRIVATE_NET_BRIDGE:-virbr60}"
PRIVATE_NET_HOST_IP="${PRIVATE_NET_HOST_IP:-10.60.0.254}"
PRIVATE_NET_MASK="${PRIVATE_NET_MASK:-255.255.255.0}"

ONLINE_NAME="${ONLINE_NAME:-sysmanage-online}"
ONLINE_VCPUS="${ONLINE_VCPUS:-2}"
ONLINE_RAM="${ONLINE_RAM:-2048}"
ONLINE_DISK_GB="${ONLINE_DISK_GB:-16}"
ONLINE_MAC="${ONLINE_MAC:-52:54:00:60:50:00}"

AIRGAP_NAME="${AIRGAP_NAME:-sysmanage-airgap}"
AIRGAP_VCPUS="${AIRGAP_VCPUS:-2}"
AIRGAP_RAM="${AIRGAP_RAM:-2048}"
AIRGAP_DISK_GB="${AIRGAP_DISK_GB:-24}"
AIRGAP_MAC="${AIRGAP_MAC:-52:54:00:60:00:01}"
AIRGAP_IP="${AIRGAP_IP:-10.60.0.1}"

AGENT_NAME="${AGENT_NAME:-sysmanage-private-agent}"
AGENT_VCPUS="${AGENT_VCPUS:-1}"
AGENT_RAM="${AGENT_RAM:-1024}"
AGENT_DISK_GB="${AGENT_DISK_GB:-10}"
AGENT_MAC="${AGENT_MAC:-52:54:00:60:00:02}"
AGENT_IP="${AGENT_IP:-10.60.0.2}"

VM_NAMES=("$ONLINE_NAME" "$AIRGAP_NAME" "$AGENT_NAME")

WORKDIR="$(mktemp -d -t sysmanage-airgap-XXXXXX)"
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

ensure_private_network() {
  if virsh_ net-info "$PRIVATE_NET_NAME" >/dev/null 2>&1; then
    log "network $PRIVATE_NET_NAME: already defined"
  else
    log "network $PRIVATE_NET_NAME: defining isolated bridge $PRIVATE_NET_BRIDGE"
    local xml="$WORKDIR/${PRIVATE_NET_NAME}.xml"
    cat > "$xml" <<EOF
<network>
  <name>${PRIVATE_NET_NAME}</name>
  <bridge name='${PRIVATE_NET_BRIDGE}' stp='on' delay='0'/>
  <ip address='${PRIVATE_NET_HOST_IP}' netmask='${PRIVATE_NET_MASK}'/>
</network>
EOF
    virsh_ net-define "$xml" >/dev/null
  fi
  net_is_active    "$PRIVATE_NET_NAME" || virsh_ net-start     "$PRIVATE_NET_NAME" >/dev/null
  net_is_autostart "$PRIVATE_NET_NAME" || virsh_ net-autostart "$PRIVATE_NET_NAME" >/dev/null
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

# $1: "dhcp" or a static /24 IPv4 (no CIDR — appended).
# $2: MAC to match.  $3: output file.
write_network_config() {
  local mode="$1" mac="$2" out="$3"
  if [[ "$mode" == "dhcp" ]]; then
    cat > "$out" <<EOF
version: 2
ethernets:
  primary:
    match:
      macaddress: "${mac}"
    set-name: eth0
    dhcp4: true
EOF
  else
    cat > "$out" <<EOF
version: 2
ethernets:
  primary:
    match:
      macaddress: "${mac}"
    set-name: eth0
    dhcp4: false
    addresses:
      - ${mode}/24
EOF
  fi
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

# provision_vm <name> <vcpus> <ram> <disk_gb> <mac> <net_mode>
#              <virt_install_network_arg> <extra_cdrom yes|no>
provision_vm() {
  local name="$1" vcpus="$2" ram="$3" disk_gb="$4" mac="$5"
  local net_mode="$6" virt_net="$7" extra_cdrom="$8"

  local ud="$WORKDIR/${name}-user-data"
  local md="$WORKDIR/${name}-meta-data"
  local nc="$WORKDIR/${name}-network-config"
  write_user_data    "$name"     "$ud"
  write_meta_data    "$name"     "$md"
  write_network_config "$net_mode" "$mac" "$nc"

  local seed_path="${IMG_POOL}/${name}-seed.iso"
  build_seed_iso "$ud" "$md" "$nc" "$seed_path"

  local disk_path="${IMG_POOL}/${name}.qcow2"
  create_disk "$disk_path" "$disk_gb"

  local cdrom_args=( --disk "path=${seed_path},device=cdrom,bus=sata" )
  if [[ "$extra_cdrom" == "yes" ]]; then
    cdrom_args+=( --disk "device=cdrom,bus=sata" )
  fi

  log "Defining $name (vcpus=$vcpus ram=${ram}M disk=${disk_gb}G mac=$mac)"
  virt_install_ --connect "$LIBVIRT_URI" \
    --name "$name" \
    --vcpus "$vcpus" \
    --memory "$ram" \
    --osinfo "$OS_VARIANT" \
    --disk "path=${disk_path},format=qcow2,bus=virtio" \
    "${cdrom_args[@]}" \
    --network "$virt_net" \
    --graphics none \
    --console pty,target_type=serial \
    --noautoconsole \
    --import
}

create_online() {
  provision_vm "$ONLINE_NAME" "$ONLINE_VCPUS" "$ONLINE_RAM" "$ONLINE_DISK_GB" \
    "$ONLINE_MAC" "dhcp" \
    "network=default,model=virtio,mac=${ONLINE_MAC}" \
    "no"
}
create_airgap() {
  provision_vm "$AIRGAP_NAME" "$AIRGAP_VCPUS" "$AIRGAP_RAM" "$AIRGAP_DISK_GB" \
    "$AIRGAP_MAC" "$AIRGAP_IP" \
    "network=${PRIVATE_NET_NAME},model=virtio,mac=${AIRGAP_MAC}" \
    "yes"
}
create_agent() {
  provision_vm "$AGENT_NAME" "$AGENT_VCPUS" "$AGENT_RAM" "$AGENT_DISK_GB" \
    "$AGENT_MAC" "$AGENT_IP" \
    "network=${PRIVATE_NET_NAME},model=virtio,mac=${AGENT_MAC}" \
    "no"
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

# get_nat_ip <vm>  — returns the DHCP-assigned IP (no CIDR) on the NAT NIC,
# empty string if not yet known.  Does NOT wait — call after the post-start
# settle sleep.
get_nat_ip() {
  local name="$1"
  virsh_ domifaddr "$name" --source lease 2>/dev/null \
    | awk '/ipv4/ {print $4}' | head -1 | sed 's|/.*||'
}

# print_vm_summary <name> <role> [<label:ip> ...]
# role drives the install hint line.
print_vm_summary() {
  local name="$1" role="$2"; shift 2
  echo "$name  (state: $(vm_state "$name"))"
  echo "  console : virsh -c ${LIBVIRT_URI} console ${name}    (Ctrl-] to exit)"
  local ip_spec label ip
  for ip_spec in "$@"; do
    IFS=':' read -r label ip <<< "$ip_spec"
    printf '  %-7s : %s\n' "$label" "$ip"
  done
  case "$role" in
    server-online)
      local nat
      nat="$(get_nat_ip "$name")"
      if [[ -n "$nat" ]]; then
        echo "  NAT     : $nat"
      else
        echo "  NAT     : (pending — re-run with the status subcommand once cloud-init finishes)"
      fi
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage"
      ;;
    server-airgap|agent-airgap)
      echo "  install : (no internet by design — install via offline ISO"
      echo "             you build on ${ONLINE_NAME} and mount on this VM)"
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
  ensure_private_network
  ensure_base_image

  ensure_vm "$ONLINE_NAME" create_online
  ensure_vm "$AIRGAP_NAME" create_airgap
  ensure_vm "$AGENT_NAME"  create_agent

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
  print_vm_summary "$ONLINE_NAME" "server-online"
  print_vm_summary "$AIRGAP_NAME" "server-airgap" "private:${AIRGAP_IP}"
  print_vm_summary "$AGENT_NAME"  "agent-airgap"  "private:${AGENT_IP}"

  echo "Default login (all VMs):"
  echo "  user     = ${USERNAME}"
  echo "  password = ${PASSWORD}"
  echo
  echo "Mount an ISO into the air-gap server's virtual DVD:"
  echo "  virsh -c ${LIBVIRT_URI} domblklist ${AIRGAP_NAME}    # find empty cdrom target"
  echo "  virsh -c ${LIBVIRT_URI} change-media ${AIRGAP_NAME} <target> /path/to/your.iso --update --live"
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
      virsh_ undefine "$name" --remove-all-storage --nvram >/dev/null 2>&1 \
        || virsh_ undefine "$name" --remove-all-storage >/dev/null 2>&1 \
        || true
    else
      log "$name: not defined — skipping"
    fi
  done

  if virsh_ net-info "$PRIVATE_NET_NAME" >/dev/null 2>&1; then
    if net_is_active "$PRIVATE_NET_NAME"; then
      virsh_ net-destroy "$PRIVATE_NET_NAME" >/dev/null 2>&1 || true
    fi
    virsh_ net-undefine "$PRIVATE_NET_NAME" >/dev/null 2>&1 || true
    log "network $PRIVATE_NET_NAME: removed"
  fi

  log ""
  log "Base cloud image kept at $BASE_IMG (re-used by 'start')."
  log "Delete it manually with:  sudo rm $BASE_IMG"
}

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
  for net in default "$PRIVATE_NET_NAME"; do
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
  # The online VM only has a NAT NIC, so it has no static-IP rows.
  print_vm_status "$ONLINE_NAME"
  print_vm_status "$AIRGAP_NAME" "private:${AIRGAP_IP}"
  print_vm_status "$AGENT_NAME"  "private:${AGENT_IP}"

  echo
  echo "Credentials: user=${USERNAME}  password=${PASSWORD}"
}

usage() {
  cat <<EOF
Usage: $0 {start|stop|status}

  start   Create and start the three VMs (idempotent — already-running
          VMs are reported, not re-created).
  stop    Destroy all three VMs, delete their disks and seed ISOs, and
          tear down the ${PRIVATE_NET_NAME} isolated network.  The Ubuntu
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
