# Managed by SysManage -- keep this line: the SysManage package installers
# use it to tell this config from the stock one the openbao package ships, and
# leave a config that carries it (including your edits) alone on upgrade.
#
# SysManage-managed OpenBAO configuration.
#
# Single-node local secrets broker for THIS SysManage server.  OpenBAO is
# central to SysManage (credential broker for multi-tenancy, plus the Pro+
# secrets / dynamic-lease features).  This config is intentionally minimal
# and identical across every supported OS so the appliance behaves the same
# everywhere.
#
# It listens on the loopback interface only -- the SysManage API talks to
# OpenBAO locally, never over the network -- so TLS is disabled on the
# listener (loopback traffic does not leave the host).  Data is kept in the
# file storage backend so a fresh install needs no external dependency.
#
# Air-gap note: file storage + locally-protected init/unseal material is the
# shipping seal mechanism (cloud-KMS auto-unseal is unreachable offline).
# See docs/planning/openbao-deployment-and-airgap.md §6.

storage "file" {
  path = "/var/lib/openbao/data"
}

listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = "true"
}

api_addr      = "http://127.0.0.1:8200"
disable_mlock = true
ui            = false

# Optional auto-unseal.  By default OpenBAO is unsealed at boot from the
# root-only key file /var/lib/openbao/init.json (never from sysmanage.yaml).
# Where you run a key service, uncomment ONE seal stanza instead and OpenBAO
# unseals itself; the init/unseal one-shot then keeps only a recovery key and
# the root token in init.json.  Set it up before OpenBAO is first initialized:
# moving an existing install to a seal needs `bao operator unseal -migrate`
# (see the OpenBAO seal migration docs).  The token below belongs in the
# environment of the openbao service (VAULT_TOKEN), never in this file.
#
# Transit against another OpenBAO or Vault:
# seal "transit" {
#   address    = "https://keys.example.com:8200"
#   key_name   = "sysmanage-autounseal"
#   mount_path = "transit/"
# }
#
# A cloud key service works the same way, e.g. seal "awskms" { kms_key_id = "..." }.
