// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Federation role card for Settings → Server Role.
 *
 * The federation counterpart to the air-gap server-role card — an
 * INDEPENDENT axis (a server can be an air-gap collector AND a federation
 * site).  Lets the operator pick none / coordinator / site, then exchange
 * federation identity public keys with the peer exactly like the air-gap
 * collector/repository key exchange.
 *
 * Backed by GET/PUT /api/v1/federation-role and
 * GET /api/v1/federation/identity-key + /api/v1/federation/trusted-peers.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Radio,
  RadioGroup,
  Snackbar,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteIcon from "@mui/icons-material/Delete";
import { useTranslation } from "react-i18next";

import axiosInstance from "../Services/api";
import { copyToClipboard } from "../utils/clipboard";

type FederationRole = "none" | "coordinator" | "site";

const ROLE_URL = "/api/v1/federation-role";
const IDENTITY_URL = "/api/v1/federation/identity-key";
const PEERS_URL = "/api/v1/federation/trusted-peers";
// NB: the site engine router is mounted at prefix "/v1/federation/site"
// (the controller is "/v1/federation"), so the site-side handshake routes
// live under .../federation/site/*, not .../federation/*.
const ENROLL_URL = "/api/v1/federation/site/enroll";
const ENROLL_STATUS_URL = "/api/v1/federation/site/enrollment-status";

interface IdentityKey {
  public_key_pem: string;
  fingerprint: string;
}

interface TrustedPeer {
  name: string;
  fingerprint: string | null;
}

const FederationRoleCard: React.FC = () => {
  const { t } = useTranslation();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [currentRole, setCurrentRole] = useState<FederationRole>("none");
  const [selectedRole, setSelectedRole] = useState<FederationRole>("none");
  const [error, setError] = useState<string | null>(null);
  const [snackOpen, setSnackOpen] = useState(false);

  const [key, setKey] = useState<IdentityKey | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [peers, setPeers] = useState<TrustedPeer[]>([]);
  const [peerName, setPeerName] = useState("");
  const [peerPem, setPeerPem] = useState("");
  const [peerBusy, setPeerBusy] = useState(false);

  // Site-side enrollment: only shown when this server's role is "site".
  const [coordUrl, setCoordUrl] = useState("");
  const [enrollToken, setEnrollToken] = useState("");
  // Strict trust: the coordinator's identity public key, obtained OUT OF BAND
  // and pasted here so this site can authenticate the coordinator's cert.
  const [coordIdentityKey, setCoordIdentityKey] = useState("");
  const [enrolling, setEnrolling] = useState(false);
  const [enrollStatus, setEnrollStatus] = useState<string | null>(null);
  const [enrollCoordUrl, setEnrollCoordUrl] = useState<string | null>(null);
  const [enrollError, setEnrollError] = useState<string | null>(null);

  const fetchRole = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axiosInstance.get<{ role: string }>(ROLE_URL);
      const role = (r.data.role as FederationRole) || "none";
      setCurrentRole(role);
      setSelectedRole(role);
      setError(null);
    } catch {
      setError(
        t("federationRole.loadError", "Could not load the federation role."),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  const fetchKeyAndPeers = useCallback(async () => {
    try {
      const k = await axiosInstance.get<IdentityKey>(IDENTITY_URL);
      setKey(k.data);
    } catch {
      setKey(null);
    }
    try {
      const p = await axiosInstance.get<{ trusted: TrustedPeer[] }>(PEERS_URL);
      setPeers(p.data.trusted ?? []);
    } catch {
      setPeers([]);
    }
  }, []);

  useEffect(() => {
    fetchRole();
  }, [fetchRole]);

  const fetchEnrollmentStatus = useCallback(async () => {
    try {
      const s = await axiosInstance.get<{
        status: string;
        coordinator: { coordinator_url?: string | null } | null;
      }>(ENROLL_STATUS_URL);
      setEnrollStatus(s.data.status ?? null);
      setEnrollCoordUrl(s.data.coordinator?.coordinator_url ?? null);
    } catch {
      setEnrollStatus(null);
    }
  }, []);

  useEffect(() => {
    if (currentRole !== "none") fetchKeyAndPeers();
    if (currentRole === "site") fetchEnrollmentStatus();
  }, [currentRole, fetchKeyAndPeers, fetchEnrollmentStatus]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axiosInstance.put(ROLE_URL, { role: selectedRole });
      setCurrentRole(selectedRole);
      setSnackOpen(true);
      setError(null);
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(
        detail || t("federationRole.saveError", "Could not save the federation role."),
      );
    } finally {
      setSaving(false);
    }
  };

  const copy = async (value: string, what: string) => {
    if (await copyToClipboard(value)) {
      setCopied(what);
      globalThis.setTimeout(() => setCopied(null), 2000);
    } else {
      setError(t("federationRole.copyError", "Could not copy to clipboard."));
    }
  };

  const importPeer = async () => {
    setPeerBusy(true);
    try {
      await axiosInstance.post(PEERS_URL, {
        name: peerName,
        public_key_pem: peerPem,
      });
      setPeerName("");
      setPeerPem("");
      setError(null);
      await fetchKeyAndPeers();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(detail || t("federationRole.importError", "Could not import the key."));
    } finally {
      setPeerBusy(false);
    }
  };

  const handleEnroll = async () => {
    setEnrolling(true);
    setEnrollError(null);
    try {
      await axiosInstance.post(ENROLL_URL, {
        coordinator_url: coordUrl.trim(),
        enrollment_token: enrollToken.trim(),
        coordinator_identity_public_key_pem: coordIdentityKey.trim(),
      });
      setEnrollToken("");
      await fetchEnrollmentStatus();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setEnrollError(
        detail ||
          t("federationRole.enroll.error", "Could not enroll with the coordinator."),
      );
    } finally {
      setEnrolling(false);
    }
  };

  const removePeer = async (name: string) => {
    try {
      await axiosInstance.delete(`${PEERS_URL}/${encodeURIComponent(name)}`);
      await fetchKeyAndPeers();
    } catch {
      setError(t("federationRole.removeError", "Could not remove the key."));
    }
  };

  const roleOptions: Array<{
    value: FederationRole;
    title: string;
    description: string;
  }> = [
    {
      value: "none",
      title: t("federationRole.none.title", "Not federated"),
      description: t(
        "federationRole.none.description",
        "The default. This server is not part of a multi-site federation. Choose this unless you are running a coordinator or a subordinate site.",
      ),
    },
    {
      value: "coordinator",
      title: t("federationRole.coordinator.title", "Federation Coordinator"),
      description: t(
        "federationRole.coordinator.description",
        "The hub that aggregates host inventory, compliance, and vulnerability rollups from many subordinate site servers and dispatches commands and policies down to them. One coordinator per federation.",
      ),
    },
    {
      value: "site",
      title: t("federationRole.site.title", "Federation Site"),
      description: t(
        "federationRole.site.description",
        "A subordinate server that runs autonomously and reports up to a coordinator. It keeps managing its own hosts even when the coordinator is unreachable, replaying queued data on reconnect.",
      ),
    },
  ];

  if (loading) {
    return (
      <Card variant="outlined" data-testid="federation-role-card">
        <CardContent sx={{ display: "flex", justifyContent: "center", p: 4 }}>
          <CircularProgress />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card variant="outlined" data-testid="federation-role-card">
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {t("federationRole.heading", "Federation Role")}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t(
            "federationRole.intro",
            "Choose how this server participates in a multi-site federation. This is independent of the air-gap role on the left — a server can be both. Takes effect after the next restart.",
          )}
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <FormControl component="fieldset" sx={{ width: "100%" }}>
          <RadioGroup
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value as FederationRole)}
          >
            {roleOptions.map((opt) => (
              <Box
                key={opt.value}
                sx={{
                  border: 1,
                  borderColor:
                    selectedRole === opt.value ? "primary.main" : "divider",
                  borderRadius: 1,
                  p: 2,
                  mb: 1.5,
                }}
              >
                <FormControlLabel
                  value={opt.value}
                  control={<Radio />}
                  label={
                    <Typography variant="subtitle1">
                      {opt.title}
                      {opt.value === currentRole && (
                        <Typography
                          component="span"
                          variant="caption"
                          color="success.main"
                          sx={{ ml: 1 }}
                        >
                          {t("federationRole.currentTag", "(current)")}
                        </Typography>
                      )}
                    </Typography>
                  }
                />
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ ml: 4, mt: 0.5 }}
                >
                  {opt.description}
                </Typography>
              </Box>
            ))}
          </RadioGroup>
        </FormControl>

        <Box sx={{ mt: 1, mb: 1 }}>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={saving || selectedRole === currentRole}
            startIcon={saving ? <CircularProgress size={16} /> : undefined}
            data-testid="federation-role-save"
          >
            {saving
              ? t("federationRole.saving", "Saving…")
              : t("federationRole.save", "Save Federation Role")}
          </Button>
        </Box>

        {/* Identity-key + peer exchange — shown once federated. */}
        {currentRole !== "none" && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" gutterBottom>
              {t("federationRole.identity.title", "This server's identity key")}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {t(
                "federationRole.identity.help",
                "Copy this public key and paste it into the peer's federation card so each side can record the other's identity fingerprint and verify it out of band. The private key never leaves this server.",
              )}
            </Typography>
            {key ? (
              <Box sx={{ mb: 2 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                    {key.fingerprint.slice(0, 24)}…
                  </Typography>
                  <Tooltip
                    title={
                      copied === "fp"
                        ? t("federationRole.copied", "Copied!")
                        : t("federationRole.copyFingerprint", "Copy fingerprint")
                    }
                  >
                    <IconButton
                      size="small"
                      onClick={() => copy(key.fingerprint, "fp")}
                      data-testid="federation-copy-fingerprint"
                    >
                      <ContentCopyIcon fontSize="inherit" />
                    </IconButton>
                  </Tooltip>
                </Box>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<ContentCopyIcon />}
                  onClick={() => copy(key.public_key_pem, "pem")}
                  sx={{ mt: 1 }}
                  data-testid="federation-copy-key"
                >
                  {copied === "pem"
                    ? t("federationRole.copied", "Copied!")
                    : t("federationRole.identity.copyKey", "Copy Public Key")}
                </Button>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t("federationRole.identity.pending", "Generating identity key…")}
              </Typography>
            )}

            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" gutterBottom>
              {t("federationRole.peers.title", "Peer identity keys")}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {t(
                "federationRole.peers.help",
                "Record a peer's public key here to verify its identity fingerprint out of band. The federation connection itself is secured by the TLS certificate pinned during enrollment — these keys are for human verification, not access control.",
              )}
            </Typography>
            <List dense data-testid="federation-peer-list">
              {peers.map((p) => (
                <ListItem
                  key={p.name}
                  secondaryAction={
                    <IconButton
                      edge="end"
                      size="small"
                      onClick={() => removePeer(p.name)}
                      data-testid={`federation-peer-remove-${p.name}`}
                    >
                      <DeleteIcon fontSize="inherit" />
                    </IconButton>
                  }
                >
                  <ListItemText
                    primary={p.name}
                    secondary={p.fingerprint?.slice(0, 24) ?? ""}
                  />
                </ListItem>
              ))}
              {peers.length === 0 && (
                <Typography variant="body2" color="text.secondary" sx={{ px: 2 }}>
                  {t("federationRole.peers.empty", "No peer identity keys recorded yet.")}
                </Typography>
              )}
            </List>
            <TextField
              size="small"
              fullWidth
              label={t("federationRole.peers.name", "Peer name")}
              value={peerName}
              onChange={(e) => setPeerName(e.target.value)}
              sx={{ mb: 1 }}
              slotProps={{ htmlInput: { "data-testid": "federation-peer-name" } }}
            />
            <TextField
              size="small"
              fullWidth
              multiline
              minRows={3}
              label={t("federationRole.peers.pem", "Peer public key (PEM)")}
              value={peerPem}
              onChange={(e) => setPeerPem(e.target.value)}
              sx={{ mb: 1 }}
              slotProps={{ htmlInput: { "data-testid": "federation-peer-pem" } }}
            />
            <Button
              variant="outlined"
              onClick={importPeer}
              disabled={peerBusy || !peerName.trim() || !peerPem.trim()}
              data-testid="federation-peer-import"
            >
              {t("federationRole.peers.import", "Import Peer Key")}
            </Button>

            {/* Site-side enrollment handshake — only on a subordinate site. */}
            {currentRole === "site" && (
              <>
                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" gutterBottom>
                  {t("federationRole.enroll.title", "Enroll with coordinator")}
                </Typography>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ mb: 1 }}
                >
                  {t(
                    "federationRole.enroll.help",
                    "Point this site at its coordinator and paste the one-time enrollment token the coordinator issued (from its Sites page). This site calls back to complete the handshake and begin syncing.",
                  )}
                </Typography>
                {enrollStatus === "enrolled" ? (
                  <Alert
                    severity="success"
                    sx={{ mb: 1 }}
                    data-testid="federation-enroll-status"
                  >
                    {t("federationRole.enroll.enrolled", "Enrolled with coordinator")}
                    {enrollCoordUrl ? ` (${enrollCoordUrl})` : ""}
                  </Alert>
                ) : (
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 1 }}
                    data-testid="federation-enroll-status"
                  >
                    {t(
                      "federationRole.enroll.notEnrolled",
                      "Not yet enrolled with a coordinator.",
                    )}
                  </Typography>
                )}
                {enrollError && (
                  <Alert severity="error" sx={{ mb: 1 }}>
                    {enrollError}
                  </Alert>
                )}
                <TextField
                  size="small"
                  fullWidth
                  label={t("federationRole.enroll.coordUrl", "Coordinator URL")}
                  placeholder="https://coordinator.example.com:8080"
                  value={coordUrl}
                  onChange={(e) => setCoordUrl(e.target.value)}
                  sx={{ mb: 1 }}
                  slotProps={{
                    htmlInput: { "data-testid": "federation-enroll-url" },
                  }}
                />
                <TextField
                  size="small"
                  fullWidth
                  label={t("federationRole.enroll.token", "Enrollment token")}
                  value={enrollToken}
                  onChange={(e) => setEnrollToken(e.target.value)}
                  sx={{ mb: 1 }}
                  slotProps={{
                    htmlInput: { "data-testid": "federation-enroll-token" },
                  }}
                />
                <TextField
                  size="small"
                  fullWidth
                  multiline
                  minRows={3}
                  label={t(
                    "federationRole.enroll.coordIdentityKey",
                    "Coordinator identity public key (PEM)",
                  )}
                  helperText={t(
                    "federationRole.enroll.coordIdentityKeyHelp",
                    "Required. Paste the coordinator's identity public key, obtained out of band (from its Server Role page). This site refuses to enroll unless the coordinator proves this exact key — it is what defeats an enrollment-time man-in-the-middle.",
                  )}
                  value={coordIdentityKey}
                  onChange={(e) => setCoordIdentityKey(e.target.value)}
                  sx={{ mb: 1 }}
                  slotProps={{
                    htmlInput: {
                      "data-testid": "federation-enroll-coord-identity-key",
                    },
                  }}
                />
                <Button
                  variant="contained"
                  onClick={handleEnroll}
                  disabled={
                    enrolling ||
                    !coordUrl.trim() ||
                    !enrollToken.trim() ||
                    !coordIdentityKey.trim()
                  }
                  startIcon={
                    enrolling ? <CircularProgress size={16} /> : undefined
                  }
                  data-testid="federation-enroll-submit"
                >
                  {enrolling
                    ? t("federationRole.enroll.submitting", "Enrolling…")
                    : t("federationRole.enroll.submit", "Enroll with coordinator")}
                </Button>
              </>
            )}
          </>
        )}

        <Snackbar
          open={snackOpen}
          autoHideDuration={5000}
          onClose={() => setSnackOpen(false)}
          anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        >
          <Alert
            severity="success"
            variant="filled"
            onClose={() => setSnackOpen(false)}
          >
            {t(
              "federationRole.saved",
              "Federation role saved. Restart the server for it to take full effect.",
            )}
          </Alert>
        </Snackbar>
      </CardContent>
    </Card>
  );
};

export default FederationRoleCard;
