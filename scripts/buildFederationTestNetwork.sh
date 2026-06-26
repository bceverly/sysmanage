#!/usr/bin/env bash
# buildFederationTestNetwork.sh — Provision four KVM VMs for sysmanage
# multi-site federation testing on libvirt/KVM.
#
#   sysmanage-coordinator — The federation COORDINATOR.  Dual-homed: a
#                           NAT NIC for internet (install sysmanage from
#                           the PPA) plus a static 10.70.0.1 on the
#                           isolated sysmanage-fed bridge.  Set its
#                           Server Role -> Federation card to
#                           "Coordinator" in the UI.
#   sysmanage-site-a      — A subordinate SITE server.  Dual-homed
#                           (internet + static 10.70.0.2).  Enrolls
#                           upstream against the coordinator at
#                           10.70.0.1.  Server Role -> "Site".
#   sysmanage-site-b      — A second SITE server (static 10.70.0.3) so you
#                           can exercise cross-site rollups, the federated
#                           host directory, and per-site command dispatch.
#   sysmanage-fed-agent   — A sysmanage-agent (static 10.70.0.11) that
#                           registers with site-a, so you can test the full
#                           dispatch path: coordinator -> site-a -> agent.
#
# Usage:
#   scripts/buildFederationTestNetwork.sh start    # create + start (idempotent)
#   scripts/buildFederationTestNetwork.sh stop     # destroy + undefine + delete disks
#   scripts/buildFederationTestNetwork.sh status   # show VM/network state + IPs
#
# Uses the Ubuntu 26.04 server cloud image + cloud-init.  Does NOT install
# sysmanage or sysmanage-agent — that's your job after the VMs come up.
#
# All four VMs share credentials:
#   user     = ubuntu
#   password = Ubuntu123$
#
# Requirements on the host:
#   sudo apt install libvirt-clients libvirt-daemon-system virtinst \
#                    qemu-utils qemu-system-x86 cloud-image-utils curl python3-gi
#
# Resource sizing.  Disk sizes are the maximum the VM filesystem can
# grow to — qcow2 is thin-allocated so unused space doesn't actually
# consume host disk.  Defaults are sized for a real end-to-end test:
#   coordinator : 2 vCPU / 4 GiB RAM / 40 GiB disk  (full sysmanage stack:
#                 postgres + OpenBAO + backend + the federation_controller
#                 engine)
#   site-a/b    : 2 vCPU / 4 GiB RAM / 40 GiB disk  (full sysmanage stack +
#                 the federation_site engine)
#   fed-agent   : 1 vCPU / 2 GiB RAM / 20 GiB disk  (OS + agent; 1 GiB OOM'd
#                 the agent during package/update-detection collection)
# Three full server stacks is ~12 GiB of guest RAM; bump/shrink any node via
# the environment variables below if your host is tight.

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

# Isolated bridge for the federation network.  Every VM keeps a NAT NIC
# for internet (so sysmanage installs from the PPA) AND a static NIC on
# this bridge, which gives the nodes stable, known addresses to enroll
# and sync against.  The host gets an IP on the bridge too, so you can SSH
# straight into any node over 10.70.0.x.
FED_NET_NAME="${FED_NET_NAME:-sysmanage-fed}"
FED_NET_BRIDGE="${FED_NET_BRIDGE:-virbr70}"
FED_NET_HOST_IP="${FED_NET_HOST_IP:-10.70.0.254}"
FED_NET_MASK="${FED_NET_MASK:-255.255.255.0}"

COORD_NAME="${COORD_NAME:-sysmanage-coordinator}"
COORD_VCPUS="${COORD_VCPUS:-2}"
COORD_RAM="${COORD_RAM:-4096}"
COORD_DISK_GB="${COORD_DISK_GB:-40}"
COORD_NAT_MAC="${COORD_NAT_MAC:-52:54:00:70:50:00}"
COORD_FED_MAC="${COORD_FED_MAC:-52:54:00:70:00:01}"
COORD_IP="${COORD_IP:-10.70.0.1}"

SITE_A_NAME="${SITE_A_NAME:-sysmanage-site-a}"
SITE_A_VCPUS="${SITE_A_VCPUS:-2}"
SITE_A_RAM="${SITE_A_RAM:-4096}"
SITE_A_DISK_GB="${SITE_A_DISK_GB:-40}"
SITE_A_NAT_MAC="${SITE_A_NAT_MAC:-52:54:00:70:50:01}"
SITE_A_FED_MAC="${SITE_A_FED_MAC:-52:54:00:70:00:02}"
SITE_A_IP="${SITE_A_IP:-10.70.0.2}"

SITE_B_NAME="${SITE_B_NAME:-sysmanage-site-b}"
SITE_B_VCPUS="${SITE_B_VCPUS:-2}"
SITE_B_RAM="${SITE_B_RAM:-4096}"
SITE_B_DISK_GB="${SITE_B_DISK_GB:-40}"
SITE_B_NAT_MAC="${SITE_B_NAT_MAC:-52:54:00:70:50:02}"
SITE_B_FED_MAC="${SITE_B_FED_MAC:-52:54:00:70:00:03}"
SITE_B_IP="${SITE_B_IP:-10.70.0.3}"

AGENT_NAME="${AGENT_NAME:-sysmanage-fed-agent}"
AGENT_VCPUS="${AGENT_VCPUS:-1}"
# 2 GiB: at 1 GiB the agent's Python process OOM-kills in a crash-restart loop
# during its package/update-detection collection (the apt available-package
# universe balloons RSS to ~700 MiB).  Override with AGENT_RAM=<MiB>.
AGENT_RAM="${AGENT_RAM:-2048}"
AGENT_DISK_GB="${AGENT_DISK_GB:-20}"
AGENT_NAT_MAC="${AGENT_NAT_MAC:-52:54:00:70:50:0b}"
AGENT_FED_MAC="${AGENT_FED_MAC:-52:54:00:70:00:0b}"
AGENT_IP="${AGENT_IP:-10.70.0.11}"

VM_NAMES=("$COORD_NAME" "$SITE_A_NAME" "$SITE_B_NAME" "$AGENT_NAME")

WORKDIR="$(mktemp -d -t sysmanage-fed-XXXXXX)"
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

ensure_fed_network() {
  if virsh_ net-info "$FED_NET_NAME" >/dev/null 2>&1; then
    log "network $FED_NET_NAME: already defined"
  else
    log "network $FED_NET_NAME: defining isolated bridge $FED_NET_BRIDGE"
    local xml="$WORKDIR/${FED_NET_NAME}.xml"
    cat > "$xml" <<EOF
<network>
  <name>${FED_NET_NAME}</name>
  <bridge name='${FED_NET_BRIDGE}' stp='on' delay='0'/>
  <ip address='${FED_NET_HOST_IP}' netmask='${FED_NET_MASK}'/>
</network>
EOF
    virsh_ net-define "$xml" >/dev/null
  fi
  net_is_active    "$FED_NET_NAME" || virsh_ net-start     "$FED_NET_NAME" >/dev/null
  net_is_autostart "$FED_NET_NAME" || virsh_ net-autostart "$FED_NET_NAME" >/dev/null
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

# Dual-NIC netplan: eth0 = NAT NIC (DHCP, carries the default route so the
# node has internet), eth1 = federation NIC (static /24 on the isolated
# bridge, no gateway).  Inter-node federation traffic to 10.70.0.x is
# directly connected over eth1; everything else exits via eth0's default
# route.
# $1: NAT MAC.  $2: federation MAC.  $3: federation static IPv4 (no CIDR).
# $4: output file.
write_network_config() {
  local nat_mac="$1" fed_mac="$2" fed_ip="$3" out="$4"
  cat > "$out" <<EOF
version: 2
ethernets:
  nat0:
    match:
      macaddress: "${nat_mac}"
    set-name: eth0
    dhcp4: true
  fed0:
    match:
      macaddress: "${fed_mac}"
    set-name: eth1
    dhcp4: false
    addresses:
      - ${fed_ip}/24
EOF
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

# provision_vm <name> <vcpus> <ram> <disk_gb> <nat_mac> <fed_mac> <fed_ip>
# Every federation node is dual-homed: a NAT NIC for internet + a static
# NIC on the ${FED_NET_NAME} bridge.
provision_vm() {
  local name="$1" vcpus="$2" ram="$3" disk_gb="$4"
  local nat_mac="$5" fed_mac="$6" fed_ip="$7"

  local ud="$WORKDIR/${name}-user-data"
  local md="$WORKDIR/${name}-meta-data"
  local nc="$WORKDIR/${name}-network-config"
  write_user_data    "$name" "$ud"
  write_meta_data    "$name" "$md"
  write_network_config "$nat_mac" "$fed_mac" "$fed_ip" "$nc"

  local seed_path="${IMG_POOL}/${name}-seed.iso"
  build_seed_iso "$ud" "$md" "$nc" "$seed_path"

  local disk_path="${IMG_POOL}/${name}.qcow2"
  create_disk "$disk_path" "$disk_gb"

  log "Defining $name (vcpus=$vcpus ram=${ram}M disk=${disk_gb}G nat=$nat_mac fed=$fed_mac/$fed_ip)"
  virt_install_ --connect "$LIBVIRT_URI" \
    --name "$name" \
    --vcpus "$vcpus" \
    --memory "$ram" \
    --osinfo "$OS_VARIANT" \
    --disk "path=${disk_path},format=qcow2,bus=virtio" \
    --disk "path=${seed_path},device=cdrom,bus=sata" \
    --network "network=default,model=virtio,mac=${nat_mac}" \
    --network "network=${FED_NET_NAME},model=virtio,mac=${fed_mac}" \
    --graphics none \
    --console pty,target_type=serial \
    --noautoconsole \
    --import
}

create_coordinator() {
  provision_vm "$COORD_NAME" "$COORD_VCPUS" "$COORD_RAM" "$COORD_DISK_GB" \
    "$COORD_NAT_MAC" "$COORD_FED_MAC" "$COORD_IP"
}
create_site_a() {
  provision_vm "$SITE_A_NAME" "$SITE_A_VCPUS" "$SITE_A_RAM" "$SITE_A_DISK_GB" \
    "$SITE_A_NAT_MAC" "$SITE_A_FED_MAC" "$SITE_A_IP"
}
create_site_b() {
  provision_vm "$SITE_B_NAME" "$SITE_B_VCPUS" "$SITE_B_RAM" "$SITE_B_DISK_GB" \
    "$SITE_B_NAT_MAC" "$SITE_B_FED_MAC" "$SITE_B_IP"
}
create_agent() {
  provision_vm "$AGENT_NAME" "$AGENT_VCPUS" "$AGENT_RAM" "$AGENT_DISK_GB" \
    "$AGENT_NAT_MAC" "$AGENT_FED_MAC" "$AGENT_IP"
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
# settle sleep.  Filters to the default-network lease so the static
# federation address never shadows the NAT one.
get_nat_ip() {
  local name="$1"
  virsh_ domifaddr "$name" --source lease 2>/dev/null \
    | awk '/ipv4/ {print $4}' | grep -v '^10\.70\.' | head -1 | sed 's|/.*||'
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
  local nat
  nat="$(get_nat_ip "$name")"
  if [[ -n "$nat" ]]; then
    echo "  NAT     : $nat"
  else
    echo "  NAT     : (pending — re-run with the status subcommand once cloud-init finishes)"
  fi
  case "$role" in
    coordinator)
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage"
      echo "  role    : UI -> Settings -> Server Role -> Federation card -> Coordinator,"
      echo "            then Federation -> Sites to enroll site-a / site-b and issue"
      echo "            their enrollment tokens.  Copy this box's federation identity key"
      echo "            (Server Role page) and import it on each site."
      ;;
    site)
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage"
      echo "  role    : UI -> Settings -> Server Role -> Federation card -> Site, paste the"
      echo "            coordinator's identity key + enrollment token, and enroll upstream"
      echo "            against the coordinator at https://${COORD_IP}:<api-port>"
      ;;
    agent)
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage-agent \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage-agent"
      echo "  config  : point /etc/sysmanage-agent.yaml hostname at site-a (${SITE_A_IP})"
      echo "            so dispatch flows coordinator -> site-a -> this agent"
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
  ensure_fed_network
  ensure_base_image

  ensure_vm "$COORD_NAME"  create_coordinator
  ensure_vm "$SITE_A_NAME" create_site_a
  ensure_vm "$SITE_B_NAME" create_site_b
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
  print_vm_summary "$COORD_NAME"  "coordinator" "fed:${COORD_IP}"
  print_vm_summary "$SITE_A_NAME" "site"        "fed:${SITE_A_IP}"
  print_vm_summary "$SITE_B_NAME" "site"        "fed:${SITE_B_IP}"
  print_vm_summary "$AGENT_NAME"  "agent"       "fed:${AGENT_IP}"

  echo "Default login (all VMs):"
  echo "  user     = ${USERNAME}"
  echo "  password = ${PASSWORD}"
  echo
  echo "sysmanage UI login — when you configure /etc/sysmanage.yaml on the server(s):"
  echo "  - security.admin_userid MUST be a valid EMAIL (login validates EmailStr;"
  echo "    a bare 'admin' -> HTTP 422, not 401). e.g. admin@example.com / admin"
  echo "  - email.enabled: true  (just the flag — no SMTP server/password needed)."
  echo
  echo "Federation network (${FED_NET_NAME}, static, no internet):"
  echo "  coordinator : ${COORD_IP}"
  echo "  site-a      : ${SITE_A_IP}"
  echo "  site-b      : ${SITE_B_IP}"
  echo "  fed-agent   : ${AGENT_IP}"
  echo "  host        : ${FED_NET_HOST_IP}    (SSH from here:  ssh ${USERNAME}@${COORD_IP})"
  echo
  echo "Suggested bring-up order:"
  echo "  1. Install sysmanage on coordinator + both sites; sysmanage-agent on fed-agent."
  echo "  2. On the coordinator, set Server Role -> Coordinator and run an alembic"
  echo "     upgrade head (the federation_role column ships in migration m7fedrole)."
  echo "  3. On each site, set Server Role -> Site, exchange identity keys, and enroll"
  echo "     upstream against https://${COORD_IP}:<api-port>."
  echo "  4. Point fed-agent at site-a (${SITE_A_IP}) and watch the rollup + dispatch"
  echo "     paths light up on the coordinator's Federation pages."
  echo
  echo "Re-check status :  $0 status"
  echo "Tear everything :  $0 stop"
}

cmd_stop() {
  check_deps
  for name in "${VM_NAMES[@]}"; do
    # Always try destroy first, regardless of what vm_running thinks.
    # Skipping destroy when vm_running returned false (e.g. a transient
    # libvirt state lie, a previously-failed run, or a fast-moving
    # crash) and then undefining leaves a "transient" running domain
    # that ``start`` can't recreate ("Domain is already active").
    # destroy on a stopped domain is a no-op + non-zero exit, which
    # ``|| true`` absorbs cleanly.
    log "$name: destroying (if running)"
    virsh_ destroy "$name" >/dev/null 2>&1 || true
    if vm_exists "$name"; then
      log "$name: undefining (removing disks)"
      virsh_ undefine "$name" --remove-all-storage --nvram >/dev/null 2>&1 \
        || virsh_ undefine "$name" --remove-all-storage >/dev/null 2>&1 \
        || virsh_ undefine "$name" >/dev/null 2>&1 \
        || warn "$name: undefine failed — may need manual cleanup with 'virsh undefine $name --remove-all-storage'"
    else
      log "$name: not defined — skipping undefine"
    fi
  done

  if virsh_ net-info "$FED_NET_NAME" >/dev/null 2>&1; then
    if net_is_active "$FED_NET_NAME"; then
      virsh_ net-destroy "$FED_NET_NAME" >/dev/null 2>&1 || true
    fi
    virsh_ net-undefine "$FED_NET_NAME" >/dev/null 2>&1 || true
    log "network $FED_NET_NAME: removed"
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
    nat_ip="$(get_nat_ip "$name")"
    if [[ -n "$nat_ip" ]]; then
      printf "    %-14s %s\n" "NAT (DHCP):" "$nat_ip"
    fi
  fi
}

cmd_status() {
  check_deps
  echo "=== Networks ==="
  for net in default "$FED_NET_NAME"; do
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
  print_vm_status "$COORD_NAME"  "fed:${COORD_IP}"
  print_vm_status "$SITE_A_NAME" "fed:${SITE_A_IP}"
  print_vm_status "$SITE_B_NAME" "fed:${SITE_B_IP}"
  print_vm_status "$AGENT_NAME"  "fed:${AGENT_IP}"

  echo
  echo "Credentials: user=${USERNAME}  password=${PASSWORD}"
}

usage() {
  cat <<EOF
Usage: $0 {start|stop|status}

  start   Create and start the four VMs (idempotent — already-running
          VMs are reported, not re-created).
  stop    Destroy all four VMs, delete their disks and seed ISOs, and
          tear down the ${FED_NET_NAME} isolated network.  The Ubuntu
          base cloud image is kept so a subsequent 'start' is fast.
  status  Show network state and per-VM state + configured federation
          static IPs + DHCP-assigned NAT IPs.
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
