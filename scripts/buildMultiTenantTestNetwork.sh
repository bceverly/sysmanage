#!/usr/bin/env bash
# buildMultiTenantTestNetwork.sh — Provision KVM VMs for sysmanage
# Phase 13.1 MULTI-TENANCY testing on libvirt/KVM.
#
# Multi-tenancy splits data across logical partitions, each of which can live
# in its OWN physical database (design §5: same schema, layout chosen by config
# not code).  This script gives every partition — and a second tenant — its own
# VM, so you can exercise the real distributed-database topology instead of the
# collapsed single-DB homelab default:
#
#   sysmanage-mt-registry  (10.80.0.1) — PostgreSQL for the REGISTRY / bootstrap
#                                        database (the control plane: tenant
#                                        registry + per-tenant placements).
#                                        This is the DB your sysmanage.yaml
#                                        ``registry:`` block points at.
#   sysmanage-mt-shared    (10.80.0.2) — PostgreSQL for the SHARED reference
#                                        database (``shared_*`` tables).  NOTE:
#                                        in the current code (13.1.A) the shared
#                                        partition still collapses onto the
#                                        bootstrap engine; this VM is here so the
#                                        topology is ready for the 13.1.C/D
#                                        dedicated-engine wiring.
#   sysmanage-mt-tenant-a  (10.80.0.3) — PostgreSQL for TENANT A's database.
#   sysmanage-mt-tenant-b  (10.80.0.4) — PostgreSQL for TENANT B's database (the
#                                        "additional tenant" — proves per-tenant
#                                        data really lands in separate DBs).
#   sysmanage-mt-control   (10.80.0.10) — The CONTROL PLANE: runs the sysmanage
#                                        server + OpenBAO.  This is what actually
#                                        routes requests across the databases
#                                        above (get_request_engine seam + the
#                                        licensed multitenancy_engine leasing
#                                        per-tenant credentials from OpenBAO).
#                                        Set INCLUDE_CONTROL_PLANE=0 to omit it
#                                        and instead point your dev host's
#                                        sysmanage at these DBs.
#
# The four DB VMs come up TURNKEY: cloud-init installs PostgreSQL, opens it on
# the isolated 10.80.0.0/24 network, and creates the role + database.  The
# control-plane VM is a bare Ubuntu box — install sysmanage + OpenBAO on it per
# the instructions printed at the end (mirrors buildFederationTestNetwork.sh).
#
# Usage:
#   scripts/buildMultiTenantTestNetwork.sh start    # create + start (idempotent)
#   scripts/buildMultiTenantTestNetwork.sh stop     # destroy + undefine + delete disks
#   scripts/buildMultiTenantTestNetwork.sh status    # show VM/network state + IPs
#
# All VMs share login credentials:
#   user     = ubuntu
#   password = Ubuntu123$
# The PostgreSQL role on every DB VM:
#   role     = sysmanage
#   password = SysMgrTest123   (database = per-VM, see the summary)
#
# Requirements on the host:
#   sudo apt install libvirt-clients libvirt-daemon-system virtinst \
#                    qemu-utils qemu-system-x86 cloud-image-utils curl python3-gi

set -euo pipefail

# ---------------------------------------------------------------------------
# Optional HA mode: give tenant-a a streaming-replication STANDBY so you can
# test a PostgreSQL failover of a tenant database (Phase 15.1) — including the
# OpenBAO dynamic-credential path, which reaches tenant DBs via leased creds.
# Enable with the ``--ha`` flag (or HA=1).  Adds the ``failover`` / ``failback``
# subcommands that drive that tenant-a primary/standby pair over SSH.
# ---------------------------------------------------------------------------
HA_MODE="${HA:-0}"
_args=()
for _a in "$@"; do
  case "$_a" in
    --ha) HA_MODE=1 ;;
    *)    _args+=("$_a") ;;
  esac
done
set -- ${_args[@]+"${_args[@]}"}

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

# PostgreSQL role provisioned on every DB VM (alphanumeric on purpose — it goes
# through psql in cloud-init runcmd, so no shell-special characters).
DB_ROLE="${DB_ROLE:-sysmanage}"
DBPASS="${DBPASS:-SysMgrTest123}"

# Whether to also build the control-plane (server + OpenBAO) VM.  Set to 0 if
# you'd rather run sysmanage from your dev host against these DBs.
INCLUDE_CONTROL_PLANE="${INCLUDE_CONTROL_PLANE:-1}"

# Isolated bridge for the multi-tenant DB network.  Every VM keeps a NAT NIC
# for internet (so cloud-init can apt-install PostgreSQL and the control plane
# can install sysmanage from the PPA) AND a static NIC on this bridge, giving
# the nodes stable, known addresses.  The host gets an IP on the bridge too, so
# you can SSH straight into any node over 10.80.0.x.
MT_NET_NAME="${MT_NET_NAME:-sysmanage-mt}"
MT_NET_BRIDGE="${MT_NET_BRIDGE:-virbr80}"
MT_NET_HOST_IP="${MT_NET_HOST_IP:-10.80.0.254}"
MT_NET_MASK="${MT_NET_MASK:-255.255.255.0}"
MT_NET_CIDR="${MT_NET_CIDR:-10.80.0.0/24}"

# Per-VM sizing.  Disk sizes are the max the FS can grow to — qcow2 is
# thin-allocated so unused space costs nothing on the host.
DB_VCPUS="${DB_VCPUS:-1}"
DB_RAM="${DB_RAM:-2048}"
DB_DISK_GB="${DB_DISK_GB:-20}"

REGISTRY_NAME="${REGISTRY_NAME:-sysmanage-mt-registry}"
REGISTRY_DBNAME="${REGISTRY_DBNAME:-sysmanage_registry}"
REGISTRY_NAT_MAC="${REGISTRY_NAT_MAC:-52:54:00:80:50:01}"
REGISTRY_MT_MAC="${REGISTRY_MT_MAC:-52:54:00:80:00:01}"
REGISTRY_IP="${REGISTRY_IP:-10.80.0.1}"

SHARED_NAME="${SHARED_NAME:-sysmanage-mt-shared}"
SHARED_DBNAME="${SHARED_DBNAME:-sysmanage_shared}"
SHARED_NAT_MAC="${SHARED_NAT_MAC:-52:54:00:80:50:02}"
SHARED_MT_MAC="${SHARED_MT_MAC:-52:54:00:80:00:02}"
SHARED_IP="${SHARED_IP:-10.80.0.2}"

TENANT_A_NAME="${TENANT_A_NAME:-sysmanage-mt-tenant-a}"
TENANT_A_DBNAME="${TENANT_A_DBNAME:-sysmanage_tenant_a}"
TENANT_A_NAT_MAC="${TENANT_A_NAT_MAC:-52:54:00:80:50:03}"
TENANT_A_MT_MAC="${TENANT_A_MT_MAC:-52:54:00:80:00:03}"
TENANT_A_IP="${TENANT_A_IP:-10.80.0.3}"

TENANT_B_NAME="${TENANT_B_NAME:-sysmanage-mt-tenant-b}"
TENANT_B_DBNAME="${TENANT_B_DBNAME:-sysmanage_tenant_b}"
TENANT_B_NAT_MAC="${TENANT_B_NAT_MAC:-52:54:00:80:50:04}"
TENANT_B_MT_MAC="${TENANT_B_MT_MAC:-52:54:00:80:00:04}"
TENANT_B_IP="${TENANT_B_IP:-10.80.0.4}"

# HA mode only: a streaming standby of tenant-a, plus the replication role the
# standby uses to clone + stream from the tenant-a primary.
REPL_ROLE="${REPL_ROLE:-replicator}"
REPL_PASS="${REPL_PASS:-ReplTest123}"
TENANT_A_STANDBY_NAME="${TENANT_A_STANDBY_NAME:-sysmanage-mt-tenant-a-standby}"
TENANT_A_STANDBY_NAT_MAC="${TENANT_A_STANDBY_NAT_MAC:-52:54:00:80:50:05}"
TENANT_A_STANDBY_MT_MAC="${TENANT_A_STANDBY_MT_MAC:-52:54:00:80:00:05}"
TENANT_A_STANDBY_IP="${TENANT_A_STANDBY_IP:-10.80.0.5}"

CONTROL_NAME="${CONTROL_NAME:-sysmanage-mt-control}"
CONTROL_VCPUS="${CONTROL_VCPUS:-2}"
CONTROL_RAM="${CONTROL_RAM:-4096}"
CONTROL_DISK_GB="${CONTROL_DISK_GB:-40}"
CONTROL_NAT_MAC="${CONTROL_NAT_MAC:-52:54:00:80:50:0a}"
CONTROL_MT_MAC="${CONTROL_MT_MAC:-52:54:00:80:00:0a}"
CONTROL_IP="${CONTROL_IP:-10.80.0.10}"

# The set of VMs to manage.  Control plane is appended only when enabled.
VM_NAMES=("$REGISTRY_NAME" "$SHARED_NAME" "$TENANT_A_NAME" "$TENANT_B_NAME")
if [[ "$HA_MODE" == "1" ]]; then
  VM_NAMES+=("$TENANT_A_STANDBY_NAME")
fi
if [[ "$INCLUDE_CONTROL_PLANE" == "1" ]]; then
  VM_NAMES+=("$CONTROL_NAME")
fi

WORKDIR="$(mktemp -d -t sysmanage-mt-XXXXXX)"
trap 'rm -rf "$WORKDIR"' EXIT

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

# Force C locale so we can grep virsh output for English strings regardless of
# the user's $LANG.
virsh_() { LC_ALL=C virsh -c "$LIBVIRT_URI" "$@"; }

net_is_active()    { virsh_ net-list --name 2>/dev/null | grep -qFx "$1"; }
net_is_autostart() { virsh_ net-info "$1" 2>/dev/null | grep -qE '^Autostart:[[:space:]]+yes$'; }

# virt-install ships with `#!/usr/bin/env python3`, which inside an active venv
# resolves to the venv's gi-less interpreter.  Invoke through the system Python
# explicitly so the shebang's PATH lookup is bypassed.
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

ensure_mt_network() {
  if virsh_ net-info "$MT_NET_NAME" >/dev/null 2>&1; then
    log "network $MT_NET_NAME: already defined"
  else
    log "network $MT_NET_NAME: defining isolated bridge $MT_NET_BRIDGE"
    local xml="$WORKDIR/${MT_NET_NAME}.xml"
    cat > "$xml" <<EOF
<network>
  <name>${MT_NET_NAME}</name>
  <bridge name='${MT_NET_BRIDGE}' stp='on' delay='0'/>
  <ip address='${MT_NET_HOST_IP}' netmask='${MT_NET_MASK}'/>
</network>
EOF
    virsh_ net-define "$xml" >/dev/null
  fi
  net_is_active    "$MT_NET_NAME" || virsh_ net-start     "$MT_NET_NAME" >/dev/null
  net_is_autostart "$MT_NET_NAME" || virsh_ net-autostart "$MT_NET_NAME" >/dev/null
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

# Shared header (identical login + ssh setup on every node).
_user_data_header() {
  local host="$1" out="$2" do_pkg_update="$3"
  cat > "$out" <<EOF
#cloud-config
hostname: ${host}
fqdn: ${host}
manage_etc_hosts: true
ssh_pwauth: true
disable_root: false
package_update: ${do_pkg_update}
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
EOF
}

# A DB node: install PostgreSQL, open it on the isolated subnet, create the
# role + database.  The role/db creation is idempotent (guarded by existence
# checks) so a re-applied seed never errors.  Runtime shell ``$`` is escaped
# (\$) so it survives this build-host heredoc into the guest unchanged.
# mode = plain (role + db) | primary (role + db + replication config/role) |
# standby (postgres + subnet only; it is cloned from the primary via basebackup).
write_user_data_db() {
  local host="$1" dbname="$2" out="$3" mode="${4:-plain}"
  _user_data_header "$host" "$out" "true"
  cat >> "$out" <<EOF
packages:
  - postgresql
runcmd:
  - systemctl enable --now ssh
  - |
    for d in /etc/postgresql/*/main; do
      echo "listen_addresses = '*'" >> "\$d/postgresql.conf"
      echo "host all all ${MT_NET_CIDR} scram-sha-256" >> "\$d/pg_hba.conf"
EOF
  if [[ "$mode" == "primary" ]]; then
    cat >> "$out" <<EOF
      echo "wal_level = replica" >> "\$d/postgresql.conf"
      echo "max_wal_senders = 10" >> "\$d/postgresql.conf"
      echo "host replication ${REPL_ROLE} ${MT_NET_CIDR} scram-sha-256" >> "\$d/pg_hba.conf"
EOF
  fi
  cat >> "$out" <<EOF
    done
  - systemctl restart postgresql
EOF
  if [[ "$mode" != "standby" ]]; then
    cat >> "$out" <<EOF
  - |
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_ROLE}'" | grep -q 1 \\
      || sudo -u postgres psql -c "CREATE ROLE ${DB_ROLE} LOGIN PASSWORD '${DBPASS}' CREATEDB CREATEROLE;"
  - |
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${dbname}'" | grep -q 1 \\
      || sudo -u postgres createdb -O ${DB_ROLE} ${dbname}
EOF
  fi
  if [[ "$mode" == "primary" ]]; then
    cat >> "$out" <<EOF
  - |
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${REPL_ROLE}'" | grep -q 1 \\
      || sudo -u postgres psql -c "CREATE ROLE ${REPL_ROLE} REPLICATION LOGIN PASSWORD '${REPL_PASS}';"
EOF
  fi
}

# The control-plane node: bare Ubuntu + ssh.  sysmanage + OpenBAO are installed
# per the printed instructions (matches buildFederationTestNetwork.sh).
write_user_data_control() {
  local host="$1" out="$2"
  _user_data_header "$host" "$out" "false"
  cat >> "$out" <<EOF
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

# Dual-NIC netplan: eth0 = NAT NIC (DHCP, default route → internet), eth1 =
# multi-tenant NIC (static /24 on the isolated bridge, no gateway).
# $1: NAT MAC.  $2: MT MAC.  $3: MT static IPv4 (no CIDR).  $4: output file.
write_network_config() {
  local nat_mac="$1" mt_mac="$2" mt_ip="$3" out="$4"
  cat > "$out" <<EOF
version: 2
ethernets:
  nat0:
    match:
      macaddress: "${nat_mac}"
    set-name: eth0
    dhcp4: true
  mt0:
    match:
      macaddress: "${mt_mac}"
    set-name: eth1
    dhcp4: false
    addresses:
      - ${mt_ip}/24
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

# provision_vm <name> <kind> <dbname|-> <vcpus> <ram> <disk_gb> <nat_mac> <mt_mac> <mt_ip>
# kind = "db" | "control".  Every node is dual-homed (NAT NIC + static MT NIC).
provision_vm() {
  local name="$1" kind="$2" dbname="$3" vcpus="$4" ram="$5" disk_gb="$6"
  local nat_mac="$7" mt_mac="$8" mt_ip="$9"

  local ud="$WORKDIR/${name}-user-data"
  local md="$WORKDIR/${name}-meta-data"
  local nc="$WORKDIR/${name}-network-config"
  case "$kind" in
    db)         write_user_data_db "$name" "$dbname" "$ud" "plain" ;;
    db-primary) write_user_data_db "$name" "$dbname" "$ud" "primary" ;;
    db-standby) write_user_data_db "$name" "$dbname" "$ud" "standby" ;;
    *)          write_user_data_control "$name" "$ud" ;;
  esac
  write_meta_data      "$name" "$md"
  write_network_config "$nat_mac" "$mt_mac" "$mt_ip" "$nc"

  local seed_path="${IMG_POOL}/${name}-seed.iso"
  build_seed_iso "$ud" "$md" "$nc" "$seed_path"

  local disk_path="${IMG_POOL}/${name}.qcow2"
  create_disk "$disk_path" "$disk_gb"

  log "Defining $name (kind=$kind db=${dbname} vcpus=$vcpus ram=${ram}M disk=${disk_gb}G mt=$mt_ip)"
  virt_install_ --connect "$LIBVIRT_URI" \
    --name "$name" \
    --vcpus "$vcpus" \
    --memory "$ram" \
    --osinfo "$OS_VARIANT" \
    --disk "path=${disk_path},format=qcow2,bus=virtio" \
    --disk "path=${seed_path},device=cdrom,bus=sata" \
    --network "network=default,model=virtio,mac=${nat_mac}" \
    --network "network=${MT_NET_NAME},model=virtio,mac=${mt_mac}" \
    --graphics none \
    --console pty,target_type=serial \
    --noautoconsole \
    --import
}

create_registry() {
  provision_vm "$REGISTRY_NAME" "db" "$REGISTRY_DBNAME" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$REGISTRY_NAT_MAC" "$REGISTRY_MT_MAC" "$REGISTRY_IP"
}
create_shared() {
  provision_vm "$SHARED_NAME" "db" "$SHARED_DBNAME" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$SHARED_NAT_MAC" "$SHARED_MT_MAC" "$SHARED_IP"
}
create_tenant_a() {
  # In HA mode tenant-a is the replication PRIMARY (extra wal/repl config + a
  # replication role); otherwise it is a plain single DB.
  local kind="db"
  [[ "$HA_MODE" == "1" ]] && kind="db-primary"
  provision_vm "$TENANT_A_NAME" "$kind" "$TENANT_A_DBNAME" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$TENANT_A_NAT_MAC" "$TENANT_A_MT_MAC" "$TENANT_A_IP"
}
create_tenant_a_standby() {
  provision_vm "$TENANT_A_STANDBY_NAME" "db-standby" "$TENANT_A_DBNAME" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$TENANT_A_STANDBY_NAT_MAC" "$TENANT_A_STANDBY_MT_MAC" "$TENANT_A_STANDBY_IP"
}
create_tenant_b() {
  provision_vm "$TENANT_B_NAME" "db" "$TENANT_B_DBNAME" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$TENANT_B_NAT_MAC" "$TENANT_B_MT_MAC" "$TENANT_B_IP"
}
create_control() {
  provision_vm "$CONTROL_NAME" "control" "-" "$CONTROL_VCPUS" "$CONTROL_RAM" "$CONTROL_DISK_GB" \
    "$CONTROL_NAT_MAC" "$CONTROL_MT_MAC" "$CONTROL_IP"
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

# get_nat_ip <vm> — DHCP-assigned IP (no CIDR) on the NAT NIC, empty if unknown.
# Filters out the static 10.80.x MT address so it never shadows the NAT one.
get_nat_ip() {
  local name="$1"
  virsh_ domifaddr "$name" --source lease 2>/dev/null \
    | awk '/ipv4/ {print $4}' | grep -v '^10\.80\.' | head -1 | sed 's|/.*||'
}

# print_vm_summary <name> <role> <mt_ip> [<dbname>]
print_vm_summary() {
  local name="$1" role="$2" mt_ip="$3" dbname="${4:-}"
  echo "$name  (state: $(vm_state "$name"))"
  echo "  console : virsh -c ${LIBVIRT_URI} console ${name}    (Ctrl-] to exit)"
  printf '  %-7s : %s\n' "mt" "$mt_ip"
  local nat
  nat="$(get_nat_ip "$name")"
  if [[ -n "$nat" ]]; then
    echo "  NAT     : $nat"
  else
    echo "  NAT     : (pending — re-run '$0 status' once cloud-init finishes)"
  fi
  case "$role" in
    db)
      echo "  ssh     : ssh ${USERNAME}@${mt_ip}      (password: ${PASSWORD})"
      echo "  db      : postgresql://${DB_ROLE}:${DBPASS}@${mt_ip}:5432/${dbname}"
      echo "  verify  : psql 'postgresql://${DB_ROLE}:${DBPASS}@${mt_ip}:5432/${dbname}' -c '\\conninfo'"
      ;;
    db-standby)
      echo "  ssh     : ssh ${USERNAME}@${mt_ip}      (password: ${PASSWORD})"
      echo "  role    : streaming STANDBY of tenant-a (${TENANT_A_IP}); clone it once with"
      echo "            '$0 failback', then use '$0 failover' to promote it in a test"
      ;;
    control)
      echo "  ssh     : ssh ${USERNAME}@${mt_ip}      (password: ${PASSWORD})"
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage postgresql-client"
      echo "  openbao : build/start via the repo scripts (build-openbao.sh / start-openbao.sh)"
      echo "  role    : this box runs the server + OpenBAO and routes across the DB VMs"
      ;;
  esac
  echo
}

# ---------------------------------------------------------------------------
# Failover / failback helpers (HA mode — drive the tenant-a pair over SSH)
# ---------------------------------------------------------------------------

ha_ssh() {
  local ip="$1"; shift
  sshpass -p "$PASSWORD" ssh \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=10 -o LogLevel=ERROR \
    "${USERNAME}@${ip}" "$@"
}

check_ssh_deps() {
  command -v sshpass >/dev/null 2>&1 \
    || die "failover/failback drive the DB nodes over SSH and need 'sshpass'.
Install with:  sudo apt install sshpass"
}

# pg_role <ip> -> primary | standby | down   (pg_is_in_recovery: f=primary t=standby)
pg_role() {
  local ip="$1" rec
  rec="$(ha_ssh "$ip" "sudo -u postgres psql -tAc 'select pg_is_in_recovery();'" 2>/dev/null | tr -d '[:space:]')"
  case "$rec" in
    f) echo "primary" ;;
    t) echo "standby" ;;
    *) echo "down" ;;
  esac
}

pg_version() {
  ha_ssh "$1" "pg_lsclusters -h 2>/dev/null | awk 'NR==1{print \$1}'" 2>/dev/null | tr -d '[:space:]'
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_start() {
  check_deps
  log "Workspace         : $WORKDIR"
  log "libvirt image pool: $IMG_POOL"
  log "libvirt URI       : $LIBVIRT_URI"
  log "control plane     : $([[ "$INCLUDE_CONTROL_PLANE" == "1" ]] && echo "included ($CONTROL_NAME)" || echo "skipped (INCLUDE_CONTROL_PLANE=0)")"
  log "HA mode           : $([[ "$HA_MODE" == "1" ]] && echo "on — tenant-a gets a standby ($TENANT_A_STANDBY_NAME)" || echo "off (pass --ha to enable)")"

  ensure_default_network
  ensure_mt_network
  ensure_base_image

  ensure_vm "$REGISTRY_NAME" create_registry
  ensure_vm "$SHARED_NAME"   create_shared
  ensure_vm "$TENANT_A_NAME" create_tenant_a
  ensure_vm "$TENANT_B_NAME" create_tenant_b
  if [[ "$HA_MODE" == "1" ]]; then
    ensure_vm "$TENANT_A_STANDBY_NAME" create_tenant_a_standby
  fi
  if [[ "$INCLUDE_CONTROL_PLANE" == "1" ]]; then
    ensure_vm "$CONTROL_NAME" create_control
  fi

  if (( CREATED_COUNT > 0 )); then
    log ""
    log "Waiting 45s for cloud-init (PostgreSQL install on the DB VMs takes a"
    log "moment) + DHCP leases to settle..."
    sleep 45
  fi

  echo
  echo "=========================================="
  echo "  Post-start summary"
  echo "=========================================="
  echo
  print_vm_summary "$REGISTRY_NAME" "db"      "$REGISTRY_IP" "$REGISTRY_DBNAME"
  print_vm_summary "$SHARED_NAME"   "db"      "$SHARED_IP"   "$SHARED_DBNAME"
  print_vm_summary "$TENANT_A_NAME" "db"      "$TENANT_A_IP" "$TENANT_A_DBNAME"
  print_vm_summary "$TENANT_B_NAME" "db"      "$TENANT_B_IP" "$TENANT_B_DBNAME"
  if [[ "$HA_MODE" == "1" ]]; then
    print_vm_summary "$TENANT_A_STANDBY_NAME" "db-standby" "$TENANT_A_STANDBY_IP" "$TENANT_A_DBNAME"
  fi
  if [[ "$INCLUDE_CONTROL_PLANE" == "1" ]]; then
    print_vm_summary "$CONTROL_NAME" "control" "$CONTROL_IP"
  fi

  echo "Login (all VMs):  user=${USERNAME}  password=${PASSWORD}"
  echo "Postgres role  :  ${DB_ROLE} / ${DBPASS}   (per-VM database, see above)"
  echo
  echo "Multi-tenant network (${MT_NET_NAME}, isolated 10.80.0.0/24):"
  echo "  registry DB : ${REGISTRY_IP}   db=${REGISTRY_DBNAME}"
  echo "  shared DB   : ${SHARED_IP}   db=${SHARED_DBNAME}   (forward-looking; collapses onto bootstrap in 13.1.A)"
  echo "  tenant-a DB : ${TENANT_A_IP}   db=${TENANT_A_DBNAME}"
  echo "  tenant-b DB : ${TENANT_B_IP}   db=${TENANT_B_DBNAME}"
  [[ "$HA_MODE" == "1" ]] && \
  echo "  tnt-a stdby : ${TENANT_A_STANDBY_IP}   (streaming standby of tenant-a — see HA guide below)"
  [[ "$INCLUDE_CONTROL_PLANE" == "1" ]] && \
  echo "  control     : ${CONTROL_IP}  (sysmanage server + OpenBAO)"
  echo "  host        : ${MT_NET_HOST_IP}    (SSH from here:  ssh ${USERNAME}@${REGISTRY_IP})"
  echo
  print_wiring_guide
  [[ "$HA_MODE" == "1" ]] && print_ha_guide
  echo "Re-check status :  $0 status"
  echo "Tear everything :  $0 stop"
}

# The MT-specific bring-up sequence.  Kept accurate to the current code:
# registry = the bootstrap DB sysmanage.yaml points at; tenant DBs are reached
# via OpenBAO-brokered credentials + the licensed multitenancy_engine; the three
# alembic chains (registry/shared/tenant) run via 'make migrate'.
print_wiring_guide() {
  cat <<EOF
==========================================================================
  Wiring it together — multi-tenant bring-up (run on the control plane)
==========================================================================
The four DB VMs are turnkey (PostgreSQL is installed, opened on 10.80.0.0/24,
role '${DB_ROLE}' + per-VM database created).  Confirm one is reachable:

  psql 'postgresql://${DB_ROLE}:${DBPASS}@${REGISTRY_IP}:5432/${REGISTRY_DBNAME}' -c '\\conninfo'

Then, on the control plane (the ${CONTROL_NAME} VM, or your dev host if you ran
with INCLUDE_CONTROL_PLANE=0):

1. INSTALL the server + OpenBAO.
   - Package:  sudo apt install -y sysmanage     (after adding the PPA), OR run
     your dev checkout.  Build/start OpenBAO with scripts/build-openbao.sh then
     scripts/start-openbao.sh.

2. POINT the registry/bootstrap DB at the registry VM in /etc/sysmanage.yaml
   (the 'registry:' block is the new name for 'database:'), and turn MT on:

     registry:
       host: ${REGISTRY_IP}
       port: 5432
       name: ${REGISTRY_DBNAME}
       user: ${DB_ROLE}
       password: ${DBPASS}
     multitenancy:
       enabled: true
       self_service_provisioning: true
     vault:               # OpenBAO — brokers per-tenant DB credentials
       url: http://localhost:8200
       ...
     security:
       # admin_userid MUST be a valid email — /api/login validates it as
       # EmailStr, so a bare 'admin' is rejected with HTTP 422 (NOT 401).
       admin_userid: admin@example.com
       admin_password: admin
     email:
       enabled: true       # just the flag — no SMTP server/password needed for the test

   NOTE: per-tenant DB routing requires the licensed multitenancy_engine to be
   loaded (it owns the per-tenant engine cache + OpenBAO dynamic-credential
   leasing).  Without it the server raises a clear "Pro+ MULTITENANT_SAAS"
   error instead of silently misrouting.

3. RUN THE THREE ALEMBIC CHAINS (registry / shared / tenant) against the
   registry DB.  'make migrate' drives scripts/sysmanage_migrate.py — with MT
   on it starts OpenBAO for the per-tenant fan-out automatically:

     make migrate

4. PROVISION the least-privilege provisioner identity (a scoped Postgres role +
   OpenBAO policy so the server can self-provision tenants without holding root):

     make provision-bootstrap ARGS='--bao-token \$BAO_TOKEN'

5. CREATE THE TWO TENANTS from the control plane UI (Settings → Tenants, the
   /tenants page) or the control_plane API.  Provision tenant A against
   ${TENANT_A_IP}/${TENANT_A_DBNAME} and tenant B against
   ${TENANT_B_IP}/${TENANT_B_DBNAME}.  (For OpenBAO dynamic creds, configure its
   database secrets engine to reach each tenant Postgres using the '${DB_ROLE}'
   admin role created on those VMs.)

6. FAN THE TENANT CHAIN OUT to both new tenant DBs (OpenBAO must be running):

     make migrate-tenants

7. BIND HOSTS TO TENANTS.  Issue a tenant-scoped enrollment token per tenant
   (Tenants → token), drop it in each agent's sysmanage-agent.yaml under a
   top-level 'security:' mapping (security.enrollment_token), and (re)register
   the agent.  The host's data then lands in that tenant's database.

8. VERIFY ROUTING.  Switch the active tenant in the UI and confirm a host's
   detail/data is served from its tenant DB — e.g. compare row counts:

     psql 'postgresql://${DB_ROLE}:${DBPASS}@${TENANT_A_IP}:5432/${TENANT_A_DBNAME}' -c 'SELECT count(*) FROM hosts;'
     psql 'postgresql://${DB_ROLE}:${DBPASS}@${TENANT_B_IP}:5432/${TENANT_B_DBNAME}' -c 'SELECT count(*) FROM hosts;'

Caveat: in the current code (Phase 13.1.A) the registry and shared partitions
both collapse onto the bootstrap engine; the dedicated registry/shared engines
land in 13.1.C/D.  The ${SHARED_NAME} VM is provided so the topology is ready
for that wiring — until then, the shared chain's tables live in the registry DB.
==========================================================================
EOF
}

cmd_stop() {
  check_deps
  # Stop every VM this script can manage, regardless of the current
  # INCLUDE_CONTROL_PLANE setting, so a control plane created in a prior run is
  # still torn down.
  local all=("$REGISTRY_NAME" "$SHARED_NAME" "$TENANT_A_NAME" "$TENANT_B_NAME" \
             "$TENANT_A_STANDBY_NAME" "$CONTROL_NAME")
  for name in "${all[@]}"; do
    # Always try destroy first (a transient/running domain that vm_running
    # mis-reports would otherwise survive undefine as an unrecreatable
    # "already active" domain).  destroy on a stopped domain is a harmless
    # non-zero that '|| true' absorbs.
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

  if virsh_ net-info "$MT_NET_NAME" >/dev/null 2>&1; then
    if net_is_active "$MT_NET_NAME"; then
      virsh_ net-destroy "$MT_NET_NAME" >/dev/null 2>&1 || true
    fi
    virsh_ net-undefine "$MT_NET_NAME" >/dev/null 2>&1 || true
    log "network $MT_NET_NAME: removed"
  fi

  log ""
  log "Base cloud image kept at $BASE_IMG (re-used by 'start')."
  log "Delete it manually with:  sudo rm $BASE_IMG"
}

print_vm_status() {
  local name="$1" mt_ip="$2"
  if ! vm_exists "$name"; then
    printf "  %-26s %s\n" "$name" "(not defined)"
    return
  fi
  local state
  state="$(vm_state "$name")"
  printf "  %-26s %s\n" "$name" "$state"
  printf "    %-12s %s\n" "mt:" "$mt_ip"
  if [[ "$state" == "running" ]]; then
    local nat_ip
    nat_ip="$(get_nat_ip "$name")"
    if [[ -n "$nat_ip" ]]; then
      printf "    %-12s %s\n" "NAT (DHCP):" "$nat_ip"
    fi
  fi
}

cmd_status() {
  check_deps
  echo "=== Networks ==="
  for net in default "$MT_NET_NAME"; do
    if virsh_ net-info "$net" >/dev/null 2>&1; then
      if net_is_active "$net"; then
        printf "  %-26s %s\n" "$net" "active"
      else
        printf "  %-26s %s\n" "$net" "inactive"
      fi
    else
      printf "  %-26s %s\n" "$net" "(not defined)"
    fi
  done

  echo
  echo "=== VMs ==="
  print_vm_status "$REGISTRY_NAME" "$REGISTRY_IP"
  print_vm_status "$SHARED_NAME"   "$SHARED_IP"
  print_vm_status "$TENANT_A_NAME" "$TENANT_A_IP"
  print_vm_status "$TENANT_B_NAME" "$TENANT_B_IP"
  if vm_exists "$TENANT_A_STANDBY_NAME"; then
    print_vm_status "$TENANT_A_STANDBY_NAME" "$TENANT_A_STANDBY_IP"
  fi
  print_vm_status "$CONTROL_NAME"  "$CONTROL_IP"

  echo
  echo "Login: user=${USERNAME}  password=${PASSWORD}   |   Postgres: ${DB_ROLE}/${DBPASS}"
}

# HA-mode addendum: how to bring up + exercise the tenant-a failover.  Printed
# by cmd_start only when --ha is set.
print_ha_guide() {
  cat <<EOF
==========================================================================
  HA mode — tenant-a failover (Phase 15.1)
==========================================================================
tenant-a (${TENANT_A_IP}) is the replication PRIMARY; ${TENANT_A_STANDBY_NAME}
(${TENANT_A_STANDBY_IP}) is a bare PostgreSQL box waiting to become its standby.

1. CLONE the standby from the primary (one-time; needs 'sshpass' on this host):

     $0 failback        # basebackups ${TENANT_A_STANDBY_IP} from ${TENANT_A_IP} and starts it streaming

2. POINT tenant-a's access at BOTH nodes so the current primary is auto-selected:
   - In the server / when provisioning tenant-a, use a multi-host DSN:
       postgresql://${DB_ROLE}:${DBPASS}@${TENANT_A_IP},${TENANT_A_STANDBY_IP}:5432/${TENANT_A_DBNAME}?target_session_attrs=read-write
   - For OpenBAO dynamic creds, set tenant-a's database secrets 'connection_url'
     to the same comma-separated pair, so it can still mint creds after a failover.

3. TEST the failover (with the agent reporting into tenant-a so a load runs):

     $0 failover        # stops the primary + promotes the standby
     # -> the server's pre-ping + multi-host DSN reconnect to the new primary,
     #    and the OpenBAO lease-acquisition retry covers the dynamic-creds path.
     $0 failback        # rebuild the other node as a standby again

==========================================================================
EOF
}

cmd_failover() {
  check_deps
  check_ssh_deps
  [[ "$HA_MODE" == "1" ]] || warn "failover assumes the --ha topology (tenant-a + its standby)."
  local a_role s_role primary_ip standby_ip
  a_role="$(pg_role "$TENANT_A_IP")"
  s_role="$(pg_role "$TENANT_A_STANDBY_IP")"
  log "Roles: tenant-a=${a_role} (${TENANT_A_IP}), standby=${s_role} (${TENANT_A_STANDBY_IP})"

  if [[ "$a_role" == "primary" && "$s_role" == "standby" ]]; then
    primary_ip="$TENANT_A_IP"; standby_ip="$TENANT_A_STANDBY_IP"
  elif [[ "$s_role" == "primary" && "$a_role" == "standby" ]]; then
    primary_ip="$TENANT_A_STANDBY_IP"; standby_ip="$TENANT_A_IP"
  else
    die "Need one primary + one standby (got ${a_role}/${s_role}).  Run '$0 failback' first to build the standby."
  fi

  log "Stopping the primary at ${primary_ip} (simulating its loss)"
  ha_ssh "$primary_ip" "sudo systemctl stop postgresql" \
    || warn "primary stop returned non-zero (already down?)"
  local ver
  ver="$(pg_version "$standby_ip")"
  [[ -n "$ver" ]] || die "couldn't determine PostgreSQL version on standby ${standby_ip}"
  log "Promoting the standby at ${standby_ip} (pg ${ver})"
  ha_ssh "$standby_ip" "sudo pg_ctlcluster ${ver} main promote" \
    || die "promote failed on ${standby_ip}"

  echo
  log "Failover complete — ${standby_ip} is now tenant-a's primary."
  log "Watch the server route the tenant's data there; the OpenBAO lease-acquisition"
  log "retry (Phase 15.1) covers minting new tenant creds through the gap."
  log "Repair replication when ready:  $0 failback"
}

cmd_failback() {
  check_deps
  check_ssh_deps
  local a_role s_role primary_ip rebuild_ip ver
  a_role="$(pg_role "$TENANT_A_IP")"
  s_role="$(pg_role "$TENANT_A_STANDBY_IP")"
  log "Roles: tenant-a=${a_role} (${TENANT_A_IP}), standby=${s_role} (${TENANT_A_STANDBY_IP})"

  # Rebuild whichever node is NOT the current primary as a fresh streaming
  # standby of the primary (also used for the one-time initial clone, where the
  # standby is a bare fresh postgres).
  if [[ "$a_role" == "primary" ]]; then
    primary_ip="$TENANT_A_IP"; rebuild_ip="$TENANT_A_STANDBY_IP"
  elif [[ "$s_role" == "primary" ]]; then
    primary_ip="$TENANT_A_STANDBY_IP"; rebuild_ip="$TENANT_A_IP"
  else
    die "No primary is up (${a_role}/${s_role}) — start tenant-a before failback."
  fi

  ver="$(pg_version "$primary_ip")"
  [[ -n "$ver" ]] || die "couldn't determine PostgreSQL version on primary ${primary_ip}"
  log "Rebuilding ${rebuild_ip} as a streaming standby of ${primary_ip} (pg ${ver})"
  ha_ssh "$rebuild_ip" "\
    sudo systemctl stop postgresql; \
    sudo -u postgres rm -rf /var/lib/postgresql/${ver}/main; \
    sudo -u postgres bash -c 'PGPASSWORD=\"${REPL_PASS}\" pg_basebackup -h ${primary_ip} -U ${REPL_ROLE} -D /var/lib/postgresql/${ver}/main -R -P'; \
    sudo systemctl start postgresql" \
    || die "rebuild of ${rebuild_ip} failed (check the ${REPL_ROLE} role + pg_hba replication line on ${primary_ip})"

  echo
  log "Failback complete — primary=${primary_ip}, standby=${rebuild_ip}."
  log "Verify streaming:  ssh ${USERNAME}@${primary_ip} sudo -u postgres psql -c 'select * from pg_stat_replication;'"
}

usage() {
  cat <<EOF
Usage: $0 [--ha] {start|stop|status|failover|failback}

  start     Create and start the multi-tenant test VMs (idempotent — already
            running VMs are reported, not re-created).  The four DB VMs come up
            with PostgreSQL installed + a role/database created; the control-plane
            VM is bare (install sysmanage + OpenBAO per the printed guide).
  stop      Destroy every VM (incl. a control plane / HA standby from a prior
            run), delete disks + seed ISOs, and tear down the ${MT_NET_NAME}
            network.  The Ubuntu base image is kept so the next 'start' is fast.
  status    Show network + per-VM state, static MT IPs, and DHCP NAT IPs.
  failover  (HA) Stop tenant-a's current primary and promote its standby.
  failback  (HA) Rebuild the other node as a fresh streaming standby (also does
            the one-time initial clone of the standby from tenant-a).

Options:
  --ha      Add a streaming standby for tenant-a and enable failover/failback,
            so you can test a tenant-database PostgreSQL failover (Phase 15.1).
            (Also settable with HA=1.)  failover/failback need 'sshpass'.

Key environment overrides:
  INCLUDE_CONTROL_PLANE=0   Skip the server+OpenBAO VM (run sysmanage from your host).
  DB_RAM / DB_DISK_GB       Resize the DB VMs (default 2048 MiB / 20 GiB).
  DBPASS                    PostgreSQL role password (default SysMgrTest123).
EOF
}

main() {
  case "${1:-}" in
    start)    cmd_start ;;
    stop)     cmd_stop ;;
    status)   cmd_status ;;
    failover) cmd_failover ;;
    failback) cmd_failback ;;
    -h|--help|help|"") usage ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
