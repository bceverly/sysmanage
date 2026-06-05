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

type FederationRole = "none" | "coordinator" | "site";

const ROLE_URL = "/api/v1/federation-role";
const IDENTITY_URL = "/api/v1/federation/identity-key";
const PEERS_URL = "/api/v1/federation/trusted-peers";

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

  useEffect(() => {
    if (currentRole !== "none") fetchKeyAndPeers();
  }, [currentRole, fetchKeyAndPeers]);

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
    try {
      await globalThis.navigator.clipboard.writeText(value);
      setCopied(what);
      globalThis.setTimeout(() => setCopied(null), 2000);
    } catch {
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
              : t("federationRole.save", "Save Role")}
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
                "Copy this public key and paste it into the peer's federation card so each side can pin the other's identity. The private key never leaves this server.",
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
              {t("federationRole.peers.title", "Trusted peer keys")}
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
                  {t("federationRole.peers.empty", "No trusted peer keys yet.")}
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
