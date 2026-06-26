#!/usr/bin/env bash
# buildStandaloneTestNetwork.sh — Provision KVM VMs for a SINGLE-TENANT,
# STANDALONE sysmanage deployment on libvirt/KVM.
#
# This is the plain-vanilla topology: ONE sysmanage server talking to ONE
# PostgreSQL database, managing ONE agent.  No multi-tenancy, no federation,
# no air-gap.  It exists so you can exercise the classic 3-tier split — server,
# database, and a managed host — each on its OWN VM, the way a small real
# deployment looks (DB on a separate box from the app server):
#
#   sysmanage-st-db      (10.81.0.1)  — PostgreSQL for the server's ONE database.
#                                       Comes up TURNKEY: cloud-init installs
#                                       PostgreSQL, opens it on the isolated
#                                       10.81.0.0/24 network, and creates the
#                                       sysmanage role + database.  This is what
#                                       /etc/sysmanage.yaml ``database:`` points
#                                       at.
#   sysmanage-st-server  (10.81.0.10) — The sysmanage SERVER (backend API + web
#                                       UI).  A bare Ubuntu box — install
#                                       sysmanage on it per the instructions
#                                       printed at the end, then point its
#                                       ``database:`` block at the DB VM.
#   sysmanage-st-agent   (10.81.0.20) — A sysmanage-AGENT (a managed host).  Bare
#                                       Ubuntu — install sysmanage-agent and
#                                       point it at the server, so you can test
#                                       the full register -> approve -> report
#                                       path end to end.
#
# The DB VM is turnkey; the server and agent VMs are bare Ubuntu (install
# sysmanage / sysmanage-agent per the printed guide — mirrors
# buildFederationTestNetwork.sh and buildMultiTenantTestNetwork.sh).
#
# Usage:
#   scripts/buildStandaloneTestNetwork.sh start    # create + start (idempotent)
#   scripts/buildStandaloneTestNetwork.sh stop     # destroy + undefine + delete disks
#   scripts/buildStandaloneTestNetwork.sh status   # show VM/network state + IPs
#
# All VMs share login credentials:
#   user     = ubuntu
#   password = Ubuntu123$
# The PostgreSQL role on the DB VM:
#   role     = sysmanage
#   password = SysMgrTest123    (database = sysmanage)
#
# Requirements on the host:
#   sudo apt install libvirt-clients libvirt-daemon-system virtinst \
#                    qemu-utils qemu-system-x86 cloud-image-utils curl python3-gi

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

# PostgreSQL role provisioned on the DB VM (alphanumeric on purpose — it goes
# through psql in cloud-init runcmd, so no shell-special characters).
DB_ROLE="${DB_ROLE:-sysmanage}"
DBPASS="${DBPASS:-SysMgrTest123}"
DBNAME="${DBNAME:-sysmanage}"

# Default admin login the server is configured with (security: block).  Printed
# in the guide so you know how to log into the UI.  NOTE: admin_userid MUST be a
# valid EMAIL address — the /api/login model validates it as Pydantic EmailStr,
# so a bare 'admin' (as in sysmanage.yaml.example) is rejected with HTTP 422
# before any auth runs.
ADMIN_USER="${ADMIN_USER:-admin@example.com}"
ADMIN_PASS="${ADMIN_PASS:-admin}"

# Isolated bridge for the standalone network.  Every VM keeps a NAT NIC for
# internet (so cloud-init can apt-install PostgreSQL and the server/agent can
# install sysmanage from the PPA) AND a static NIC on this bridge, giving the
# nodes stable, known addresses.  The host gets an IP on the bridge too, so you
# can SSH straight into any node — and reach the web UI — over 10.81.0.x.
#
# 10.81.0.0/24 / virbr81 is deliberately distinct from the multi-tenant
# (10.80/virbr80) and federation (10.70/virbr70) networks, so this stack can
# coexist with them.
ST_NET_NAME="${ST_NET_NAME:-sysmanage-st}"
ST_NET_BRIDGE="${ST_NET_BRIDGE:-virbr81}"
ST_NET_HOST_IP="${ST_NET_HOST_IP:-10.81.0.254}"
ST_NET_MASK="${ST_NET_MASK:-255.255.255.0}"
ST_NET_CIDR="${ST_NET_CIDR:-10.81.0.0/24}"

# --- Database VM ---
DB_NAME="${DB_NAME:-sysmanage-st-db}"
DB_VCPUS="${DB_VCPUS:-1}"
DB_RAM="${DB_RAM:-2048}"
DB_DISK_GB="${DB_DISK_GB:-20}"
DB_NAT_MAC="${DB_NAT_MAC:-52:54:00:81:50:01}"
DB_ST_MAC="${DB_ST_MAC:-52:54:00:81:00:01}"
DB_IP="${DB_IP:-10.81.0.1}"

# --- Server VM (backend API + web UI) ---
SERVER_NAME="${SERVER_NAME:-sysmanage-st-server}"
SERVER_VCPUS="${SERVER_VCPUS:-2}"
SERVER_RAM="${SERVER_RAM:-4096}"
SERVER_DISK_GB="${SERVER_DISK_GB:-40}"
SERVER_NAT_MAC="${SERVER_NAT_MAC:-52:54:00:81:50:0a}"
SERVER_ST_MAC="${SERVER_ST_MAC:-52:54:00:81:00:0a}"
SERVER_IP="${SERVER_IP:-10.81.0.10}"

# --- Agent VM (a managed host) ---
# 2 GiB: at 1 GiB the agent's Python process OOM-kills in a crash-restart loop
# during its package/update-detection collection (the apt available-package
# universe balloons RSS to ~700 MiB).  Override with AGENT_RAM=<MiB>.
AGENT_NAME="${AGENT_NAME:-sysmanage-st-agent}"
AGENT_VCPUS="${AGENT_VCPUS:-1}"
AGENT_RAM="${AGENT_RAM:-2048}"
AGENT_DISK_GB="${AGENT_DISK_GB:-20}"
AGENT_NAT_MAC="${AGENT_NAT_MAC:-52:54:00:81:50:0b}"
AGENT_ST_MAC="${AGENT_ST_MAC:-52:54:00:81:00:0b}"
AGENT_IP="${AGENT_IP:-10.81.0.20}"

# Web UI + API ports the server listens on (matches sysmanage.yaml.example).
WEBUI_PORT="${WEBUI_PORT:-3000}"
API_PORT="${API_PORT:-8080}"

WORKDIR="$(mktemp -d -t sysmanage-st-XXXXXX)"
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

ensure_st_network() {
  if virsh_ net-info "$ST_NET_NAME" >/dev/null 2>&1; then
    log "network $ST_NET_NAME: already defined"
  else
    log "network $ST_NET_NAME: defining isolated bridge $ST_NET_BRIDGE"
    local xml="$WORKDIR/${ST_NET_NAME}.xml"
    cat > "$xml" <<EOF
<network>
  <name>${ST_NET_NAME}</name>
  <bridge name='${ST_NET_BRIDGE}' stp='on' delay='0'/>
  <ip address='${ST_NET_HOST_IP}' netmask='${ST_NET_MASK}'/>
</network>
EOF
    virsh_ net-define "$xml" >/dev/null
  fi
  net_is_active    "$ST_NET_NAME" || virsh_ net-start     "$ST_NET_NAME" >/dev/null
  net_is_autostart "$ST_NET_NAME" || virsh_ net-autostart "$ST_NET_NAME" >/dev/null
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

# The DB node: install PostgreSQL, open it on the isolated subnet, create the
# role + database.  The role/db creation is idempotent (guarded by existence
# checks) so a re-applied seed never errors.  Runtime shell ``$`` is escaped
# (\$) so it survives this build-host heredoc into the guest unchanged.
write_user_data_db() {
  local host="$1" out="$2"
  _user_data_header "$host" "$out" "true"
  cat >> "$out" <<EOF
packages:
  - postgresql
runcmd:
  - systemctl enable --now ssh
  - |
    for d in /etc/postgresql/*/main; do
      echo "listen_addresses = '*'" >> "\$d/postgresql.conf"
      echo "host all all ${ST_NET_CIDR} scram-sha-256" >> "\$d/pg_hba.conf"
    done
  - systemctl restart postgresql
  - |
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_ROLE}'" | grep -q 1 \\
      || sudo -u postgres psql -c "CREATE ROLE ${DB_ROLE} LOGIN PASSWORD '${DBPASS}' CREATEDB CREATEROLE;"
  - |
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DBNAME}'" | grep -q 1 \\
      || sudo -u postgres createdb -O ${DB_ROLE} ${DBNAME}
EOF
}

# A bare node (server or agent): plain Ubuntu + ssh.  sysmanage /
# sysmanage-agent are installed per the printed instructions.
write_user_data_bare() {
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
# standalone NIC (static /24 on the isolated bridge, no gateway).
# $1: NAT MAC.  $2: ST MAC.  $3: ST static IPv4 (no CIDR).  $4: output file.
write_network_config() {
  local nat_mac="$1" st_mac="$2" st_ip="$3" out="$4"
  cat > "$out" <<EOF
version: 2
ethernets:
  nat0:
    match:
      macaddress: "${nat_mac}"
    set-name: eth0
    dhcp4: true
  st0:
    match:
      macaddress: "${st_mac}"
    set-name: eth1
    dhcp4: false
    addresses:
      - ${st_ip}/24
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

# provision_vm <name> <kind> <vcpus> <ram> <disk_gb> <nat_mac> <st_mac> <st_ip>
# kind = "db" | "bare".  Every node is dual-homed (NAT NIC + static ST NIC).
provision_vm() {
  local name="$1" kind="$2" vcpus="$3" ram="$4" disk_gb="$5"
  local nat_mac="$6" st_mac="$7" st_ip="$8"

  local ud="$WORKDIR/${name}-user-data"
  local md="$WORKDIR/${name}-meta-data"
  local nc="$WORKDIR/${name}-network-config"
  if [[ "$kind" == "db" ]]; then
    write_user_data_db "$name" "$ud"
  else
    write_user_data_bare "$name" "$ud"
  fi
  write_meta_data      "$name" "$md"
  write_network_config "$nat_mac" "$st_mac" "$st_ip" "$nc"

  local seed_path="${IMG_POOL}/${name}-seed.iso"
  build_seed_iso "$ud" "$md" "$nc" "$seed_path"

  local disk_path="${IMG_POOL}/${name}.qcow2"
  create_disk "$disk_path" "$disk_gb"

  log "Defining $name (kind=$kind vcpus=$vcpus ram=${ram}M disk=${disk_gb}G st=$st_ip)"
  virt_install_ --connect "$LIBVIRT_URI" \
    --name "$name" \
    --vcpus "$vcpus" \
    --memory "$ram" \
    --osinfo "$OS_VARIANT" \
    --disk "path=${disk_path},format=qcow2,bus=virtio" \
    --disk "path=${seed_path},device=cdrom,bus=sata" \
    --network "network=default,model=virtio,mac=${nat_mac}" \
    --network "network=${ST_NET_NAME},model=virtio,mac=${st_mac}" \
    --graphics none \
    --console pty,target_type=serial \
    --noautoconsole \
    --import
}

create_db() {
  provision_vm "$DB_NAME" "db" "$DB_VCPUS" "$DB_RAM" "$DB_DISK_GB" \
    "$DB_NAT_MAC" "$DB_ST_MAC" "$DB_IP"
}
create_server() {
  provision_vm "$SERVER_NAME" "bare" "$SERVER_VCPUS" "$SERVER_RAM" "$SERVER_DISK_GB" \
    "$SERVER_NAT_MAC" "$SERVER_ST_MAC" "$SERVER_IP"
}
create_agent() {
  provision_vm "$AGENT_NAME" "bare" "$AGENT_VCPUS" "$AGENT_RAM" "$AGENT_DISK_GB" \
    "$AGENT_NAT_MAC" "$AGENT_ST_MAC" "$AGENT_IP"
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
# Filters out the static 10.81.x ST address so it never shadows the NAT one.
get_nat_ip() {
  local name="$1"
  virsh_ domifaddr "$name" --source lease 2>/dev/null \
    | awk '/ipv4/ {print $4}' | grep -v '^10\.81\.' | head -1 | sed 's|/.*||'
}

# print_vm_summary <name> <role> <st_ip>
print_vm_summary() {
  local name="$1" role="$2" st_ip="$3"
  echo "$name  (state: $(vm_state "$name"))"
  echo "  console : virsh -c ${LIBVIRT_URI} console ${name}    (Ctrl-] to exit)"
  printf '  %-7s : %s\n' "st" "$st_ip"
  local nat
  nat="$(get_nat_ip "$name")"
  if [[ -n "$nat" ]]; then
    echo "  NAT     : $nat"
  else
    echo "  NAT     : (pending — re-run '$0 status' once cloud-init finishes)"
  fi
  echo "  ssh     : ssh ${USERNAME}@${st_ip}      (password: ${PASSWORD})"
  case "$role" in
    db)
      echo "  db      : postgresql://${DB_ROLE}:${DBPASS}@${st_ip}:5432/${DBNAME}"
      echo "  verify  : psql 'postgresql://${DB_ROLE}:${DBPASS}@${st_ip}:5432/${DBNAME}' -c '\\conninfo'"
      ;;
    server)
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage postgresql-client"
      echo "  config  : edit /etc/sysmanage.yaml — point database: at ${DB_IP}, api/webui host 0.0.0.0"
      echo "  web ui  : http://${st_ip}:${WEBUI_PORT}     (login ${ADMIN_USER}/${ADMIN_PASS})"
      echo "  api     : http://${st_ip}:${API_PORT}       (the agent connects here)"
      ;;
    agent)
      echo "  install : sudo add-apt-repository -y ppa:bceverly/sysmanage-agent \\"
      echo "              && sudo apt update && sudo apt install -y sysmanage-agent"
      echo "  config  : edit /etc/sysmanage-agent.yaml — server.hostname=${SERVER_IP} port=${API_PORT} use_https=false"
      ;;
  esac
  echo
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_start() {
  check_deps
  log "Workspace         : $WORKDIR"
  log "libvirt image pool: $IMG_POOL"
  log "libvirt URI       : $LIBVIRT_URI"

  ensure_default_network
  ensure_st_network
  ensure_base_image

  ensure_vm "$DB_NAME"     create_db
  ensure_vm "$SERVER_NAME" create_server
  ensure_vm "$AGENT_NAME"  create_agent

  if (( CREATED_COUNT > 0 )); then
    log ""
    log "Waiting 45s for cloud-init (PostgreSQL install on the DB VM takes a"
    log "moment) + DHCP leases to settle..."
    sleep 45
  fi

  echo
  echo "=========================================="
  echo "  Post-start summary"
  echo "=========================================="
  echo
  print_vm_summary "$DB_NAME"     "db"     "$DB_IP"
  print_vm_summary "$SERVER_NAME" "server" "$SERVER_IP"
  print_vm_summary "$AGENT_NAME"  "agent"  "$AGENT_IP"

  echo "Login (all VMs):  user=${USERNAME}  password=${PASSWORD}"
  echo "Postgres role  :  ${DB_ROLE} / ${DBPASS}   (database=${DBNAME})"
  echo
  echo "Standalone network (${ST_NET_NAME}, isolated 10.81.0.0/24):"
  echo "  database : ${DB_IP}   db=${DBNAME}"
  echo "  server   : ${SERVER_IP}  (sysmanage backend + web UI)"
  echo "  agent    : ${AGENT_IP}  (managed host)"
  echo "  host     : ${ST_NET_HOST_IP}    (SSH from here:  ssh ${USERNAME}@${SERVER_IP})"
  echo
  print_wiring_guide
  echo "Re-check status :  $0 status"
  echo "Tear everything :  $0 stop"
}

# The standalone bring-up sequence: install the server, point it at the DB VM,
# migrate, start it, then install + point the agent at the server.
print_wiring_guide() {
  cat <<EOF
==========================================================================
  Wiring it together — single-tenant standalone bring-up
==========================================================================
The DB VM is turnkey — cloud-init already created the role + database and opened
PostgreSQL on the 10.81.0.0/24 network, so normally there's NOTHING to do here.
Confirm it's reachable from the host:

  psql 'postgresql://${DB_ROLE}:${DBPASS}@${DB_IP}:5432/${DBNAME}' -c '\\conninfo'

--------------------------------------------------------------------------
0. DATABASE  —  do NOT set up a local DB on the server
--------------------------------------------------------------------------
   IMPORTANT: the sysmanage package's post-install message tells you to "set up
   a local database" with 'sudo apt install postgresql; sudo -u postgres
   createuser/createdb ...'.  DO NOT run that on the SERVER VM — in this topology
   the database lives on the separate DB VM (${DB_IP}).  Point the server at it
   (step 1b) instead of standing up a local one.

   cloud-init already ran the equivalent ON THE DB VM.  If you're adapting this
   to your OWN database host, or need to (re)create the role/database, ssh to the
   DB VM and run it there (as the postgres superuser — role/db creation can't be
   bootstrapped remotely):

     ssh ${USERNAME}@${DB_IP}          # password: ${PASSWORD}

     # 1) create the login role + database, owned by that role:
     sudo -u postgres psql -c "CREATE ROLE ${DB_ROLE} LOGIN PASSWORD '${DBPASS}';"
     sudo -u postgres createdb ${DBNAME} -O ${DB_ROLE}
     sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DBNAME} TO ${DB_ROLE};"

     # 2) grant NETWORK access so the server can reach it (for each PG version dir):
     for d in /etc/postgresql/*/main; do
       echo "listen_addresses = '*'"                          | sudo tee -a "\$d/postgresql.conf"
       echo "host all all ${ST_NET_CIDR} scram-sha-256"       | sudo tee -a "\$d/pg_hba.conf"
     done
     sudo systemctl restart postgresql

   Then, back on the SERVER (after installing postgresql-client in step 1a),
   verify the server can reach the DB VM:

     psql 'postgresql://${DB_ROLE}:${DBPASS}@${DB_IP}:5432/${DBNAME}' -c '\\conninfo'

--------------------------------------------------------------------------
1. SERVER  —  ssh ${USERNAME}@${SERVER_IP}   (password: ${PASSWORD})
--------------------------------------------------------------------------
   a) Install sysmanage and the PostgreSQL CLIENT (psql) — the server talks to
      the dedicated DB VM, so it needs the client to reach it (and for the
      verify steps below). The 'postgresql-client' package is just psql + libpq,
      NOT a local database server:

        sudo add-apt-repository -y ppa:bceverly/sysmanage
        sudo apt update && sudo apt install -y sysmanage postgresql-client

   b) Point /etc/sysmanage.yaml at the DB VM and bind the API/UI so the
      agent and your host can reach them.  The minimal working config:

        api:
          host: "0.0.0.0"        # listen on all NICs (agent connects here)
          port: ${API_PORT}
        database:
          user: "${DB_ROLE}"
          password: "${DBPASS}"
          host: "${DB_IP}"          # the DB VM
          port: 5432
          name: "${DBNAME}"
        security:
          # admin_userid MUST be a valid email — /api/login validates it as
          # EmailStr, so a bare 'admin' is rejected with HTTP 422 (NOT 401).
          admin_userid: "${ADMIN_USER}"
          admin_password: "${ADMIN_PASS}"
          password_salt: "$(head -c16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
          jwt_secret: "$(head -c32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
          jwt_algorithm: "HS256"
          jwt_auth_timeout: 600
          jwt_refresh_timeout: 60000
        webui:
          host: "0.0.0.0"
          port: ${WEBUI_PORT}
        logging:
          level: "INFO|WARNING|ERROR|CRITICAL"
          format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        email:
          # Email just needs to be ENABLED — no SMTP server or password required
          # for this test.  The server fills the rest (host=localhost, port=587,
          # …) with defaults; without 'enabled: true' email-dependent flows are
          # off.
          enabled: true
        cors:
          # The web UI auto-discovers allowed origins from the server's NICs, but
          # on a dual-NIC box it can pick the NAT interface and miss the isolated
          # ${SERVER_IP} that your browser actually uses — which blocks the few
          # features the UI fetches from the API by absolute URL (e.g. Pro+ plugin
          # bundles).  List the browser's origin(s) explicitly so they're allowed:
          additional_origins:
            - "http://${SERVER_IP}:${WEBUI_PORT}"
            - "http://${SERVER_IP}:${API_PORT}"

      (Two random secrets were generated above — paste them in as shown, or
      run your own. Keep admin_password out of production configs.)

   c) Create the schema (alembic) against the DB VM, then start the server.

        # packaged install (systemd):
        sudo systemctl restart sysmanage
        # — or, from a dev checkout in the repo:
        make migrate && make start

      Confirm the schema landed on the DB VM:

        psql 'postgresql://${DB_ROLE}:${DBPASS}@${DB_IP}:5432/${DBNAME}' -c '\\dt' | head

   d) Open the web UI from your host (it's on the 10.81 bridge):

        http://${SERVER_IP}:${WEBUI_PORT}     login: ${ADMIN_USER} / ${ADMIN_PASS}

--------------------------------------------------------------------------
2. AGENT  —  ssh ${USERNAME}@${AGENT_IP}   (password: ${PASSWORD})
--------------------------------------------------------------------------
   a) Install sysmanage-agent:

        sudo add-apt-repository -y ppa:bceverly/sysmanage-agent
        sudo apt update && sudo apt install -y sysmanage-agent

   b) Point /etc/sysmanage-agent.yaml at the server:

        server:
          hostname: "${SERVER_IP}"
          port: ${API_PORT}
          use_https: false
          verify_ssl: false

   c) (Re)start the agent so it registers:

        sudo systemctl restart sysmanage-agent
        # follow it:  sudo journalctl -u sysmanage-agent -f

--------------------------------------------------------------------------
3. APPROVE + VERIFY  (in the web UI, http://${SERVER_IP}:${WEBUI_PORT})
--------------------------------------------------------------------------
   - The agent shows up under Hosts as 'pending'. Approve it.
   - Within a minute it flips to 'up' and starts reporting OS / packages /
     hardware. Open its host-detail page to confirm data is flowing.
   - Sanity-check the data really lives in the DB VM:

        psql 'postgresql://${DB_ROLE}:${DBPASS}@${DB_IP}:5432/${DBNAME}' \\
             -c 'SELECT fqdn, approval_status, status FROM hosts;'
==========================================================================
EOF
}

cmd_stop() {
  check_deps
  local all=("$DB_NAME" "$SERVER_NAME" "$AGENT_NAME")
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

  if virsh_ net-info "$ST_NET_NAME" >/dev/null 2>&1; then
    if net_is_active "$ST_NET_NAME"; then
      virsh_ net-destroy "$ST_NET_NAME" >/dev/null 2>&1 || true
    fi
    virsh_ net-undefine "$ST_NET_NAME" >/dev/null 2>&1 || true
    log "network $ST_NET_NAME: removed"
  fi

  log ""
  log "Base cloud image kept at $BASE_IMG (re-used by 'start')."
  log "Delete it manually with:  sudo rm $BASE_IMG"
}

print_vm_status() {
  local name="$1" st_ip="$2"
  if ! vm_exists "$name"; then
    printf "  %-26s %s\n" "$name" "(not defined)"
    return
  fi
  local state
  state="$(vm_state "$name")"
  printf "  %-26s %s\n" "$name" "$state"
  printf "    %-12s %s\n" "st:" "$st_ip"
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
  for net in default "$ST_NET_NAME"; do
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
  print_vm_status "$DB_NAME"     "$DB_IP"
  print_vm_status "$SERVER_NAME" "$SERVER_IP"
  print_vm_status "$AGENT_NAME"  "$AGENT_IP"

  echo
  echo "Login: user=${USERNAME}  password=${PASSWORD}   |   Postgres: ${DB_ROLE}/${DBPASS}"
  echo "Web UI: http://${SERVER_IP}:${WEBUI_PORT}  (${ADMIN_USER}/${ADMIN_PASS}, once the server is installed)"
}

usage() {
  cat <<EOF
Usage: $0 {start|stop|status}

  start   Create and start the standalone test VMs (idempotent — already
          running VMs are reported, not re-created).  The DB VM comes up with
          PostgreSQL installed + a role/database created; the server and agent
          VMs are bare (install sysmanage / sysmanage-agent per the printed
          guide).
  stop    Destroy every VM, delete disks + seed ISOs, and tear down the
          ${ST_NET_NAME} network.  The Ubuntu base image is kept so the next
          'start' is fast.
  status  Show network + per-VM state, static ST IPs, and DHCP NAT IPs.

Key environment overrides:
  DB_RAM / DB_DISK_GB         Resize the DB VM (default 2048 MiB / 20 GiB).
  SERVER_RAM / SERVER_DISK_GB Resize the server VM (default 4096 MiB / 40 GiB).
  AGENT_RAM                   Agent RAM (default 2048 MiB; 1 GiB OOMs the agent).
  DBPASS                      PostgreSQL role password (default SysMgrTest123).
  ADMIN_USER / ADMIN_PASS     Server admin login printed in the guide.
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
