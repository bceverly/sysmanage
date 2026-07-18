#!/usr/bin/env bash
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# buildPostgresHATestNetwork.sh — Provision four KVM VMs for testing the
# SysManage server against a highly-available PostgreSQL cluster (Phase 15.1)
# on libvirt/KVM.
#
#   sysmanage-server      — The SysManage app server.  Dual-homed: a NAT NIC
#                           for internet (install sysmanage from the PPA) plus
#                           a static 10.90.0.10 on the isolated sysmanage-ha
#                           bridge.  Its /etc/sysmanage.yaml database points at
#                           BOTH database nodes via a libpq multi-host DSN, so
#                           it always reaches whichever is the current primary.
#   sysmanage-pg-primary  — PostgreSQL primary (static 10.90.0.20).  Owns the
#                           sysmanage database and streams WAL to the standby.
#   sysmanage-pg-standby  — PostgreSQL standby (static 10.90.0.21), a streaming-
#                           replication replica of the primary.  Promote it (or
#                           let a cluster manager promote it) to exercise the
#                           failover path.
#   sysmanage-ha-agent    — A sysmanage-agent (static 10.90.0.30) that registers
#                           with the server, so a live workload keeps hitting the
#                           database while you kill the primary.
#
# Usage:
#   scripts/buildPostgresHATestNetwork.sh start    # create + start (idempotent)
#   scripts/buildPostgresHATestNetwork.sh stop     # destroy + undefine + delete disks
#   scripts/buildPostgresHATestNetwork.sh status   # show VM/network state + IPs
#
# Uses the Ubuntu 26.04 server cloud image + cloud-init.  cloud-init now does
# the ENTIRE setup automatically on first boot — PostgreSQL primary + streaming
# standby, sysmanage (from the PPA) with a ready-to-use /etc/sysmanage.yaml
# (multi-host DSN, generated jwt/salt, admin login, email enabled) + migrations,
# and the agent — with wait-loops so the primary->standby->server->agent order
# can't race.  Each node also gets an idempotent ~/setup.sh (the exact same
# steps) that you can re-run by hand:  bash ~/setup.sh  .  Watch progress with
#   tail -f /var/log/sysmanage-setup.log   (or  cloud-init status --wait ).
# Default login once the server node finishes:  admin@sysmanage.org / SysManage!2026
#
# All four VMs share credentials:
#   user     = ubuntu
#   password = Ubuntu123$
#
# Requirements on the host:
#   sudo apt install libvirt-clients libvirt-daemon-system virtinst \
#                    qemu-utils qemu-system-x86 cloud-image-utils curl python3-gi
#
# Browser access.  The isolated sysmanage-ha bridge gives THIS host an IP on
# the same 10.90.0.x subnet (10.90.0.254), so you point your local browser
# straight at the server's static address — no SSH tunnel or port-forward
# needed.  Open  https://10.90.0.10:<web-port>  once sysmanage is installed.
#
# Resource sizing.  Disk sizes are the maximum the VM filesystem can grow to —
# qcow2 is thin-allocated so unused space doesn't actually consume host disk.
#   server      : 2 vCPU / 4 GiB RAM / 40 GiB disk  (backend + OpenBAO; the DB
#                 is external now, so no postgres here)
#   pg-primary  : 2 vCPU / 2 GiB RAM / 40 GiB disk  (PostgreSQL only)
#   pg-standby  : 2 vCPU / 2 GiB RAM / 40 GiB disk  (PostgreSQL only)
#   ha-agent    : 1 vCPU / 2 GiB RAM / 20 GiB disk  (OS + agent; 1 GiB OOM'd
#                 the agent during package/update-detection collection)
# ~10 GiB of guest RAM total; bump/shrink any node via the environment
# variables below if your host is tight.

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

# Default PostgreSQL major version shipped by UBUNTU_VERSION (26.04 -> 18).
# Used only in the printed manual-setup / failover instructions so they show a
# real, copy-pasteable version instead of a bare placeholder. The actual
# failover/failback commands derive the live version via pg_version(). If you
# bump UBUNTU_VERSION to a release with a different default PostgreSQL, update
# this to match (or export PG_VER=NN).
PG_VER="${PG_VER:-18}"

USERNAME="ubuntu"
PASSWORD='Ubuntu123$'

# Isolated bridge for the HA cluster network.  Every VM keeps a NAT NIC for
# internet (so sysmanage/postgres install from apt/the PPA) AND a static NIC on
# this bridge, which gives the nodes stable, known addresses for replication and
# the server's multi-host DSN.  The host gets an IP on the bridge too, so you
# can SSH into any node over 10.90.0.x and browse the UI from this machine.
HA_NET_NAME="${HA_NET_NAME:-sysmanage-ha}"
HA_NET_BRIDGE="${HA_NET_BRIDGE:-virbr90}"
HA_NET_HOST_IP="${HA_NET_HOST_IP:-10.90.0.254}"
HA_NET_MASK="${HA_NET_MASK:-255.255.255.0}"

SERVER_NAME="${SERVER_NAME:-sysmanage-server}"
SERVER_VCPUS="${SERVER_VCPUS:-2}"
SERVER_RAM="${SERVER_RAM:-4096}"
SERVER_DISK_GB="${SERVER_DISK_GB:-40}"
SERVER_NAT_MAC="${SERVER_NAT_MAC:-52:54:00:90:50:00}"
SERVER_HA_MAC="${SERVER_HA_MAC:-52:54:00:90:00:10}"
SERVER_IP="${SERVER_IP:-10.90.0.10}"

PGP_NAME="${PGP_NAME:-sysmanage-pg-primary}"
PGP_VCPUS="${PGP_VCPUS:-2}"
PGP_RAM="${PGP_RAM:-2048}"
PGP_DISK_GB="${PGP_DISK_GB:-40}"
PGP_NAT_MAC="${PGP_NAT_MAC:-52:54:00:90:50:01}"
PGP_HA_MAC="${PGP_HA_MAC:-52:54:00:90:00:20}"
PGP_IP="${PGP_IP:-10.90.0.20}"

PGS_NAME="${PGS_NAME:-sysmanage-pg-standby}"
PGS_VCPUS="${PGS_VCPUS:-2}"
PGS_RAM="${PGS_RAM:-2048}"
PGS_DISK_GB="${PGS_DISK_GB:-40}"
PGS_NAT_MAC="${PGS_NAT_MAC:-52:54:00:90:50:02}"
PGS_HA_MAC="${PGS_HA_MAC:-52:54:00:90:00:21}"
PGS_IP="${PGS_IP:-10.90.0.21}"

AGENT_NAME="${AGENT_NAME:-sysmanage-ha-agent}"
AGENT_VCPUS="${AGENT_VCPUS:-1}"
# 2 GiB: at 1 GiB the agent's Python process OOM-kills in a crash-restart loop
# during its package/update-detection collection.  Override with AGENT_RAM=<MiB>.
AGENT_RAM="${AGENT_RAM:-2048}"
AGENT_DISK_GB="${AGENT_DISK_GB:-20}"
AGENT_NAT_MAC="${AGENT_NAT_MAC:-52:54:00:90:50:03}"
AGENT_HA_MAC="${AGENT_HA_MAC:-52:54:00:90:00:30}"
AGENT_IP="${AGENT_IP:-10.90.0.30}"

# The sysmanage database credentials the server's DSN will use, and the
# replication role the standby uses to stream from the primary.  Printed into
# the setup instructions so the primary-setup and server-config match.
DB_NAME="${DB_NAME:-sysmanage}"
DB_USER="${DB_USER:-sysmanage}"
DB_PASSWORD="${DB_PASSWORD:-abc123}"
REPL_USER="${REPL_USER:-replicator}"
REPL_PASSWORD="${REPL_PASSWORD:-repl123}"

VM_NAMES=("$SERVER_NAME" "$PGP_NAME" "$PGS_NAME" "$AGENT_NAME")

WORKDIR="$(mktemp -d -t sysmanage-ha-XXXXXX)"
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
  # to dodge the venv issue, so test gi against the same system interpreter here.
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

ensure_ha_network() {
  if virsh_ net-info "$HA_NET_NAME" >/dev/null 2>&1; then
    log "network $HA_NET_NAME: already defined"
  else
    log "network $HA_NET_NAME: defining isolated bridge $HA_NET_BRIDGE"
    local xml="$WORKDIR/${HA_NET_NAME}.xml"
    cat > "$xml" <<EOF
<network>
  <name>${HA_NET_NAME}</name>
  <bridge name='${HA_NET_BRIDGE}' stp='on' delay='0'/>
  <ip address='${HA_NET_HOST_IP}' netmask='${HA_NET_MASK}'/>
</network>
EOF
    virsh_ net-define "$xml" >/dev/null
  fi
  net_is_active    "$HA_NET_NAME" || virsh_ net-start     "$HA_NET_NAME" >/dev/null
  net_is_autostart "$HA_NET_NAME" || virsh_ net-autostart "$HA_NET_NAME" >/dev/null
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

# emit_setup_script <role> -> the full, idempotent ~/setup.sh for that node.
# Structure: a literal head (re-exec under sudo + logging), then a host-expanded
# config block (bakes in IPs/creds ONCE), then a per-role body that is fully
# literal (so nothing gets re-expanded at author time). Every node's script is
# safe to re-run by hand:  bash ~/setup.sh
emit_setup_script() {
  local role="$1"
  cat <<'HEAD'
#!/usr/bin/env bash
# Auto-generated by buildPostgresHATestNetwork.sh — idempotent; re-runnable:
#   bash ~/setup.sh          (re-execs itself under sudo)
# Progress is logged to /var/log/sysmanage-setup.log.
set -euo pipefail
if [ "${EUID:-$(id -u)}" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
mkdir -p /var/log
exec > >(tee -a /var/log/sysmanage-setup.log) 2>&1
export DEBIAN_FRONTEND=noninteractive
HEAD
  cat <<EOF
DB_USER='${DB_USER}'; DB_PASSWORD='${DB_PASSWORD}'; DB_NAME='${DB_NAME}'
REPL_USER='${REPL_USER}'; REPL_PASSWORD='${REPL_PASSWORD}'
PGP_IP='${PGP_IP}'; PGS_IP='${PGS_IP}'; SERVER_IP='${SERVER_IP}'
EOF
  case "$role" in
    pg-primary) cat <<'BODY'
echo "=== [$(date)] pg-primary setup ==="
apt-get update -y
apt-get install -y postgresql
PGVER="$(ls -1 /etc/postgresql 2>/dev/null | sort -n | tail -1)"
[ -n "$PGVER" ] || { echo "postgresql not installed"; exit 1; }
CONF="/etc/postgresql/$PGVER/main/postgresql.conf"
HBA="/etc/postgresql/$PGVER/main/pg_hba.conf"
grep -q 'sysmanage-ha' "$CONF" || printf "\n# sysmanage-ha\nlisten_addresses = '*'\nwal_level = replica\nmax_wal_senders = 10\nhot_standby = on\n" >> "$CONF"
grep -q 'sysmanage-ha' "$HBA"  || printf "# sysmanage-ha\nhost all %s 10.90.0.0/24 scram-sha-256\nhost replication %s 10.90.0.0/24 scram-sha-256\n" "$DB_USER" "$REPL_USER" >> "$HBA"
systemctl restart postgresql
S() { sudo -u postgres psql -v ON_ERROR_STOP=1 -tAc "$1"; }
C() { sudo -u postgres psql -v ON_ERROR_STOP=1 -c "$1"; }
S "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'"     | grep -q 1 || C "CREATE ROLE \"$DB_USER\" LOGIN PASSWORD '$DB_PASSWORD'"
S "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'"  | grep -q 1 || C "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\""
S "SELECT 1 FROM pg_roles WHERE rolname='$REPL_USER'"   | grep -q 1 || C "CREATE ROLE \"$REPL_USER\" LOGIN REPLICATION PASSWORD '$REPL_PASSWORD'"
# Give this node a .pgpass too, so when it is later rebuilt as a standby (after a
# failover + failback) its WAL receiver can authenticate. Survives rm -rf of the
# data dir (it lives in the postgres home, not the data dir).
sudo -u postgres bash -c "umask 077; printf '*:*:*:%s:%s\n' '$REPL_USER' '$REPL_PASSWORD' > ~/.pgpass"
echo "=== pg-primary ready ==="
BODY
    ;;
    pg-standby) cat <<'BODY'
echo "=== [$(date)] pg-standby setup ==="
apt-get update -y
apt-get install -y postgresql
PGVER="$(ls -1 /etc/postgresql 2>/dev/null | sort -n | tail -1)"
[ -n "$PGVER" ] || { echo "postgresql not installed"; exit 1; }
DATADIR="/var/lib/postgresql/$PGVER/main"
# CRITICAL: postgresql.conf/pg_hba.conf live in /etc, which pg_basebackup does
# NOT copy (it only copies the data dir). Without this the standby keeps its
# default listen_addresses='localhost', so once promoted it's unreachable on the
# network (10.90.0.21:5432 refused) and the app can't fail over to it. Apply the
# same listen + pg_hba config the primary got, so this node is reachable both as
# a standby and after promotion.
CONF="/etc/postgresql/$PGVER/main/postgresql.conf"
HBA="/etc/postgresql/$PGVER/main/pg_hba.conf"
grep -q 'sysmanage-ha' "$CONF" || printf "\n# sysmanage-ha\nlisten_addresses = '*'\nwal_level = replica\nmax_wal_senders = 10\nhot_standby = on\n" >> "$CONF"
grep -q 'sysmanage-ha' "$HBA"  || printf "# sysmanage-ha\nhost all %s 10.90.0.0/24 scram-sha-256\nhost replication %s 10.90.0.0/24 scram-sha-256\n" "$DB_USER" "$REPL_USER" >> "$HBA"
if sudo -u postgres psql -tAc "SELECT pg_is_in_recovery()" 2>/dev/null | grep -qx t; then
  echo "already a streaming standby; nothing to do"; exit 0
fi
echo "waiting for primary $PGP_IP to accept replication (up to ~15m)..."
for i in $(seq 1 90); do
  if PGPASSWORD="$REPL_PASSWORD" psql "host=$PGP_IP port=5432 user=$REPL_USER replication=1" -tAc "IDENTIFY_SYSTEM" >/dev/null 2>&1; then
    echo "primary replication ready"; break
  fi
  echo "  ...waiting ($i)"; sleep 10
done
# A .pgpass for the postgres user is REQUIRED for ongoing streaming:
# pg_basebackup -R writes primary_conninfo WITHOUT the password, so the WAL
# receiver can't authenticate against the scram pg_hba and streaming silently
# never establishes (the standby would freeze at basebackup time). '*:*:*' so it
# works regardless of which node is primary (survives failover/failback).
sudo -u postgres bash -c "umask 077; printf '*:*:*:%s:%s\n' '$REPL_USER' '$REPL_PASSWORD' > ~/.pgpass"
systemctl stop postgresql
sudo -u postgres bash -c "rm -rf '$DATADIR'"
sudo -u postgres bash -c "PGPASSWORD='$REPL_PASSWORD' pg_basebackup -h '$PGP_IP' -U '$REPL_USER' -D '$DATADIR' -R -X stream -P"
systemctl start postgresql
# Verify streaming actually established (not just that basebackup succeeded) —
# a silent auth failure here is what leaves the standby frozen at basebackup.
for i in $(seq 1 12); do
  st="$(sudo -u postgres psql -tAc "SELECT status FROM pg_stat_wal_receiver" 2>/dev/null | tr -d '[:space:]')"
  [ "$st" = streaming ] && break
  sleep 5
done
if [ "${st:-}" = streaming ]; then
  echo "=== pg-standby STREAMING from $PGP_IP (verified) ==="
else
  echo "!!! pg-standby is NOT streaming (status='${st:-none}') — check .pgpass / primary_conninfo / pg_hba on $PGP_IP"
  sudo -u postgres psql -c "SELECT * FROM pg_stat_wal_receiver" 2>/dev/null || true
fi
BODY
    ;;
    server) cat <<'BODY'
echo "=== [$(date)] server setup ==="
apt-get update -y
apt-get install -y software-properties-common postgresql-client curl openssl
add-apt-repository -y ppa:bceverly/sysmanage
apt-get update -y
apt-get install -y sysmanage
echo "waiting for a read-write DB at $PGP_IP,$PGS_IP (up to ~15m)..."
for i in $(seq 1 90); do
  if PGPASSWORD="$DB_PASSWORD" psql "host=$PGP_IP,$PGS_IP port=5432 user=$DB_USER dbname=$DB_NAME target_session_attrs=read-write" -tAc "SELECT 1" >/dev/null 2>&1; then
    echo "database reachable (read-write)"; break
  fi
  echo "  ...waiting ($i)"; sleep 10
done
JWT="$(openssl rand -hex 32)"; SALT="$(openssl rand -hex 16)"
DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_NAME="$DB_NAME" PGP_IP="$PGP_IP" PGS_IP="$PGS_IP" JWT="$JWT" SALT="$SALT" \
/opt/sysmanage/.venv/bin/python <<'PY'
import os, yaml
p = '/etc/sysmanage.yaml'; c = {}
if os.path.exists(p):
    with open(p) as f: c = yaml.safe_load(f) or {}
c['database'] = {**c.get('database', {}), 'user': os.environ['DB_USER'], 'password': os.environ['DB_PASSWORD'],
                 'host': os.environ['PGP_IP'] + ',' + os.environ['PGS_IP'], 'port': 5432,
                 'name': os.environ['DB_NAME'], 'options': 'target_session_attrs=read-write'}
c['registry'] = dict(c['database'])
c['security'] = {**c.get('security', {}), 'admin_userid': 'admin@sysmanage.org', 'admin_password': 'SysManage!2026',
                 'jwt_secret': os.environ['JWT'], 'password_salt': os.environ['SALT'], 'jwt_algorithm': 'HS256'}
c['email'] = {**c.get('email', {}), 'enabled': True}
c['api'] = {**c.get('api', {}), 'host': '0.0.0.0', 'port': 8080}
c['api'].pop('certFile', None); c['api'].pop('keyFile', None)  # plain HTTP:8080 so the agent (ws://:8080) connects
with open(p, 'w') as f: yaml.safe_dump(c, f, default_flow_style=False, sort_keys=False)
print('patched', p)
PY
cd /opt/sysmanage
sudo -u sysmanage .venv/bin/python -m alembic upgrade head
systemctl restart sysmanage 2>/dev/null || systemctl start sysmanage
echo "=== server ready -> log in as admin@sysmanage.org / SysManage!2026 ==="
BODY
    ;;
    agent) cat <<'BODY'
echo "=== [$(date)] agent setup ==="
apt-get update -y
apt-get install -y software-properties-common
add-apt-repository -y ppa:bceverly/sysmanage-agent
apt-get update -y
apt-get install -y sysmanage-agent
# The agent builds ws://hostname:port/api/agent/connect from server.hostname /
# server.port / server.use_https (it IGNORES a server.url key). The PPA ships a
# stale sample with only server.url, so write a correct config from scratch.
# Everything else has sane defaults in the agent, so a minimal file is enough.
cat > /etc/sysmanage-agent.yaml <<CFG
# Generated by buildPostgresHATestNetwork.sh (matches the SysManage config builder)

server:
  hostname: $SERVER_IP
  port: 8080
  use_https: false
  verify_ssl: false

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
echo "=== agent config written -> ws://$SERVER_IP:8080/api/agent/connect; retries until the server is up ==="
BODY
    ;;
    *) echo 'echo "no automated setup for this role"' ;;
  esac
}

write_user_data() {
  local host="$1" out="$2"
  local role
  case "$host" in
    "$SERVER_NAME") role=server ;;
    "$PGP_NAME")    role=pg-primary ;;
    "$PGS_NAME")    role=pg-standby ;;
    "$AGENT_NAME")  role=agent ;;
    *)              role=none ;;
  esac
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
EOF
  if [ "$role" != none ]; then
    local setup_b64
    setup_b64="$(emit_setup_script "$role" | base64 -w0)"
    # Write to /root (always exists; avoids the write-files-runs-before-
    # users-groups ordering trap where /home/${USERNAME} doesn't exist yet).
    # runcmd runs in the final stage, after the user exists, so it can copy the
    # script into ~ for convenient manual re-runs — but we execute it from /root.
    cat >> "$out" <<EOF
write_files:
  - path: /root/setup.sh
    owner: root:root
    permissions: '0755'
    encoding: b64
    content: ${setup_b64}
runcmd:
  - systemctl enable --now ssh
  - install -m 0755 -o ${USERNAME} -g ${USERNAME} /root/setup.sh /home/${USERNAME}/setup.sh || true
  - bash /root/setup.sh
EOF
  else
    cat >> "$out" <<EOF
runcmd:
  - systemctl enable --now ssh
EOF
  fi
}

write_meta_data() {
  local host="$1" out="$2"
  cat > "$out" <<EOF
instance-id: iid-${host}
local-hostname: ${host}
EOF
}

# Dual-NIC netplan: eth0 = NAT NIC (DHCP, carries the default route so the
# node has internet), eth1 = HA NIC (static /24 on the isolated bridge, no
# gateway).  Inter-node traffic to 10.90.0.x is directly connected over eth1;
# everything else exits via eth0's default route.
# $1: NAT MAC.  $2: HA MAC.  $3: HA static IPv4 (no CIDR).  $4: output file.
write_network_config() {
  local nat_mac="$1" ha_mac="$2" ha_ip="$3" out="$4"
  cat > "$out" <<EOF
version: 2
ethernets:
  nat0:
    match:
      macaddress: "${nat_mac}"
    set-name: eth0
    dhcp4: true
  ha0:
    match:
      macaddress: "${ha_mac}"
    set-name: eth1
    dhcp4: false
    addresses:
      - ${ha_ip}/24
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

# provision_vm <name> <vcpus> <ram> <disk_gb> <nat_mac> <ha_mac> <ha_ip>
# Every node is dual-homed: a NAT NIC for internet + a static NIC on the
# ${HA_NET_NAME} bridge.
provision_vm() {
  local name="$1" vcpus="$2" ram="$3" disk_gb="$4"
  local nat_mac="$5" ha_mac="$6" ha_ip="$7"

  local ud="$WORKDIR/${name}-user-data"
  local md="$WORKDIR/${name}-meta-data"
  local nc="$WORKDIR/${name}-network-config"
  write_user_data    "$name" "$ud"
  write_meta_data    "$name" "$md"
  write_network_config "$nat_mac" "$ha_mac" "$ha_ip" "$nc"

  local seed_path="${IMG_POOL}/${name}-seed.iso"
  build_seed_iso "$ud" "$md" "$nc" "$seed_path"

  local disk_path="${IMG_POOL}/${name}.qcow2"
  create_disk "$disk_path" "$disk_gb"

  log "Defining $name (vcpus=$vcpus ram=${ram}M disk=${disk_gb}G nat=$nat_mac ha=$ha_mac/$ha_ip)"
  virt_install_ --connect "$LIBVIRT_URI" \
    --name "$name" \
    --vcpus "$vcpus" \
    --memory "$ram" \
    --osinfo "$OS_VARIANT" \
    --disk "path=${disk_path},format=qcow2,bus=virtio" \
    --disk "path=${seed_path},device=cdrom,bus=sata" \
    --network "network=default,model=virtio,mac=${nat_mac}" \
    --network "network=${HA_NET_NAME},model=virtio,mac=${ha_mac}" \
    --graphics none \
    --console pty,target_type=serial \
    --noautoconsole \
    --import
}

create_server() {
  provision_vm "$SERVER_NAME" "$SERVER_VCPUS" "$SERVER_RAM" "$SERVER_DISK_GB" \
    "$SERVER_NAT_MAC" "$SERVER_HA_MAC" "$SERVER_IP"
}
create_pg_primary() {
  provision_vm "$PGP_NAME" "$PGP_VCPUS" "$PGP_RAM" "$PGP_DISK_GB" \
    "$PGP_NAT_MAC" "$PGP_HA_MAC" "$PGP_IP"
}
create_pg_standby() {
  provision_vm "$PGS_NAME" "$PGS_VCPUS" "$PGS_RAM" "$PGS_DISK_GB" \
    "$PGS_NAT_MAC" "$PGS_HA_MAC" "$PGS_IP"
}
create_agent() {
  provision_vm "$AGENT_NAME" "$AGENT_VCPUS" "$AGENT_RAM" "$AGENT_DISK_GB" \
    "$AGENT_NAT_MAC" "$AGENT_HA_MAC" "$AGENT_IP"
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
# settle sleep.  Filters out the static 10.90.0.x address so it never shadows
# the NAT lease.
get_nat_ip() {
  local name="$1"
  virsh_ domifaddr "$name" --source lease 2>/dev/null \
    | awk '/ipv4/ {print $4}' | grep -v '^10\.90\.' | head -1 | sed 's|/.*||'
}

# print_vm_summary <name> <role> [<label:ip> ...]
# role drives the install/config hint lines.
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
  echo "  setup   : AUTOMATIC via cloud-init (~/setup.sh) — watch: tail -f /var/log/sysmanage-setup.log"
  echo "            re-run by hand if needed:  bash ~/setup.sh   (idempotent). Steps for reference:"
  case "$role" in
    server)
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage"
      echo "  config  : point /etc/sysmanage.yaml 'database:' at BOTH db nodes via a"
      echo "            libpq multi-host DSN (the current primary is auto-selected):"
      echo "              database:"
      echo "                user: ${DB_USER}"
      echo "                password: ${DB_PASSWORD}"
      echo "                host: \"${PGP_IP},${PGS_IP}\""
      echo "                port: 5432"
      echo "                name: ${DB_NAME}"
      echo "                options: \"target_session_attrs=read-write\""
      echo "            then run the migrations with the bundled venv (PPA install):"
      echo "              cd /opt/sysmanage && sudo -u sysmanage .venv/bin/python \\"
      echo "                scripts/sysmanage_migrate.py && sudo systemctl restart sysmanage"
      echo "  open    : from THIS host's browser ->  https://${SERVER_IP}:<web-port>"
      echo "            (admin_userid MUST be an email, e.g. admin@example.com / admin)"
      ;;
    pg-primary)
      echo "  install : sudo apt update && sudo apt install -y postgresql"
      echo "  setup   : create the sysmanage DB + a replication role, open the subnet,"
      echo "            and enable streaming replication, then restart postgres:"
      echo "              sudo -u postgres psql -c \"CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';\""
      echo "              sudo -u postgres psql -c \"CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};\""
      echo "              sudo -u postgres psql -c \"CREATE USER ${REPL_USER} WITH REPLICATION PASSWORD '${REPL_PASSWORD}';\""
      echo "            postgresql.conf:  listen_addresses='*'  wal_level=replica  max_wal_senders=10"
      echo "            pg_hba.conf:      host all         ${DB_USER}   10.90.0.0/24  scram-sha-256"
      echo "                              host replication ${REPL_USER} 10.90.0.0/24  scram-sha-256"
      echo "              sudo systemctl restart postgresql"
      ;;
    pg-standby)
      echo "  install : sudo apt update && sudo apt install -y postgresql"
      echo "  setup   : clone the primary via streaming replication (pass the"
      echo "            password with PGPASSWORD — the interactive prompt is easy to"
      echo "            fumble; ${REPL_USER} only allows *replication* connections):"
      echo "              sudo systemctl stop postgresql"
      echo "              sudo -u postgres rm -rf /var/lib/postgresql/${PG_VER}/main"
      echo "              sudo -u postgres bash -c 'PGPASSWORD=${REPL_PASSWORD} pg_basebackup \\"
      echo "                   -h ${PGP_IP} -U ${REPL_USER} -D /var/lib/postgresql/${PG_VER}/main -R -P'"
      echo "              sudo systemctl start postgresql"
      echo "            (or just run '$0 failback' from the host — it does this for you)"
      echo "  promote : to test failover ->  sudo -u postgres pg_ctlcluster ${PG_VER} main promote"
      ;;
    agent)
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage-agent \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage-agent"
      echo "  config  : point /etc/sysmanage-agent.yaml hostname at the server (${SERVER_IP})"
      echo "            so it keeps a live workload hitting the DB during the failover"
      ;;
  esac
  echo
}

# ---------------------------------------------------------------------------
# Failover / failback helpers (drive the DB nodes over SSH)
# ---------------------------------------------------------------------------

# ssh into a VM over the HA bridge using its password (the cloud-init user).
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

# pg_role <ip> -> primary | standby | down
# Uses pg_is_in_recovery(): a primary returns 'f', a streaming standby 't'.
pg_role() {
  local ip="$1" rec
  rec="$(ha_ssh "$ip" "sudo -u postgres psql -tAc 'select pg_is_in_recovery();'" 2>/dev/null | tr -d '[:space:]')"
  case "$rec" in
    f) echo "primary" ;;
    t) echo "standby" ;;
    *) echo "down" ;;
  esac
}

# pg_version <ip> -> the PostgreSQL major version (for pg_ctlcluster / data dir).
pg_version() {
  ha_ssh "$1" "pg_lsclusters -h 2>/dev/null | awk 'NR==1{print \$1}'" 2>/dev/null | tr -d '[:space:]'
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
  ensure_ha_network
  ensure_base_image

  ensure_vm "$SERVER_NAME" create_server
  ensure_vm "$PGP_NAME"    create_pg_primary
  ensure_vm "$PGS_NAME"    create_pg_standby
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
  print_vm_summary "$SERVER_NAME" "server"     "ha:${SERVER_IP}"
  print_vm_summary "$PGP_NAME"    "pg-primary" "ha:${PGP_IP}"
  print_vm_summary "$PGS_NAME"    "pg-standby" "ha:${PGS_IP}"
  print_vm_summary "$AGENT_NAME"  "agent"      "ha:${AGENT_IP}"

  echo "Default login (all VMs):"
  echo "  user     = ${USERNAME}"
  echo "  password = ${PASSWORD}"
  echo
  echo "sysmanage UI login — when you configure /etc/sysmanage.yaml on the server:"
  echo "  - security.admin_userid MUST be a valid EMAIL (login validates EmailStr;"
  echo "    a bare 'admin' -> HTTP 422, not 401). e.g. admin@example.com / admin"
  echo "  - email.enabled: true  (just the flag — no SMTP server/password needed)."
  echo
  echo "HA cluster network (${HA_NET_NAME}, static, no internet):"
  echo "  server      : ${SERVER_IP}    <- open  https://${SERVER_IP}:<web-port>  in THIS host's browser"
  echo "  pg-primary  : ${PGP_IP}"
  echo "  pg-standby  : ${PGS_IP}"
  echo "  ha-agent    : ${AGENT_IP}"
  echo "  host        : ${HA_NET_HOST_IP}    (SSH from here:  ssh ${USERNAME}@${SERVER_IP})"
  echo
  echo "Suggested bring-up order:"
  echo "  1. pg-primary: install postgres, create the ${DB_NAME} DB + ${REPL_USER} role,"
  echo "     open 10.90.0.0/24, enable wal_level=replica, restart."
  echo "  2. pg-standby: pg_basebackup from ${PGP_IP} (-R) and start — confirm it streams"
  echo "     (on the primary:  sudo -u postgres psql -c 'select * from pg_stat_replication;')."
  echo "  3. server: install sysmanage, point the DSN at \"${PGP_IP},${PGS_IP}\" with"
  echo "     target_session_attrs=read-write, alembic upgrade head, then browse the UI."
  echo "  4. ha-agent: install sysmanage-agent pointed at ${SERVER_IP} so a workload runs."
  echo
  echo "Test the Phase 15.1 failover path:"
  echo "  a. With the UI open + the agent reporting, stop the primary:"
  echo "       ssh ${USERNAME}@${PGP_IP} sudo systemctl stop postgresql"
  echo "  b. Promote the standby (or let a cluster manager do it):"
  echo "       ssh ${USERNAME}@${PGS_IP} 'sudo -u postgres pg_ctlcluster ${PG_VER} main promote'"
  echo "  c. The server's pool pre-ping discards the dead connections and the multi-host"
  echo "     DSN reconnects to ${PGS_IP} (now read-write). Confirm recovery:"
  echo "       curl -k https://${SERVER_IP}:<web-port>/api/health   # 503 during the gap, 200 after"
  echo "     See docs/administration/postgresql-ha.html for the full behavior."
  echo
  echo "Optional — multi-tenant (Pro+) dynamic DB credentials:"
  echo "  If you're exercising per-tenant databases, OpenBAO's database secrets"
  echo "  engine mints tenant credentials, and ITS OWN connection to postgres must"
  echo "  also point at the cluster endpoint or it can't mint creds after a failover:"
  echo "    bao write database/config/sysmanage plugin_name=postgresql-database-plugin \\"
  echo "      allowed_roles=\"tenant-*\" \\"
  echo "      connection_url=\"postgresql://{{username}}:{{password}}@${PGP_IP},${PGS_IP}:5432/postgres?target_session_attrs=read-write\" \\"
  echo "      username=\"openbao_admin\" password=\"...\""
  echo "  Then confirm a tenant lease requested AFTER a failover still succeeds."
  echo
  echo "Re-check status :  $0 status"
  echo "Tear everything :  $0 stop"
}

cmd_stop() {
  check_deps
  for name in "${VM_NAMES[@]}"; do
    # Always try destroy first, regardless of what vm_running thinks.
    # Skipping destroy when vm_running returned false and then undefining
    # leaves a "transient" running domain that ``start`` can't recreate
    # ("Domain is already active").  destroy on a stopped domain is a no-op +
    # non-zero exit, which ``|| true`` absorbs cleanly.
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

  if virsh_ net-info "$HA_NET_NAME" >/dev/null 2>&1; then
    if net_is_active "$HA_NET_NAME"; then
      virsh_ net-destroy "$HA_NET_NAME" >/dev/null 2>&1 || true
    fi
    virsh_ net-undefine "$HA_NET_NAME" >/dev/null 2>&1 || true
    log "network $HA_NET_NAME: removed"
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
  for net in default "$HA_NET_NAME"; do
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
  print_vm_status "$SERVER_NAME" "ha:${SERVER_IP}"
  print_vm_status "$PGP_NAME"    "ha:${PGP_IP}"
  print_vm_status "$PGS_NAME"    "ha:${PGS_IP}"
  print_vm_status "$AGENT_NAME"  "ha:${AGENT_IP}"

  echo
  echo "Browser: https://${SERVER_IP}:<web-port>  (from this host, once sysmanage is installed)"
  echo "Credentials: user=${USERNAME}  password=${PASSWORD}"
}

cmd_failover() {
  check_deps
  check_ssh_deps
  local pgp_role pgs_role primary_ip standby_ip
  pgp_role="$(pg_role "$PGP_IP")"
  pgs_role="$(pg_role "$PGS_IP")"
  log "Current roles: ${PGP_NAME}=${pgp_role} (${PGP_IP}), ${PGS_NAME}=${pgs_role} (${PGS_IP})"

  if [[ "$pgp_role" == "primary" && "$pgs_role" == "standby" ]]; then
    primary_ip="$PGP_IP"; standby_ip="$PGS_IP"
  elif [[ "$pgs_role" == "primary" && "$pgp_role" == "standby" ]]; then
    primary_ip="$PGS_IP"; standby_ip="$PGP_IP"
  else
    die "Need exactly one primary + one standby to fail over (got ${pgp_role}/${pgs_role}).
Finish cluster setup (see '$0 start'), or run '$0 failback' to repair replication."
  fi

  log "Stopping the primary at ${primary_ip} (simulating its loss)"
  ha_ssh "$primary_ip" "sudo systemctl stop postgresql" \
    || warn "primary stop returned non-zero (already down?)"

  local ver
  ver="$(pg_version "$standby_ip")"
  [[ -n "$ver" ]] || die "couldn't determine PostgreSQL version on standby ${standby_ip}"
  log "Promoting the standby at ${standby_ip} (pg ${ver}) to primary"
  ha_ssh "$standby_ip" "sudo pg_ctlcluster ${ver} main promote" \
    || die "promote failed on ${standby_ip}"

  echo
  log "Failover complete — ${standby_ip} is now the primary."
  log "The server's multi-host DSN + pool pre-ping reconnect there within a few seconds;"
  log "the OpenBAO lease-acquisition retry (Phase 15.1) covers the Pro+ per-tenant path."
  log "Watch recovery:  curl -k https://${SERVER_IP}:<web-port>/api/health   # 503 -> 200"
  log "Repair replication when ready:  $0 failback"
}

cmd_failback() {
  check_deps
  check_ssh_deps
  local pgp_role pgs_role primary_ip rebuild_ip ver
  pgp_role="$(pg_role "$PGP_IP")"
  pgs_role="$(pg_role "$PGS_IP")"
  log "Current roles: ${PGP_NAME}=${pgp_role} (${PGP_IP}), ${PGS_NAME}=${pgs_role} (${PGS_IP})"

  # Rebuild the non-primary node as a fresh streaming standby of whichever node
  # is currently primary, restoring two-node redundancy (direction-agnostic, so
  # it works after either a failover or a failover-back).
  if [[ "$pgp_role" == "primary" ]]; then
    primary_ip="$PGP_IP"; rebuild_ip="$PGS_IP"
  elif [[ "$pgs_role" == "primary" ]]; then
    primary_ip="$PGS_IP"; rebuild_ip="$PGP_IP"
  else
    die "No primary is currently up (${pgp_role}/${pgs_role}) — start one before failback."
  fi

  ver="$(pg_version "$primary_ip")"
  [[ -n "$ver" ]] || die "couldn't determine PostgreSQL version on primary ${primary_ip}"

  log "Rebuilding ${rebuild_ip} as a streaming standby of primary ${primary_ip} (pg ${ver})"
  ha_ssh "$rebuild_ip" "\
    sudo systemctl stop postgresql; \
    sudo -u postgres rm -rf /var/lib/postgresql/${ver}/main; \
    sudo -u postgres bash -c 'PGPASSWORD=\"${REPL_PASSWORD}\" pg_basebackup -h ${primary_ip} -U ${REPL_USER} -D /var/lib/postgresql/${ver}/main -R -P'; \
    sudo systemctl start postgresql" \
    || die "rebuild of ${rebuild_ip} failed (check the ${REPL_USER} role + pg_hba on ${primary_ip})"

  echo
  log "Failback complete — cluster restored: primary=${primary_ip}, standby=${rebuild_ip}."
  log "Verify streaming:  ssh ${USERNAME}@${primary_ip} sudo -u postgres psql -c 'select * from pg_stat_replication;'"
}

usage() {
  cat <<EOF
Usage: $0 {start|stop|status|failover|failback}

  start     Create and start the four VMs (server + agent + a two-node
            PostgreSQL cluster) — idempotent; already-running VMs are
            reported, not re-created.
  stop      Destroy all four VMs, delete their disks and seed ISOs, and
            tear down the ${HA_NET_NAME} isolated network.  The Ubuntu
            base cloud image is kept so a subsequent 'start' is fast.
  status    Show network state and per-VM state + configured static IPs +
            DHCP-assigned NAT IPs + the browser URL.
  failover  Stop the current primary and promote the standby, to exercise
            the server's reconnect + retry path.  (Needs 'sshpass' and a
            configured cluster.)
  failback  Rebuild the other node as a fresh streaming standby of the
            current primary, restoring two-node redundancy.
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
