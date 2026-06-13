# SysManage-managed OpenBAO configuration.
#
# Single-node local secrets broker for THIS SysManage server.  OpenBAO is
# central to SysManage (credential broker for multi-tenancy, plus the Pro+
# secrets / dynamic-lease features).  This config is intentionally minimal
# and identical across every supported OS so the appliance behaves the same
# everywhere.
#
# It listens on the loopback interface only — the SysManage API talks to
# OpenBAO locally, never over the network — so TLS is disabled on the
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
