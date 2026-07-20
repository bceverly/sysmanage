#!/usr/bin/env bash
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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
#   sysmanage-mt-agent-a   (10.80.0.11) — A sysmanage-agent enrolled into TENANT
#                                        A (via a tenant-scoped enrollment token),
#   sysmanage-mt-agent-b   (10.80.0.12) — and one into TENANT B, so each tenant
#                                        database gets real host data flowing —
#                                        you can watch it survive a failover.
#                                        Set PROVISION_AGENTS=0 to skip them.
#
# The four DB VMs come up TURNKEY: cloud-init installs PostgreSQL, opens it on
# the isolated 10.80.0.0/24 network, and creates the role + database.  The
# control-plane VM ALSO comes up turnkey by default (PROVISION_CONTROL=1): the
# host rsyncs the local sysmanage checkout + the Pro+ prebuilt engine bundles
# onto it and stands the whole multi-tenant stack up unattended — OpenBAO, the
# licensed multitenancy_engine (self-signed multitenant_saas license), the three
# alembic chains, provision-bootstrap, and two demo tenants placed + migrated
# against the tenant DB VMs.  Then one agent VM per tenant is installed + enrolled
# so each tenant DB has live data.  Set PROVISION_CONTROL=0 to leave the control
# plane bare + print the manual wiring guide (mirrors buildFederationTestNetwork.sh).
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

# The REGISTRY standby — the important one.  The registry/bootstrap DB is the
# whole platform's single point of failure (every control-plane request and, in
# collapsed mode, the shared partition live in it), so in --ha it gets its own
# streaming standby and the control plane connects via a libpq multi-host DSN
# (target_session_attrs=read-write) so a registry-primary failover is survived
# automatically — no SaaS platform can accept one DB box taking the whole thing
# down.  tenant-b also gets a standby so every live DB is HA (tenant-a already is).
REGISTRY_STANDBY_NAME="${REGISTRY_STANDBY_NAME:-sysmanage-mt-registry-standby}"
REGISTRY_STANDBY_NAT_MAC="${REGISTRY_STANDBY_NAT_MAC:-52:54:00:80:50:06}"
REGISTRY_STANDBY_MT_MAC="${REGISTRY_STANDBY_MT_MAC:-52:54:00:80:00:06}"
REGISTRY_STANDBY_IP="${REGISTRY_STANDBY_IP:-10.80.0.6}"

TENANT_B_STANDBY_NAME="${TENANT_B_STANDBY_NAME:-sysmanage-mt-tenant-b-standby}"
TENANT_B_STANDBY_NAT_MAC="${TENANT_B_STANDBY_NAT_MAC:-52:54:00:80:50:07}"
TENANT_B_STANDBY_MT_MAC="${TENANT_B_STANDBY_MT_MAC:-52:54:00:80:00:07}"
TENANT_B_STANDBY_IP="${TENANT_B_STANDBY_IP:-10.80.0.7}"

# The database pairs that become HA (primary + streaming standby) under --ha.
# Format per entry: "<label> <primary_ip> <standby_ip> <dbname>".  Shared is
# omitted: it collapses onto the registry DB today, so registry HA already
# covers it.  Used by the failover/failback machinery + the auto-clone at start.
HA_PAIRS=(
  "registry ${REGISTRY_IP} ${REGISTRY_STANDBY_IP} ${REGISTRY_DBNAME}"
  "tenant-a ${TENANT_A_IP} ${TENANT_A_STANDBY_IP} ${TENANT_A_DBNAME}"
  "tenant-b ${TENANT_B_IP} ${TENANT_B_STANDBY_IP} ${TENANT_B_DBNAME}"
)

CONTROL_NAME="${CONTROL_NAME:-sysmanage-mt-control}"
CONTROL_VCPUS="${CONTROL_VCPUS:-2}"
CONTROL_RAM="${CONTROL_RAM:-4096}"
CONTROL_DISK_GB="${CONTROL_DISK_GB:-40}"
CONTROL_NAT_MAC="${CONTROL_NAT_MAC:-52:54:00:80:50:0a}"
CONTROL_MT_MAC="${CONTROL_MT_MAC:-52:54:00:80:00:0a}"
CONTROL_IP="${CONTROL_IP:-10.80.0.10}"

# Turnkey control-plane provisioning (set PROVISION_CONTROL=0 to leave the control
# VM bare + just print the manual wiring guide).  When on (default), 'start' rsyncs
# the local sysmanage checkout + the Pro+ prebuilt engine bundles onto the control
# VM and stands the whole stack up unattended: OpenBAO, the licensed
# multitenancy_engine (self-signed multitenant_saas license, exactly as the docs
# screenshot VMs do it), the 3 alembic chains, provision-bootstrap, and the two
# demo tenants (placement → OpenBAO db-secrets → migrate-tenants) pointing at the
# already-existing tenant DBs on their own VMs.
PROVISION_CONTROL="${PROVISION_CONTROL:-1}"
CONTROL_ADMIN_USER="${CONTROL_ADMIN_USER:-admin@sysmanage.org}"
CONTROL_ADMIN_PW="${CONTROL_ADMIN_PW:-SysManage!2026}"
# Tier that grants the multitenancy_engine (the whole control-plane API lives in it).
CONTROL_TIER="${CONTROL_TIER:-multitenant_saas}"

# Host source trees pushed onto the control VM.  Derived from this script's
# location (scripts/ lives in the sysmanage checkout); override if your layout
# differs.  PRO_SRC must contain storage/modules/<engine>/.../abi3/<engine>.tar.gz
# (the prebuilt bundles) + backend/licensing (the signer pro_keygen imports).
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSMANAGE_SRC="${SYSMANAGE_SRC:-$(dirname "$_SCRIPT_DIR")}"
PRO_SRC="${PRO_SRC:-$(dirname "$SYSMANAGE_SRC")/sysmanage-professional-plus}"
PRO_KEYGEN="${PRO_KEYGEN:-$(dirname "$SYSMANAGE_SRC")/sysmanage-docs/screenshots/pro_keygen.py}"

# Per-tenant agent VMs: one sysmanage-agent per tenant, enrolled via a
# tenant-scoped enrollment token so each tenant DB gets REAL host data flowing
# (and you can watch that data survive a 'failover tenant-a').  Provisioned only
# when the control plane is (they need it up + the tenants created first).  Set
# PROVISION_AGENTS=0 to skip them.
PROVISION_AGENTS="${PROVISION_AGENTS:-1}"
AGENT_VCPUS="${AGENT_VCPUS:-1}"
AGENT_RAM="${AGENT_RAM:-1024}"
AGENT_DISK_GB="${AGENT_DISK_GB:-15}"
AGENT_A_NAME="${AGENT_A_NAME:-sysmanage-mt-agent-a}"
AGENT_A_NAT_MAC="${AGENT_A_NAT_MAC:-52:54:00:80:50:0b}"
AGENT_A_MT_MAC="${AGENT_A_MT_MAC:-52:54:00:80:00:0b}"
AGENT_A_IP="${AGENT_A_IP:-10.80.0.11}"
AGENT_B_NAME="${AGENT_B_NAME:-sysmanage-mt-agent-b}"
AGENT_B_NAT_MAC="${AGENT_B_NAT_MAC:-52:54:00:80:50:0c}"
AGENT_B_MT_MAC="${AGENT_B_MT_MAC:-52:54:00:80:00:0c}"
AGENT_B_IP="${AGENT_B_IP:-10.80.0.12}"

# Agents are only meaningful with a provisioned control plane.
_AGENTS_ON=0
[[ "$INCLUDE_CONTROL_PLANE" == "1" && "$PROVISION_CONTROL" == "1" && "$PROVISION_AGENTS" == "1" ]] && _AGENTS_ON=1

# The set of VMs to manage.  Control plane is appended only when enabled.
VM_NAMES=("$REGISTRY_NAME" "$SHARED_NAME" "$TENANT_A_NAME" "$TENANT_B_NAME")
if [[ "$HA_MODE" == "1" ]]; then
  VM_NAMES+=("$REGISTRY_STANDBY_NAME" "$TENANT_A_STANDBY_NAME" "$TENANT_B_STANDBY_NAME")
fi
if [[ "$INCLUDE_CONTROL_PLANE" == "1" ]]; then
  VM_NAMES+=("$CONTROL_NAME")
fi
if [[ "$_AGENTS_ON" == "1" ]]; then
  VM_NAMES+=("$AGENT_A_NAME" "$AGENT_B_NAME")
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
# standby (postgres + subnet + replication config so it is promotable, but NO
# role/db — those arrive when 'failback' clones it from the primary via basebackup).
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
  # Apply the replication config to BOTH the primary AND the standby.  A base
  # backup copies the data dir, not /etc, so these settings do not travel with
  # the clone — and after a failover the promoted standby must itself be a valid
  # replication PRIMARY (accept a 'host replication' connection so failback can
  # rebuild the old primary streaming FROM it).  'host all all' does not match
  # replication connections, so without this the first failover→failback cycle
  # would wedge.  wal_level/max_wal_senders default sanely on modern PG but are
  # set explicitly so the intent is on the node regardless of package defaults.
  if [[ "$mode" == "primary" || "$mode" == "standby" ]]; then
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
  # In HA mode the registry is the replication PRIMARY (the platform-critical DB).
  local kind="db"
  [[ "$HA_MODE" == "1" ]] && kind="db-primary"
  provision_vm "$REGISTRY_NAME" "$kind" "$REGISTRY_DBNAME" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$REGISTRY_NAT_MAC" "$REGISTRY_MT_MAC" "$REGISTRY_IP"
}
create_registry_standby() {
  provision_vm "$REGISTRY_STANDBY_NAME" "db-standby" "$REGISTRY_DBNAME" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$REGISTRY_STANDBY_NAT_MAC" "$REGISTRY_STANDBY_MT_MAC" "$REGISTRY_STANDBY_IP"
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
  local kind="db"
  [[ "$HA_MODE" == "1" ]] && kind="db-primary"
  provision_vm "$TENANT_B_NAME" "$kind" "$TENANT_B_DBNAME" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$TENANT_B_NAT_MAC" "$TENANT_B_MT_MAC" "$TENANT_B_IP"
}
create_tenant_b_standby() {
  provision_vm "$TENANT_B_STANDBY_NAME" "db-standby" "$TENANT_B_DBNAME" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$TENANT_B_STANDBY_NAT_MAC" "$TENANT_B_STANDBY_MT_MAC" "$TENANT_B_STANDBY_IP"
}
create_control() {
  provision_vm "$CONTROL_NAME" "control" "-" "$CONTROL_VCPUS" "$CONTROL_RAM" "$CONTROL_DISK_GB" \
    "$CONTROL_NAT_MAC" "$CONTROL_MT_MAC" "$CONTROL_IP"
}
# Agent VMs come up bare (like the control plane) — they're installed + enrolled
# by provision_agents() after the tenants + their enrollment tokens exist.
create_agent_a() {
  provision_vm "$AGENT_A_NAME" "control" "-" "$AGENT_VCPUS" "$AGENT_RAM" "$AGENT_DISK_GB" \
    "$AGENT_A_NAT_MAC" "$AGENT_A_MT_MAC" "$AGENT_A_IP"
}
create_agent_b() {
  provision_vm "$AGENT_B_NAME" "control" "-" "$AGENT_VCPUS" "$AGENT_RAM" "$AGENT_DISK_GB" \
    "$AGENT_B_NAT_MAC" "$AGENT_B_MT_MAC" "$AGENT_B_IP"
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

# A compact at-a-glance access table: every VM's name, role, IP, and how to reach
# it (SSH for boxes, the browser URL for the control plane).
print_ssh_table() {
  local entries=(
    "${REGISTRY_NAME}|registry DB|${REGISTRY_IP}"
    "${SHARED_NAME}|shared DB|${SHARED_IP}"
    "${TENANT_A_NAME}|tenant-a DB|${TENANT_A_IP}"
    "${TENANT_B_NAME}|tenant-b DB|${TENANT_B_IP}"
  )
  if [[ "$HA_MODE" == "1" ]]; then
    entries+=(
      "${REGISTRY_STANDBY_NAME}|registry standby|${REGISTRY_STANDBY_IP}"
      "${TENANT_A_STANDBY_NAME}|tenant-a standby|${TENANT_A_STANDBY_IP}"
      "${TENANT_B_STANDBY_NAME}|tenant-b standby|${TENANT_B_STANDBY_IP}"
    )
  fi
  [[ "$INCLUDE_CONTROL_PLANE" == "1" ]] && entries+=("${CONTROL_NAME}|control plane|${CONTROL_IP}")
  if [[ "$_AGENTS_ON" == "1" ]]; then
    entries+=(
      "${AGENT_A_NAME}|agent (tenant-a)|${AGENT_A_IP}"
      "${AGENT_B_NAME}|agent (tenant-b)|${AGENT_B_IP}"
    )
  fi
  echo "Log in to any VM:   user=${USERNAME}   password=${PASSWORD}"
  echo "(your host is on the isolated 10.80.0.0/24 bridge, so ssh + the browser reach these directly)"
  echo
  printf '  %-31s %-18s %-12s %s\n' "VM" "ROLE" "IP" "ACCESS"
  printf '  %-31s %-18s %-12s %s\n' "-------------------------------" "------------------" "------------" "-----------------------------"
  local e name role ip access
  for e in "${entries[@]}"; do
    IFS='|' read -r name role ip <<<"$e"
    if [[ "$role" == "control plane" ]]; then
      access="ssh ${USERNAME}@${ip}  |  UI http://${ip}:3000"
    else
      access="ssh ${USERNAME}@${ip}"
    fi
    printf '  %-31s %-18s %-12s %s\n' "$name" "$role" "$ip" "$access"
  done
  echo
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
      echo "  role    : streaming STANDBY for ${dbname} (auto-cloned at start)"
      echo "  check   : ssh ${USERNAME}@${mt_ip} \"sudo -u postgres psql -tAc 'select pg_is_in_recovery()'\"  (t=standby)"
      ;;
    control)
      echo "  ssh     : ssh ${USERNAME}@${mt_ip}      (password: ${PASSWORD})"
      echo "  web ui  : http://${mt_ip}:3000     (open from THIS host's browser)"
      echo "  api     : http://${mt_ip}:8080"
      echo "  login   : ${CONTROL_ADMIN_USER} / ${CONTROL_ADMIN_PW}"
      echo "  role    : sysmanage server + OpenBAO (routes across the tenant DBs)"
      echo "  logs    : /var/log/sysmanage-control-setup.log  (setup)  ·  /var/log/sysmanage-start.log (server)"
      ;;
    agent)
      echo "  ssh     : ssh ${USERNAME}@${mt_ip}      (password: ${PASSWORD})"
      echo "  role    : sysmanage-agent enrolled into ${dbname}"
      echo "  logs    : sudo journalctl -u sysmanage-agent -f   ·   /var/log/sysmanage-agent-setup.log"
      ;;
  esac
  echo
}

# ---------------------------------------------------------------------------
# Failover / failback helpers (HA mode — drive the tenant-a pair over SSH)
# ---------------------------------------------------------------------------

ha_ssh() {
  local ip="$1"; shift
  # nosemgrep: generic.secrets.security.detected-ssh-password.detected-ssh-password -- test-VM password for the local libvirt rig, not a production secret
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
# Turnkey control-plane provisioning (host-driven over SSH — it needs local
# artifacts: your sysmanage checkout + the Pro+ prebuilt engine bundles).
# Mirrors the proven docs-screenshot provisioner (sysmanage-docs/screenshots/
# provision.sh) for the Pro+ engine + self-signed-license mechanism, and the
# multitenancy_engine's own control-plane API contract for tenant bring-up.
# ---------------------------------------------------------------------------

# rsync to a root-owned path on the VM: ubuntu has NOPASSWD sudo, so run the
# REMOTE rsync under sudo.  $1=local src, $2="<ip>:/abs/dest".
ha_rsync() {
  local src="$1" dest="$2"; shift 2
  # nosemgrep: generic.secrets.security.detected-ssh-password.detected-ssh-password -- test-VM password for the local libvirt rig, not a production secret
  sshpass -p "$PASSWORD" rsync -a --rsync-path="sudo rsync" \
    -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10" \
    "$@" "$src" "${USERNAME}@${dest}"
}

# scp a file into the ubuntu user's home on the VM.  $1=local file, $2=ip.
ha_scp() {
  # nosemgrep: generic.secrets.security.detected-ssh-password.detected-ssh-password -- test-VM password for the local libvirt rig, not a production secret
  sshpass -p "$PASSWORD" scp \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10 \
    "$1" "${USERNAME}@${2}:"
}

# Write the unattended, root-run control-plane setup script.  Host values are
# injected verbatim at the top; the body below is literal (single-quoted heredoc)
# and references them as shell vars.
emit_control_setup() {
  local f="$1"
  cat > "$f" <<'HEAD'
#!/usr/bin/env bash
# Unattended multi-tenant control-plane bring-up.  Runs as root on the control VM.
set -uo pipefail
exec > >(tee -a /var/log/sysmanage-control-setup.log) 2>&1
echo "### control-setup starting $(date -u +%FT%TZ)"
HEAD
  cat >> "$f" <<EOF
REGISTRY_IP='${REGISTRY_IP}'
REGISTRY_STANDBY_IP='${REGISTRY_STANDBY_IP}'
REGISTRY_HA='${HA_MODE}'
REGISTRY_DBNAME='${REGISTRY_DBNAME}'
DB_ROLE='${DB_ROLE}'
DBPASS='${DBPASS}'
TENANT_A_IP='${TENANT_A_IP}'
TENANT_A_STANDBY_IP='${TENANT_A_STANDBY_IP}'
TENANT_A_DBNAME='${TENANT_A_DBNAME}'
TENANT_B_IP='${TENANT_B_IP}'
TENANT_B_STANDBY_IP='${TENANT_B_STANDBY_IP}'
TENANT_B_DBNAME='${TENANT_B_DBNAME}'
ADMIN_USER='${CONTROL_ADMIN_USER}'
ADMIN_PW='${CONTROL_ADMIN_PW}'
TIER='${CONTROL_TIER}'
EOF
  cat >> "$f" <<'BODY'
SERVER=/opt/sysmanage
PRO=/opt/pro
LICDIR=/var/lib/sysmanage/license
MODDIR=/var/lib/sysmanage/modules
SVPY="$SERVER/.venv/bin/python"
export DEBIAN_FRONTEND=noninteractive

echo "=== [1/10] OS dependencies ==="
apt-get update -y
apt-get install -y postgresql-client python3 python3-venv python3-pip gettext \
    build-essential libpq-dev git rsync curl jq unzip ca-certificates gnupg openssl
# Node 20 for the React/Vite web UI (Ubuntu's default Node is too old for Vite).
if ! node --version 2>/dev/null | grep -qE '^v(1[89]|2[0-9])\.'; then
    apt-get purge -y libnode-dev libnode72 nodejs npm >/dev/null 2>&1 || true
    apt-get autoremove -y >/dev/null 2>&1 || true
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -o Dpkg::Options::="--force-overwrite" nodejs
fi

echo "=== [2/10] wait for the registry DB (${REGISTRY_IP}/${REGISTRY_DBNAME}) ==="
for i in $(seq 1 60); do
    PGPASSWORD="$DBPASS" psql -h "$REGISTRY_IP" -U "$DB_ROLE" -d "$REGISTRY_DBNAME" -tAc 'select 1' >/dev/null 2>&1 && { echo "  registry DB up"; break; }
    sleep 5
done

echo "=== [3/10] /etc/sysmanage.yaml (multi-tenant; registry on ${REGISTRY_IP}) ==="
# No security.admin_* here (that would trip the config-security banner); the admin
# user is created directly in stage [8]. email.enabled with smtp.host=localhost is
# "on" for the UI without needing a real SMTP server.
JWT="$(openssl rand -hex 32)"; SALT="$(openssl rand -hex 32)"
# HA: point the registry at a libpq multi-host list (primary,standby) and pin
# writes to the writable node.  config.py normalizes registry -> database, and
# db.py builds the URL with these options + pool_pre_ping (HA_ENGINE_KWARGS), so
# a registry-primary failover is survived with no config change — the whole point
# of registry HA.  Single-host otherwise.
if [ "$REGISTRY_HA" = "1" ] && [ -n "$REGISTRY_STANDBY_IP" ]; then
    REG_HOST="${REGISTRY_IP},${REGISTRY_STANDBY_IP}"
    REG_OPTIONS='  options: "target_session_attrs=read-write"'
else
    REG_HOST="${REGISTRY_IP}"
    REG_OPTIONS=""
fi
cat > /etc/sysmanage.yaml <<YAML
registry:
  host: "${REG_HOST}"
  port: 5432
  user: ${DB_ROLE}
  password: ${DBPASS}
  name: ${REGISTRY_DBNAME}
${REG_OPTIONS}
api:
  host: 0.0.0.0
  port: 8080
webui:
  host: 0.0.0.0
  port: 3000
  ssl: false
  https: false
multitenancy:
  enabled: true
  self_service_provisioning: true
vault:
  enabled: true
  url: http://127.0.0.1:8200
security:
  jwt_secret: "${JWT}"
  password_salt: "${SALT}"
email:
  enabled: true
  smtp:
    host: localhost
    port: 25
    use_tls: false
    use_ssl: false
    username: ""
    password: ""
    timeout: 30
  from_address: noreply@demo.sysmanage.org
  from_name: SysManage MT Demo
geo_lookup:
  enabled: false
YAML

echo "=== [4/10] Python venv + backend deps + OpenBAO ==="
cd "$SERVER"
make setup-venv
echo "  installing Python dependencies (a few minutes)..."
.venv/bin/pip install -r requirements.txt
# NOTE: psycopg2 is intentionally NOT installed — the repo is psycopg3-only
# (Phase 15.2).  The multitenancy_engine's _build_url now emits postgresql+psycopg;
# make sure storage/modules ships that rebuilt engine (make build-modules) so
# migrate-tenants doesn't hit "No module named 'psycopg2'" against an old bundle.
# OpenBAO (per-tenant credential broker). Best-effort: the repo's installer, then
# a fallback to the full dev install if that entrypoint has moved.
.venv/bin/python scripts/install-openbao.py >/dev/null 2>&1 || make install-dev >/dev/null 2>&1 || \
    echo "  WARN: could not auto-install OpenBAO — start-openbao.sh may fail (shakeout item)"

echo "=== [5/10] start OpenBAO ==="
./scripts/start-openbao.sh || echo "  WARN: start-openbao returned non-zero"
export BAO_ADDR="http://127.0.0.1:8200" VAULT_ADDR="http://127.0.0.1:8200"
if command -v bao >/dev/null 2>&1; then BAO=bao
elif [ -x "$HOME/.local/bin/bao" ]; then BAO="$HOME/.local/bin/bao"
elif [ -x /usr/local/bin/bao ]; then BAO=/usr/local/bin/bao
else BAO=bao; fi
BAO_TOKEN=""
[ -f "$SERVER/.vault_credentials" ] && BAO_TOKEN="$(grep 'ROOT_TOKEN=' "$SERVER/.vault_credentials" | cut -d= -f2)"
BAO_TOKEN="${BAO_TOKEN:-dev-only-token-change-me}"
export BAO_TOKEN VAULT_TOKEN="$BAO_TOKEN"
# The server + migrate process authenticate to OpenBAO with the token from
# /etc/sysmanage/openbao-token (vault_service._load_token_file).  Without it the
# db-secrets lease fails 'vault.not_enabled'/403 and migrate-tenants can't run.
mkdir -p /etc/sysmanage
printf '%s' "$BAO_TOKEN" > /etc/sysmanage/openbao-token
chmod 640 /etc/sysmanage/openbao-token

echo "=== [6/10] install prebuilt Pro+ $TIER engines + register + self-signed license ==="
PYVER="$("$SVPY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PLAT=linux; ARCH=x86_64
mkdir -p "$MODDIR" "$LICDIR"
# Resolve from the Pro+ tree: 'cd "$PRO"' so python -c's implicit CWD entry on
# sys.path is /opt/pro (not /opt/sysmanage, whose OSS backend.licensing.features
# has no get_modules_for_tier — that's a signing-side Pro+ function).
ENGINES="$(cd "$PRO" && PYTHONPATH="$PRO" "$SVPY" -c "from backend.licensing.features import get_modules_for_tier; print(' '.join(m for m in get_modules_for_tier('$TIER') if m != 'proplus_core'))")"
[ -n "$ENGINES" ] || { echo "  ERROR: could not resolve engines for tier $TIER"; ENGINES=""; }
for code in $ENGINES; do
    tb=""
    for _abi in "$PYVER" abi3; do
        tb="$(ls -1 "$PRO"/storage/modules/"$code"/*/"$PLAT"/"$ARCH"/"$_abi"/"$code".tar.gz 2>/dev/null | sort -V | tail -1 || true)"
        [ -n "$tb" ] && break
    done
    [ -n "$tb" ] || { echo "  WARN: no $PLAT/$ARCH bundle for $code — skipping"; continue; }
    dest="$MODDIR/${code}_${PYVER}"; rm -rf "$dest"; mkdir -p "$dest"; tar -xzf "$tb" -C "$dest"; echo "  + $code"
done
for code in $ENGINES proplus_core; do
    pj="$(ls -1 "$PRO"/storage/modules/"$code"/*/"$code"-plugin.iife.js 2>/dev/null | sort -V | tail -1 || true)"
    [ -n "$pj" ] && cp -f "$pj" "$MODDIR/${code}-plugin.iife.js"
done
rm -f "$MODDIR/proplus-plugin.iife.js"
# Register each extracted engine in proplus_module_cache so the loader finds it
# locally (offline; no license server). Verbatim from the docs provisioner.
cd "$SERVER" && PYTHONPATH="$SERVER" "$SVPY" - <<'PY'
import hashlib, json, platform
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from backend.persistence import db
from backend.persistence.models import ProPlusModuleCache
MODULES_DIR = Path("/var/lib/sysmanage/modules")
SYSTEM = platform.system().lower()
MACHINE = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}.get(
    platform.machine().lower(), platform.machine().lower())
def sha512(p):
    h = hashlib.sha512()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(8192), b""):
            h.update(c)
    return h.hexdigest()
Session = sessionmaker(bind=db.get_engine())
now = datetime.now(timezone.utc).replace(tzinfo=None)
ins = upd = 0
with Session() as s:
    for d in sorted(MODULES_DIR.glob("*_[0-9].[0-9]*")):
        if not d.is_dir():
            continue
        pyv = d.name.rsplit("_", 1)[1]; code = d.name[: -(len(pyv) + 1)]
        sos = sorted(d.glob("*.so"))
        if not sos:
            continue
        so = sos[0]
        try:
            ver = json.loads((d / "metadata.json").read_text())["version"]
        except Exception:
            ver = "unknown"
        row = (s.query(ProPlusModuleCache).filter_by(module_code=code, platform=SYSTEM,
               architecture=MACHINE, python_version=pyv).first())
        if row is None:
            s.add(ProPlusModuleCache(module_code=code, version=ver, platform=SYSTEM,
                  architecture=MACHINE, python_version=pyv, file_path=str(so),
                  file_hash=sha512(so), downloaded_at=now)); ins += 1
        else:
            row.version = ver; row.file_path = str(so); row.file_hash = sha512(so); row.downloaded_at = now; upd += 1
    s.commit()
print(f"  module cache: {ins} inserted, {upd} updated")
PY
# Self-signed multitenant_saas license (phone_home_url="" so validation stays local).
TIER="$TIER" PRO_PLUS_DIR="$PRO" OUT_DIR="$LICDIR" "$SVPY" /opt/pro_keygen.py
LIC="$(cat "$LICDIR/license.jwt")" "$SVPY" - <<'PY' || echo "  WARN: license inject failed"
import os, yaml
cfg = yaml.safe_load(open('/etc/sysmanage.yaml'))
cfg['license'] = {'key': os.environ['LIC'], 'modules_path': '/var/lib/sysmanage/modules', 'phone_home_url': ''}
yaml.safe_dump(cfg, open('/etc/sysmanage.yaml', 'w'), sort_keys=False)
PY

echo "=== [7/10] run the 3 alembic chains against the registry DB ==="
cd "$SERVER" && "$SVPY" scripts/sysmanage_migrate.py --no-tenants || echo "  WARN: base migrate returned non-zero"

echo "=== [8/10] create admin user + provision-bootstrap ==="
cd "$SERVER" && "$SVPY" - <<PY || echo "  (admin may already exist)"
import sys; sys.path.insert(0, ".")
from scripts._sysmanage_secure_installation import create_admin_user
create_admin_user({"email": "${ADMIN_USER}", "password": "${ADMIN_PW}", "first_name": "Admin", "last_name": "User"}, salt=None)
PY
make provision-bootstrap ARGS="--bao-token $BAO_TOKEN --pg-host ${REGISTRY_IP} --pg-superuser ${DB_ROLE} --pg-superuser-password ${DBPASS}" \
    || echo "  WARN: provision-bootstrap returned non-zero (continuing)"

echo "=== [9/10] start server (backend + frontend) + verify engines ==="
cd "$SERVER" && make stop >/dev/null 2>&1 || true
nohup make start > /var/log/sysmanage-start.log 2>&1 &
for i in $(seq 1 60); do
    curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1 && break
    sleep 3
done
curl -fsS http://127.0.0.1:8080/api/v1/server-info 2>/dev/null \
    | "$SVPY" -c "import sys,json; d=json.load(sys.stdin); print('  tier:', d.get('license_tier'), '| engines:', d.get('loaded_engines'))" 2>/dev/null \
    || echo "  (server-info unavailable — see /var/log/sysmanage-start.log)"

echo "=== [10/10] create + place + wire + migrate the two demo tenants ==="
# Defensively clear any lockout on the admin from prior runs: failed logins
# accumulate a counter and a locked account returns HTTP 423 forever, so a
# re-run would keep failing.  (The user/bootstrap tables collapse onto the
# registry DB in this topology.)
PGPASSWORD="$DBPASS" psql -h "$REGISTRY_IP" -U "$DB_ROLE" -d "$REGISTRY_DBNAME" \
    -c "UPDATE \"user\" SET is_locked=false, failed_login_attempts=0 WHERE userid='${ADMIN_USER}';" >/dev/null 2>&1 || true
# Log in, capturing the HTTP status + body so a failure is diagnosable, not silent.
LOGIN_RESP="$(curl -s -w $'\n%{http_code}' -X POST http://127.0.0.1:8080/api/v1/login \
    -H 'Content-Type: application/json' -d "{\"userid\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PW}\"}")"
LOGIN_CODE="$(printf '%s\n' "$LOGIN_RESP" | tail -n1)"
LOGIN_BODY="$(printf '%s\n' "$LOGIN_RESP" | sed '$d')"
JWT="$(printf '%s' "$LOGIN_BODY" | jq -r '.Authorization // .access_token // .token // empty' 2>/dev/null)"
if [ -z "$JWT" ]; then
    echo "  WARN: admin login failed (HTTP ${LOGIN_CODE}): ${LOGIN_BODY}"
    echo "  -> skipping tenant creation.  Create tenants from the UI, or fix + re-run."
else
    AUTH="Authorization: Bearer $JWT"; CP="http://127.0.0.1:8080/api/v1/control-plane"
    # Create the tenant; if it already exists (409 on a re-run), look it up by
    # slug so placement + migrate still proceed idempotently.
    mk_tenant() {  # $1=name $2=slug -> echoes the tenant id
        local id
        id="$(curl -s -X POST "$CP/tenants" -H "$AUTH" -H 'Content-Type: application/json' \
                -d "{\"name\":\"$1\",\"slug\":\"$2\"}" | jq -r '.id // empty')"
        if [ -z "$id" ]; then
            id="$(curl -s "$CP/tenants" -H "$AUTH" \
                  | jq -r --arg s "$2" '(.tenants // .items // .)[]? | select(.slug==$s) | .id' 2>/dev/null | head -1)"
        fi
        printf '%s' "$id"
    }
    place() { curl -s -X PUT "$CP/tenants/$1/placement" -H "$AUTH" -H 'Content-Type: application/json' \
                -d "{\"host\":\"$2\",\"port\":5432,\"dbname\":\"$3\",\"tier\":\"silo\",\"openbao_role\":\"$4\"}" >/dev/null; }
    # OpenBAO db-secrets for each REMOTE tenant Postgres (the 'sysmanage' admin role
    # already exists on those VMs). The role name MUST match the placement's openbao_role
    # or migrate-tenants silently skips the tenant.
    bao_tenant() {  # $1=config/db_name $2=host(may be multi-host) $3=dbname $4=leaserole
        local primary="${2%%,*}" owner="${3}_owner"
        # Stable NOLOGIN OWNER role that owns the tenant schema — mirrors the
        # engine's create_tenant_database/configure_openbao_role.  Each rotating
        # OpenBAO lease role is created IN ROLE <owner> and defaults SET role to
        # <owner>, so objects a lease creates are owned by <owner> and EVERY lease
        # can read them.  Without this each ephemeral lease owns its own tables and
        # the next lease (and migrate-tenants) gets "permission denied for table".
        # Applied via the provisioner (sysmanage) on the primary.
        PGPASSWORD="$DBPASS" psql -h "$primary" -U "$DB_ROLE" -d "$3" -v ON_ERROR_STOP=0 >/dev/null 2>&1 <<SQL
DO \$do\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='$owner') THEN CREATE ROLE "$owner" NOLOGIN; END IF;
END \$do\$;
GRANT "$owner" TO CURRENT_USER WITH ADMIN OPTION;
ALTER DATABASE "$3" OWNER TO "$owner";
ALTER SCHEMA public OWNER TO "$owner";
GRANT ALL ON SCHEMA public TO "$owner";
SQL
        local tsa=""; case "$2" in *,*) tsa="&target_session_attrs=read-write" ;; esac
        "$BAO" write "database/config/$1" plugin_name=postgresql-database-plugin allowed_roles="$4" \
            username="$DB_ROLE" password="$DBPASS" \
            connection_url="postgresql://{{username}}:{{password}}@$2:5432/$3?sslmode=prefer${tsa}" || echo "    WARN: bao config/$1 failed"
        "$BAO" write "database/roles/$4" db_name="$1" default_ttl=1h max_ttl=24h \
            creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}' IN ROLE \"$owner\"; ALTER ROLE \"{{name}}\" SET role TO '$owner';" \
            || echo "    WARN: bao role/$4 failed"
    }
    # HA: place each tenant at its primary+standby PAIR (libpq multi-host) so the
    # tenant's per-request engine (_build_url appends target_session_attrs=read-write)
    # and migrate-tenants both survive a tenant-DB failover — the app-side rebind
    # that makes 'failover tenant-a' keep the tenant serving, mirroring registry HA.
    if [ "$REGISTRY_HA" = "1" ]; then
        TA_HOST="${TENANT_A_IP},${TENANT_A_STANDBY_IP}"; TB_HOST="${TENANT_B_IP},${TENANT_B_STANDBY_IP}"
    else
        TA_HOST="$TENANT_A_IP"; TB_HOST="$TENANT_B_IP"
    fi
    TA="$(mk_tenant 'Tenant A' 'tenant-a')"; TB="$(mk_tenant 'Tenant B' 'tenant-b')"
    [ -n "$TA" ] && place "$TA" "$TA_HOST" "$TENANT_A_DBNAME" tenant-a-db && echo "  tenant-a: $TA (host=$TA_HOST)"
    [ -n "$TB" ] && place "$TB" "$TB_HOST" "$TENANT_B_DBNAME" tenant-b-db && echo "  tenant-b: $TB (host=$TB_HOST)"

    # Give the admin a registry identity + a grant to each tenant.  The tenant
    # switcher lists a user's GRANTS (not all tenants), so without this the
    # dropdown shows only "No tenant" even though the tenants exist.
    RUID="$(curl -s -H "$AUTH" "$CP/users?email=${ADMIN_USER}" | jq -r 'if length>0 then .[0].id else empty end')"
    [ -z "$RUID" ] && RUID="$(curl -s -X POST "$CP/users" -H "$AUTH" -H 'Content-Type: application/json' -d "{\"email\":\"${ADMIN_USER}\"}" | jq -r '.id // empty')"
    grant() { [ -n "$RUID" ] && [ -n "$1" ] && curl -s -o /dev/null -X POST "$CP/grants" -H "$AUTH" \
        -H 'Content-Type: application/json' -d "{\"user_id\":\"$RUID\",\"tenant_id\":\"$1\",\"role\":\"admin\",\"is_default\":$2}"; }
    grant "$TA" true; grant "$TB" false
    echo "  granted ${ADMIN_USER} -> both tenants (appear in the switcher)"

    bao_tenant tenant-a "$TA_HOST" "$TENANT_A_DBNAME" tenant-a-db
    bao_tenant tenant-b "$TB_HOST" "$TENANT_B_DBNAME" tenant-b-db
    cd "$SERVER" && ( make migrate-tenants || "$SVPY" scripts/sysmanage_migrate.py --tenants-only ) \
        || echo "  WARN: migrate-tenants returned non-zero"

    # Mint one enrollment token per tenant (plaintext returned ONCE) so the agent
    # VMs can register straight into their tenant.  The host reads this file.
    mk_token() { curl -s -X POST "$CP/tenants/$1/enrollment-tokens" -H "$AUTH" \
                   -H 'Content-Type: application/json' -d "{\"label\":\"$2\"}" | jq -r '.token // empty'; }
    { [ -n "$TA" ] && echo "TENANT_A_TOKEN=$(mk_token "$TA" agent-a)"
      [ -n "$TB" ] && echo "TENANT_B_TOKEN=$(mk_token "$TB" agent-b)"; } > /root/tenant-enrollment.env
    chmod 600 /root/tenant-enrollment.env
    echo "  enrollment tokens -> /root/tenant-enrollment.env"
fi

echo "### control-setup complete $(date -u +%FT%TZ)"
BODY
}

# Host-side driver: wait for the control VM, push the local trees, run the setup.
provision_control_plane() {
  check_ssh_deps
  command -v rsync >/dev/null 2>&1 \
    || die "control-plane provisioning needs rsync on the host.  Install:  sudo apt install rsync"
  [ -d "$SYSMANAGE_SRC" ]  || die "SYSMANAGE_SRC not found: $SYSMANAGE_SRC"
  [ -d "$PRO_SRC" ]        || die "Pro+ source not found: $PRO_SRC
The control plane needs the prebuilt multitenancy_engine bundle from the Pro+ repo.
Set PRO_SRC=/path/to/sysmanage-professional-plus, or run with PROVISION_CONTROL=0
to leave the control VM bare and just print the manual wiring guide."
  [ -f "$PRO_KEYGEN" ]     || die "pro_keygen.py not found: $PRO_KEYGEN (set PRO_KEYGEN=...)"
  [ -e "$PRO_SRC/storage/modules/multitenancy_engine" ] \
    || warn "No multitenancy_engine bundle under $PRO_SRC/storage/modules — run 'make pull-modules' in the Pro+ repo first, or the engine won't load."

  local ip="$CONTROL_IP" i
  log "Control plane: waiting for SSH + cloud-init on $ip ..."
  for i in $(seq 1 60); do
    ha_ssh "$ip" "test -f /var/lib/cloud/instance/boot-finished" >/dev/null 2>&1 && break
    sleep 5
  done
  ha_ssh "$ip" "cloud-init status --wait" >/dev/null 2>&1 || true

  log "Control plane: pushing sysmanage checkout -> $ip:/opt/sysmanage (rsync) ..."
  ha_ssh "$ip" "sudo mkdir -p /opt/sysmanage /opt/pro && sudo chown ${USERNAME}:${USERNAME} /opt/sysmanage /opt/pro" || true
  ha_rsync "$SYSMANAGE_SRC/" "$ip:/opt/sysmanage/" \
    --delete --exclude '.git' --exclude '.venv' --exclude 'node_modules' \
    --exclude 'frontend/node_modules' --exclude '__pycache__' --exclude '*.pyc'
  log "Control plane: pushing Pro+ engine bundles -> $ip:/opt/pro (rsync) ..."
  ha_rsync "$PRO_SRC/" "$ip:/opt/pro/" \
    --delete --exclude '.git' --exclude '.venv' --exclude 'node_modules' \
    --exclude 'frontend' --exclude '__pycache__' --exclude '*.pyc'
  ha_rsync "$PRO_KEYGEN" "$ip:/opt/pro_keygen.py"

  local setup="$WORKDIR/control-setup.sh"
  emit_control_setup "$setup"
  ha_scp "$setup" "$ip"
  log "Control plane: running unattended setup on $ip (several minutes; live output below,"
  log "also tee'd to /var/log/sysmanage-control-setup.log on the VM) ..."
  ha_ssh "$ip" "sudo bash /home/${USERNAME}/control-setup.sh" \
    || warn "control-setup returned non-zero — inspect /var/log/sysmanage-control-setup.log on $ip"
}

# Write the root-run agent setup script.  Installs sysmanage-agent from the PPA
# and points it at the control plane with a tenant-scoped enrollment token, so
# the host registers straight into that tenant's database.
emit_agent_setup() {
  local f="$1" token="$2"
  cat > "$f" <<'HEAD'
#!/usr/bin/env bash
# Unattended sysmanage-agent bring-up (enrolls into one tenant).  Runs as root.
set -uo pipefail
exec > >(tee -a /var/log/sysmanage-agent-setup.log) 2>&1
echo "### agent-setup starting $(date -u +%FT%TZ)"
HEAD
  cat >> "$f" <<EOF
SERVER_IP='${CONTROL_IP}'
ENROLL_TOKEN='${token}'
EOF
  cat >> "$f" <<'BODY'
export DEBIAN_FRONTEND=noninteractive
add-apt-repository -y ppa:bceverly/sysmanage-agent || true
apt-get update -y
apt-get install -y sysmanage-agent
# nosemgrep: javascript.lang.security.detect-insecure-websocket.detect-insecure-websocket -- local test rig: the agent connects over plain ws:// (HTTP:8080), not production
# The agent builds ws://hostname:port/api/agent/connect from server.hostname /
# port / use_https (it ignores server.url).  security.enrollment_token is what
# binds this host to its tenant at registration (the multitenancy engine
# validates + consumes it).  Format matches the SysManage config builder.
cat > /etc/sysmanage-agent.yaml <<CFG
server:
  hostname: ${SERVER_IP}
  port: 8080
  use_https: false
  verify_ssl: false

security:
  enrollment_token: "${ENROLL_TOKEN}"

client:
  registration_retry_interval: 30
  max_registration_retries: 10
  update_check_interval: 3600
  package_collection_interval: 86400
  enable_package_collection: true
  collect_packages_at_startup: true

i18n:
  language: en

logging:
  level: "INFO"

websocket:
  auto_reconnect: true
  reconnect_interval: 5
  ping_interval: 60

script_execution:
  enabled: false

data_collection:
  enabled: true
  types:
    - software_packages
    - system_updates
    - hardware_info
    - network_interfaces
    - user_accounts
    - system_metrics

database:
  path: "/var/lib/sysmanage-agent/agent.db"
CFG
systemctl enable --now sysmanage-agent 2>/dev/null || systemctl restart sysmanage-agent 2>/dev/null || true
echo "### agent-setup complete $(date -u +%FT%TZ)"
BODY
}

# Host-side: read the per-tenant enrollment tokens the control plane wrote, then
# install + enroll each agent VM into its tenant.  Runs after the control plane.
provision_agents() {
  check_ssh_deps
  local tokens token_a token_b
  # control-setup wrote /root/tenant-enrollment.env on the control VM.
  tokens="$(ha_ssh "$CONTROL_IP" "sudo cat /root/tenant-enrollment.env 2>/dev/null" 2>/dev/null)"
  token_a="$(printf '%s\n' "$tokens" | sed -n 's/^TENANT_A_TOKEN=//p' | tr -d '[:space:]')"
  token_b="$(printf '%s\n' "$tokens" | sed -n 's/^TENANT_B_TOKEN=//p' | tr -d '[:space:]')"
  [ -n "$token_a" ] || warn "no tenant-a enrollment token on the control plane — agent-a won't bind to a tenant (check the control-setup log)."
  [ -n "$token_b" ] || warn "no tenant-b enrollment token on the control plane — agent-b won't bind to a tenant."
  _provision_one_agent "$AGENT_A_NAME" "$AGENT_A_IP" "$token_a" "tenant-a"
  _provision_one_agent "$AGENT_B_NAME" "$AGENT_B_IP" "$token_b" "tenant-b"
}

_provision_one_agent() {
  local name="$1" ip="$2" token="$3" label="$4" setup i
  log "Agent for ${label} on ${ip}: waiting for SSH + cloud-init..."
  for i in $(seq 1 60); do
    ha_ssh "$ip" "test -f /var/lib/cloud/instance/boot-finished" >/dev/null 2>&1 && break
    sleep 5
  done
  setup="$WORKDIR/agent-setup-${label}.sh"
  emit_agent_setup "$setup" "$token"
  ha_scp "$setup" "$ip" || { warn "agent [${label}] on ${ip} unreachable (scp failed) — skipping"; return 0; }
  log "Agent for ${label}: installing + enrolling (tee'd to /var/log/sysmanage-agent-setup.log on the VM)..."
  ha_ssh "$ip" "sudo bash /home/${USERNAME}/$(basename "$setup")" \
    || warn "agent [${label}] setup returned non-zero — inspect /var/log/sysmanage-agent-setup.log on $ip"
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
    ensure_vm "$REGISTRY_STANDBY_NAME" create_registry_standby
    ensure_vm "$TENANT_A_STANDBY_NAME" create_tenant_a_standby
    ensure_vm "$TENANT_B_STANDBY_NAME" create_tenant_b_standby
  fi
  if [[ "$INCLUDE_CONTROL_PLANE" == "1" ]]; then
    ensure_vm "$CONTROL_NAME" create_control
  fi
  if [[ "$_AGENTS_ON" == "1" ]]; then
    ensure_vm "$AGENT_A_NAME" create_agent_a
    ensure_vm "$AGENT_B_NAME" create_agent_b
  fi

  if (( CREATED_COUNT > 0 )); then
    log ""
    log "Waiting 45s for cloud-init (PostgreSQL install on the DB VMs takes a"
    log "moment) + DHCP leases to settle..."
    sleep 45
  fi

  # HA: clone every standby now so the topology is genuinely fault-tolerant the
  # moment 'start' returns — the registry standby in particular, so the control
  # plane comes up already surviving a registry-primary failover.  Runs BEFORE
  # control-plane provisioning so the registry standby is streaming (in recovery,
  # read-only) when the server first connects — the multi-host DSN's
  # target_session_attrs=read-write then correctly pins writes to the primary.
  # Each provisioning phase is guarded with '|| warn' so that a partial failure
  # (an unreachable VM, a slow SSH, a non-zero setup step) NEVER aborts the run
  # under 'set -e' — the end-of-run summary with every VM's login + IPs must
  # always print.  Individual steps already log their own WARNs.
  if [[ "$HA_MODE" == "1" ]]; then
    echo
    log "=== Building HA standbys (registry + tenant-a + tenant-b) ==="
    ha_autobuild_standbys || warn "standby build hit an error (see above) — continuing to the summary"
  fi

  # Turnkey control plane: stand the whole multi-tenant stack up unattended.
  if [[ "$INCLUDE_CONTROL_PLANE" == "1" && "$PROVISION_CONTROL" == "1" ]]; then
    echo
    log "=== Provisioning the control plane (unattended) ==="
    provision_control_plane || warn "control-plane provisioning hit an error (see above) — continuing to the summary"
  fi

  # One agent per tenant, enrolled via the tenant's token, so each tenant DB gets
  # real host data flowing (and you can watch it survive a per-tenant failover).
  if [[ "$_AGENTS_ON" == "1" ]]; then
    echo
    log "=== Provisioning per-tenant agents (agent-a -> tenant-a, agent-b -> tenant-b) ==="
    provision_agents || warn "agent provisioning hit an error (see above) — continuing to the summary"
  fi

  echo
  echo "=========================================="
  echo "  Post-start summary"
  echo "=========================================="
  echo
  print_ssh_table
  echo "------------------------------------------------------------------------"
  echo "  Per-VM detail"
  echo "------------------------------------------------------------------------"
  echo
  print_vm_summary "$REGISTRY_NAME" "db"      "$REGISTRY_IP" "$REGISTRY_DBNAME"
  print_vm_summary "$SHARED_NAME"   "db"      "$SHARED_IP"   "$SHARED_DBNAME"
  print_vm_summary "$TENANT_A_NAME" "db"      "$TENANT_A_IP" "$TENANT_A_DBNAME"
  print_vm_summary "$TENANT_B_NAME" "db"      "$TENANT_B_IP" "$TENANT_B_DBNAME"
  if [[ "$HA_MODE" == "1" ]]; then
    print_vm_summary "$REGISTRY_STANDBY_NAME" "db-standby" "$REGISTRY_STANDBY_IP" "$REGISTRY_DBNAME"
    print_vm_summary "$TENANT_A_STANDBY_NAME" "db-standby" "$TENANT_A_STANDBY_IP" "$TENANT_A_DBNAME"
    print_vm_summary "$TENANT_B_STANDBY_NAME" "db-standby" "$TENANT_B_STANDBY_IP" "$TENANT_B_DBNAME"
  fi
  if [[ "$INCLUDE_CONTROL_PLANE" == "1" ]]; then
    print_vm_summary "$CONTROL_NAME" "control" "$CONTROL_IP"
  fi
  if [[ "$_AGENTS_ON" == "1" ]]; then
    print_vm_summary "$AGENT_A_NAME" "agent" "$AGENT_A_IP" "tenant-a"
    print_vm_summary "$AGENT_B_NAME" "agent" "$AGENT_B_IP" "tenant-b"
  fi

  echo "Login (all VMs):  user=${USERNAME}  password=${PASSWORD}"
  echo "Postgres role  :  ${DB_ROLE} / ${DBPASS}   (per-VM database, see above)"
  echo
  echo "Multi-tenant network (${MT_NET_NAME}, isolated 10.80.0.0/24):"
  echo "  registry DB : ${REGISTRY_IP}   db=${REGISTRY_DBNAME}"
  echo "  shared DB   : ${SHARED_IP}   db=${SHARED_DBNAME}   (forward-looking; collapses onto bootstrap in 13.1.A)"
  echo "  tenant-a DB : ${TENANT_A_IP}   db=${TENANT_A_DBNAME}"
  echo "  tenant-b DB : ${TENANT_B_IP}   db=${TENANT_B_DBNAME}"
  if [[ "$HA_MODE" == "1" ]]; then
  echo "  reg  stdby  : ${REGISTRY_STANDBY_IP}   (streaming standby of the registry DB — the platform-critical pair)"
  echo "  tnt-a stdby : ${TENANT_A_STANDBY_IP}   (streaming standby of tenant-a)"
  echo "  tnt-b stdby : ${TENANT_B_STANDBY_IP}   (streaming standby of tenant-b — see HA guide below)"
  fi
  [[ "$INCLUDE_CONTROL_PLANE" == "1" ]] && \
  echo "  control     : ${CONTROL_IP}  (sysmanage server + OpenBAO)"
  if [[ "$_AGENTS_ON" == "1" ]]; then
  echo "  agent-a     : ${AGENT_A_IP}   (sysmanage-agent enrolled into tenant-a)"
  echo "  agent-b     : ${AGENT_B_IP}   (sysmanage-agent enrolled into tenant-b)"
  fi
  echo "  host        : ${MT_NET_HOST_IP}    (SSH from here:  ssh ${USERNAME}@${REGISTRY_IP})"
  echo
  if [[ "$INCLUDE_CONTROL_PLANE" == "1" && "$PROVISION_CONTROL" == "1" ]]; then
    echo "=========================================="
    echo "  Control plane provisioned automatically"
    echo "=========================================="
    echo "  Web UI  : http://${CONTROL_IP}:3000     (from your host's browser)"
    echo "  API     : http://${CONTROL_IP}:8080"
    echo "  Login   : ${CONTROL_ADMIN_USER} / ${CONTROL_ADMIN_PW}"
    echo "  License : self-signed ${CONTROL_TIER} (multitenancy_engine loaded; phone-home disabled)"
    echo "  Tenants : tenant-a (${TENANT_A_IP}/${TENANT_A_DBNAME}) + tenant-b (${TENANT_B_IP}/${TENANT_B_DBNAME}) created, placed + migrated"
    if [[ "$_AGENTS_ON" == "1" ]]; then
    echo "  Agents  : agent-a (${AGENT_A_IP}) enrolled into tenant-a, agent-b (${AGENT_B_IP}) into tenant-b"
    echo "            -> each tenant DB now gets real host data; switch tenants in the UI to see it."
    fi
    echo "  Setup log on the VM:  /var/log/sysmanage-control-setup.log"
    echo "  (Re-run just this step:  ssh ${USERNAME}@${CONTROL_IP} 'sudo bash /home/${USERNAME}/control-setup.sh')"
    echo
    if [[ "$_AGENTS_ON" != "1" ]]; then
    echo "  To bind a host to a tenant: issue a tenant-scoped enrollment token"
    echo "  (Settings -> Tenants) and drop it in that agent's security.enrollment_token."
    echo
    fi
  else
    print_wiring_guide
  fi
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
             "$REGISTRY_STANDBY_NAME" "$TENANT_A_STANDBY_NAME" "$TENANT_B_STANDBY_NAME" \
             "$CONTROL_NAME" "$AGENT_A_NAME" "$AGENT_B_NAME")
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
  if vm_exists "$REGISTRY_STANDBY_NAME"; then
    print_vm_status "$REGISTRY_STANDBY_NAME" "$REGISTRY_STANDBY_IP"
  fi
  if vm_exists "$TENANT_A_STANDBY_NAME"; then
    print_vm_status "$TENANT_A_STANDBY_NAME" "$TENANT_A_STANDBY_IP"
  fi
  if vm_exists "$TENANT_B_STANDBY_NAME"; then
    print_vm_status "$TENANT_B_STANDBY_NAME" "$TENANT_B_STANDBY_IP"
  fi
  print_vm_status "$CONTROL_NAME"  "$CONTROL_IP"
  if vm_exists "$AGENT_A_NAME"; then print_vm_status "$AGENT_A_NAME" "$AGENT_A_IP"; fi
  if vm_exists "$AGENT_B_NAME"; then print_vm_status "$AGENT_B_NAME" "$AGENT_B_IP"; fi

  echo
  echo "Login: user=${USERNAME}  password=${PASSWORD}   |   Postgres: ${DB_ROLE}/${DBPASS}"
}

# HA-mode addendum: how to exercise the failovers.  Printed by cmd_start when --ha.
print_ha_guide() {
  cat <<EOF
==========================================================================
  HA mode — every live DB has a streaming standby (Phase 15.1)
==========================================================================
'start' already CLONED and verified all three standbys (registry, tenant-a,
tenant-b), so the topology is fault-tolerant right now — no single DB box can
take the platform down.  The pairs:

  registry : ${REGISTRY_IP}  (primary)  +  ${REGISTRY_STANDBY_IP}  (standby)   <- platform-critical
  tenant-a : ${TENANT_A_IP}  (primary)  +  ${TENANT_A_STANDBY_IP}  (standby)
  tenant-b : ${TENANT_B_IP}  (primary)  +  ${TENANT_B_STANDBY_IP}  (standby)

THE HEADLINE TEST — kill the registry primary, platform stays up:

     $0 failover registry     # stop ${REGISTRY_IP}, promote ${REGISTRY_STANDBY_IP}

  The control plane keeps serving with NO manual step: its registry DSN is the
  libpq multi-host list (host="${REGISTRY_IP},${REGISTRY_STANDBY_IP}"
  target_session_attrs=read-write) and every engine has pool_pre_ping, so dead
  pooled connections are discarded and re-resolved to the promoted node.  Reload
  the UI at http://${CONTROL_IP}:3000 — it stays up.  Then repair replication:

     $0 failback registry     # rebuild ${REGISTRY_IP} as a fresh streaming standby

PER-TENANT failover is now automatic too (target tenant-a / tenant-b):

     $0 failover tenant-a     # stop + promote tenant-a's standby
     $0 failback tenant-a

  Each tenant is PLACED at its primary+standby pair (libpq multi-host), so the
  tenant's per-request engine survives a tenant-DB failover the same way the
  registry does: the engine's DSN builder appends target_session_attrs=read-write
  for a multi-host placement and every tenant engine has pool_pre_ping, so dead
  connections re-resolve to the promoted node.  OpenBAO's own admin connection is
  pointed at the pair too, so it keeps minting tenant creds after a failover.
  (Caveat: that last part needs OpenBAO's postgres plugin to honor libpq
  multi-host — modern pgx-based builds do; if yours is lib/pq, front the tenant
  pair with a VIP/proxy and use that single address in the OpenBAO connection_url.)

status shows each node's role:  $0 status
==========================================================================
EOF
}

# Resolve an HA pair label -> "primary_ip standby_ip dbname" (from HA_PAIRS).
_ha_resolve() {
  local want="$1" entry label pip sip db
  for entry in "${HA_PAIRS[@]}"; do
    read -r label pip sip db <<<"$entry"
    if [[ "$label" == "$want" ]]; then echo "$pip $sip $db"; return 0; fi
  done
  return 1
}

# Space-separated list of HA target labels (for usage / errors).
_ha_labels() { local e l; for e in "${HA_PAIRS[@]}"; do read -r l _ <<<"$e"; printf '%s ' "$l"; done; }

# Core: (re)build <rebuild_ip> as a fresh streaming standby of <primary_ip>.
# Returns 0 iff streaming is verified.  Shared by failback + the start auto-clone.
_ha_rebuild_standby() {
  local label="$1" primary_ip="$2" rebuild_ip="$3" ver st i
  ver="$(pg_version "$primary_ip")"
  [[ -n "$ver" ]] || { warn "[$label] can't determine PostgreSQL version on primary ${primary_ip}"; return 1; }
  log "[$label] rebuilding ${rebuild_ip} as a streaming standby of ${primary_ip} (pg ${ver})"
  # .pgpass BEFORE start: pg_basebackup -R omits the password from
  # primary_conninfo, so ongoing WAL streaming can't auth under scram — without it
  # the base backup succeeds but streaming silently never starts, and a later
  # failover promotes a frozen snapshot missing every post-clone write.
  ha_ssh "$rebuild_ip" "\
    sudo systemctl stop postgresql; \
    sudo -u postgres rm -rf /var/lib/postgresql/${ver}/main; \
    sudo -u postgres bash -c 'umask 077; echo \"*:*:*:${REPL_ROLE}:${REPL_PASS}\" > ~/.pgpass'; \
    sudo -u postgres bash -c 'PGPASSWORD=\"${REPL_PASS}\" pg_basebackup -h ${primary_ip} -U ${REPL_ROLE} -D /var/lib/postgresql/${ver}/main -R -X stream -P'; \
    sudo systemctl start postgresql" \
    || { warn "[$label] rebuild of ${rebuild_ip} failed (check ${REPL_ROLE} role + 'host replication' pg_hba on ${primary_ip})"; return 1; }
  log "[$label] waiting for ${rebuild_ip} to reach streaming replication..."
  st=""
  for i in $(seq 1 30); do
    st="$(ha_ssh "$rebuild_ip" "sudo -u postgres psql -tAc \"SELECT status FROM pg_stat_wal_receiver\"" 2>/dev/null | tr -d '[:space:]')"
    [[ "$st" == "streaming" ]] && break
    sleep 2
  done
  if [[ "$st" == "streaming" ]]; then
    log "[$label] streaming verified — primary=${primary_ip}, standby=${rebuild_ip}"
    return 0
  fi
  warn "[$label] ${rebuild_ip} is NOT streaming (pg_stat_wal_receiver='${st:-<empty>}'); a failover now would lose writes."
  return 1
}

# Clone EVERY HA standby at bring-up so the topology is genuinely HA the moment
# 'start' finishes — the registry standby especially, so the control plane comes
# up already able to survive a registry failover.  Waits for each primary first.
ha_autobuild_standbys() {
  check_ssh_deps
  local entry label pip sip db i
  for entry in "${HA_PAIRS[@]}"; do
    read -r label pip sip db <<<"$entry"
    log "[$label] waiting for primary ${pip} to accept connections..."
    for i in $(seq 1 60); do
      [[ "$(pg_role "$pip")" == "primary" ]] && break
      sleep 5
    done
    if [[ "$(pg_role "$sip")" == "standby" ]]; then
      log "[$label] standby ${sip} already streaming — skipping"
      continue
    fi
    _ha_rebuild_standby "$label" "$pip" "$sip" || warn "[$label] initial standby build did not verify (see above)"
  done
}

# failover [target]   target = registry (default) | tenant-a | tenant-b
cmd_failover() {
  check_deps
  check_ssh_deps
  [[ "$HA_MODE" == "1" ]] || warn "failover assumes the --ha topology."
  local target="${1:-registry}" pair p_ip s_ip db a_role s_role primary_ip standby_ip ver
  pair="$(_ha_resolve "$target")" || die "unknown HA target '$target'.  Available: $(_ha_labels)"
  read -r p_ip s_ip db <<<"$pair"
  a_role="$(pg_role "$p_ip")"; s_role="$(pg_role "$s_ip")"
  log "[$target] roles: ${p_ip}=${a_role}, ${s_ip}=${s_role}"

  if [[ "$a_role" == "primary" && "$s_role" == "standby" ]]; then
    primary_ip="$p_ip"; standby_ip="$s_ip"
  elif [[ "$s_role" == "primary" && "$a_role" == "standby" ]]; then
    primary_ip="$s_ip"; standby_ip="$p_ip"
  else
    die "[$target] need one primary + one standby (got ${a_role}/${s_role}).  Run '$0 failback $target' first."
  fi

  log "[$target] stopping the primary at ${primary_ip} (simulating its loss)"
  ha_ssh "$primary_ip" "sudo systemctl stop postgresql" \
    || warn "primary stop returned non-zero (already down?)"
  ver="$(pg_version "$standby_ip")"
  [[ -n "$ver" ]] || die "couldn't determine PostgreSQL version on standby ${standby_ip}"
  log "[$target] promoting the standby at ${standby_ip} (pg ${ver})"
  ha_ssh "$standby_ip" "sudo pg_ctlcluster ${ver} main promote" \
    || die "promote failed on ${standby_ip}"

  echo
  log "[$target] failover complete — ${standby_ip} is now the ${target} primary."
  if [[ "$target" == "registry" ]]; then
    log "The control plane should keep serving with NO manual step: its registry DSN is"
    log "the libpq multi-host list (target_session_attrs=read-write) + pool_pre_ping, so"
    log "dead pooled connections are discarded and re-resolved to the promoted node."
    log "This is the proof point — one DB box died and the whole platform stayed up."
  else
    log "The OpenBAO lease-acquisition retry (Phase 15.1) covers minting ${target} creds through the gap."
  fi
  log "Repair replication when ready:  $0 failback $target"
}

# failback [target]   rebuild the non-primary node as a fresh streaming standby.
cmd_failback() {
  check_deps
  check_ssh_deps
  local target="${1:-registry}" pair p_ip s_ip db a_role s_role primary_ip rebuild_ip
  pair="$(_ha_resolve "$target")" || die "unknown HA target '$target'.  Available: $(_ha_labels)"
  read -r p_ip s_ip db <<<"$pair"
  a_role="$(pg_role "$p_ip")"; s_role="$(pg_role "$s_ip")"
  log "[$target] roles: ${p_ip}=${a_role}, ${s_ip}=${s_role}"

  if [[ "$a_role" == "primary" ]]; then
    primary_ip="$p_ip"; rebuild_ip="$s_ip"
  elif [[ "$s_role" == "primary" ]]; then
    primary_ip="$s_ip"; rebuild_ip="$p_ip"
  else
    die "[$target] no primary is up (${a_role}/${s_role}) — start the ${target} primary before failback."
  fi

  _ha_rebuild_standby "$target" "$primary_ip" "$rebuild_ip"
  log "[$target] inspect on the primary:  ssh ${USERNAME}@${primary_ip} sudo -u postgres psql -c 'select * from pg_stat_replication;'"
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
  failover [target]  (HA) Stop <target>'s current primary + promote its standby.
            target = registry (default) | tenant-a | tenant-b.  The registry
            case is the headline: the control plane keeps serving with no manual
            step (multi-host DSN + pool_pre_ping).
  failback [target]  (HA) Rebuild the non-primary node as a fresh streaming
            standby of <target> (same targets; also the one-time initial clone).

Options:
  --ha      Give the registry, tenant-a AND tenant-b DBs a streaming standby
            each (so every live DB survives a single-box loss — no SaaS platform
            can accept one DB failure taking the whole thing down) and enable
            failover/failback.  'start' auto-clones the standbys so the topology
            is HA immediately, and the control plane connects to the registry via
            a libpq multi-host DSN.  (Also settable with HA=1.)  Needs 'sshpass'.

Key environment overrides:
  INCLUDE_CONTROL_PLANE=0   Skip the server+OpenBAO VM (run sysmanage from your host).
  PROVISION_CONTROL=0       Leave the control plane bare (print the manual wiring guide).
  PROVISION_AGENTS=0        Skip the per-tenant agent VMs (no live tenant data).
  DB_RAM / DB_DISK_GB       Resize the DB VMs (default 2048 MiB / 20 GiB).
  DBPASS                    PostgreSQL role password (default SysMgrTest123).
EOF
}

main() {
  case "${1:-}" in
    start)    cmd_start ;;
    stop)     cmd_stop ;;
    status)   cmd_status ;;
    failover) cmd_failover "${2:-}" ;;
    failback) cmd_failback "${2:-}" ;;
    -h|--help|help|"") usage ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
