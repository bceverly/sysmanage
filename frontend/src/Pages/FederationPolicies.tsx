// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Phase 12.3: federation policies management UI.
 *
 * Operator-facing CRUD on coordinator-defined policies.  Each policy
 * is polymorphic by ``policy_type`` (update_profile, firewall_role,
 * compliance_baseline, ...) with the type-specific body stored as
 * JSON in ``definition_json``.  This page surfaces:
 *
 *   - List view with type + active-only filters
 *   - Create dialog (type select + name + description + JSON editor)
 *   - Edit dialog (same shape, pre-filled)
 *   - Assign-to-sites dialog (multi-select against the loaded site list)
 *   - "Push now" action that triggers immediate distribution to
 *     every assigned site
 *   - Deactivate (soft-disable; row stays for audit)
 *
 * As with every other federation page, ``licensed: false`` from any
 * endpoint switches to the Enterprise upsell view rather than
 * trying to render data.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputLabel from "@mui/material/InputLabel";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  doAssignFederationPolicy,
  doCreateFederationPolicy,
  doDeactivateFederationPolicy,
  doGetFederationPolicy,
  doListFederationPolicies,
  doListFederationSites,
  doPushFederationPolicy,
  doUpdateFederationPolicy,
  FederationPolicy,
  FederationPolicyAssignment,
  FederationSiteSummary,
} from "../Services/federation";
import FederationAlertConfig from "../Components/FederationAlertConfig";

// Operator-visible policy types.  Mirrored from
// federation_policy_service's docstring — the engine accepts any
// string but the UI offers these common shapes as a select.  Free-
// form input remains available via the "Other..." sentinel.
const KNOWN_POLICY_TYPES = [
  "update_profile",
  "firewall_role",
  "compliance_baseline",
];
const POLICY_TYPE_OTHER = "__other__";

interface PoliciesState {
  loading: boolean;
  licensed: boolean | null;
  policies: FederationPolicy[];
  error: string | null;
}

interface CreateDialogState {
  open: boolean;
  policy_type: string;
  custom_policy_type: string;
  name: string;
  description: string;
  definition_text: string;
  error: string | null;
  submitting: boolean;
}

const EMPTY_CREATE: CreateDialogState = {
  open: false,
  policy_type: KNOWN_POLICY_TYPES[0],
  custom_policy_type: "",
  name: "",
  description: "",
  definition_text: "{}",
  error: null,
  submitting: false,
};

interface EditDialogState {
  open: boolean;
  policy: FederationPolicy | null;
  name: string;
  description: string;
  definition_text: string;
  error: string | null;
  submitting: boolean;
}

interface AssignDialogState {
  open: boolean;
  policy: FederationPolicy | null;
  loadingSites: boolean;
  sites: FederationSiteSummary[];
  selected: Set<string>;
  error: string | null;
  submitting: boolean;
  existingAssignments: FederationPolicyAssignment[];
}

const FederationPolicies: React.FC = () => {
  const { t } = useTranslation();

  const [state, setState] = useState<PoliciesState>({
    loading: true,
    licensed: null,
    policies: [],
    error: null,
  });
  const [filterType, setFilterType] = useState<string>("");
  const [activeOnly, setActiveOnly] = useState<boolean>(true);
  const [toast, setToast] = useState<string | null>(null);
  const [busyPolicyId, setBusyPolicyId] = useState<string | null>(null);
  const [createDialog, setCreateDialog] = useState<CreateDialogState>(EMPTY_CREATE);
  const [editDialog, setEditDialog] = useState<EditDialogState>({
    open: false,
    policy: null,
    name: "",
    description: "",
    definition_text: "{}",
    error: null,
    submitting: false,
  });
  const [assignDialog, setAssignDialog] = useState<AssignDialogState>({
    open: false,
    policy: null,
    loadingSites: false,
    sites: [],
    selected: new Set(),
    error: null,
    submitting: false,
    existingAssignments: [],
  });

  const fetchPolicies = useCallback(async () => {
    try {
      const data = await doListFederationPolicies({
        policy_type: filterType || undefined,
        active_only: activeOnly,
      });
      setState({
        loading: false,
        licensed: Boolean(data.licensed),
        policies: data.policies ?? [],
        error: null,
      });
    } catch (err) {
      setState({
        loading: false,
        licensed: null,
        policies: [],
        error:
          (err instanceof Error && err.message) ||
          t("policies.errorLoad", "Failed to load federation policies."),
      });
    }
  }, [filterType, activeOnly, t]);

  useEffect(() => {
    setState((prev) => ({ ...prev, loading: true }));
    fetchPolicies();
  }, [fetchPolicies]);

  // -------- Create flow --------------------------------------------------

  const handleSubmitCreate = async () => {
    if (createDialog.submitting) return;
    const resolvedType =
      createDialog.policy_type === POLICY_TYPE_OTHER
        ? createDialog.custom_policy_type.trim()
        : createDialog.policy_type;
    if (!resolvedType) {
      setCreateDialog((prev) => ({
        ...prev,
        error: t(
          "policies.create.typeRequired",
          "Policy type is required.",
        ),
      }));
      return;
    }
    let definition: Record<string, unknown>;
    try {
      definition = JSON.parse(createDialog.definition_text || "{}");
      if (typeof definition !== "object" || definition === null || Array.isArray(definition)) {
        throw new Error("must be a JSON object");
      }
    } catch {
      setCreateDialog((prev) => ({
        ...prev,
        error: t(
          "policies.create.invalidJson",
          "Definition must be a JSON object.",
        ),
      }));
      return;
    }
    setCreateDialog((prev) => ({ ...prev, submitting: true, error: null }));
    try {
      const resp = await doCreateFederationPolicy({
        policy_type: resolvedType,
        name: createDialog.name.trim(),
        description: createDialog.description.trim() || null,
        definition,
      });
      if (!resp.licensed) {
        setCreateDialog((prev) => ({
          ...prev,
          submitting: false,
          error: t(
            "policies.create.engineUnavailable",
            "The federation controller engine is not loaded; cannot create policies.",
          ),
        }));
        return;
      }
      setCreateDialog(EMPTY_CREATE);
      setToast(t("policies.create.success", "Policy created."));
      await fetchPolicies();
    } catch (err) {
      setCreateDialog((prev) => ({
        ...prev,
        submitting: false,
        error:
          (err instanceof Error && err.message) ||
          t("policies.create.error", "Failed to create policy."),
      }));
    }
  };

  // -------- Edit flow ----------------------------------------------------

  const openEditDialog = (policy: FederationPolicy) => {
    setEditDialog({
      open: true,
      policy,
      name: policy.name,
      description: policy.description ?? "",
      definition_text: policy.definition_json,
      error: null,
      submitting: false,
    });
  };

  const handleSubmitEdit = async () => {
    if (!editDialog.policy || editDialog.submitting) return;
    let definition: Record<string, unknown> | undefined;
    if (editDialog.definition_text.trim()) {
      try {
        const parsed = JSON.parse(editDialog.definition_text);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("must be a JSON object");
        }
        definition = parsed as Record<string, unknown>;
      } catch {
        setEditDialog((prev) => ({
          ...prev,
          error: t(
            "policies.create.invalidJson",
            "Definition must be a JSON object.",
          ),
        }));
        return;
      }
    }
    setEditDialog((prev) => ({ ...prev, submitting: true, error: null }));
    try {
      await doUpdateFederationPolicy(editDialog.policy.id, {
        name: editDialog.name.trim() || undefined,
        description: editDialog.description.trim() || null,
        definition,
      });
      setEditDialog((prev) => ({ ...prev, open: false, submitting: false }));
      setToast(t("policies.edit.success", "Policy updated."));
      await fetchPolicies();
    } catch (err) {
      setEditDialog((prev) => ({
        ...prev,
        submitting: false,
        error:
          (err instanceof Error && err.message) ||
          t("policies.edit.error", "Failed to update policy."),
      }));
    }
  };

  // -------- Assignment flow ---------------------------------------------

  const openAssignDialog = async (policy: FederationPolicy) => {
    setAssignDialog({
      open: true,
      policy,
      loadingSites: true,
      sites: [],
      selected: new Set(),
      error: null,
      submitting: false,
      existingAssignments: [],
    });
    try {
      // Fetch both the available sites AND the policy's current
      // assignments in parallel — the dialog pre-checks rows the
      // operator has already assigned, and re-assignment is treated
      // by the backend as a push-status reset (per 12.1.F semantics).
      const [sitesResp, detailResp] = await Promise.all([
        doListFederationSites(),
        doGetFederationPolicy(policy.id),
      ]);
      const sites = sitesResp.sites ?? [];
      const assignments = detailResp.assignments ?? [];
      setAssignDialog((prev) => ({
        ...prev,
        loadingSites: false,
        sites,
        existingAssignments: assignments,
        selected: new Set(assignments.map((a) => a.site_id)),
      }));
    } catch (err) {
      setAssignDialog((prev) => ({
        ...prev,
        loadingSites: false,
        error:
          (err instanceof Error && err.message) ||
          t("policies.assign.errorLoad", "Failed to load sites."),
      }));
    }
  };

  const handleToggleAssignSite = (siteId: string) => {
    setAssignDialog((prev) => {
      const next = new Set(prev.selected);
      if (next.has(siteId)) {
        next.delete(siteId);
      } else {
        next.add(siteId);
      }
      return { ...prev, selected: next };
    });
  };

  const handleSubmitAssign = async () => {
    if (!assignDialog.policy || assignDialog.submitting) return;
    setAssignDialog((prev) => ({ ...prev, submitting: true, error: null }));
    try {
      await doAssignFederationPolicy(
        assignDialog.policy.id,
        Array.from(assignDialog.selected),
      );
      setAssignDialog((prev) => ({ ...prev, open: false, submitting: false }));
      setToast(t("policies.assign.success", "Policy assignments updated."));
    } catch (err) {
      setAssignDialog((prev) => ({
        ...prev,
        submitting: false,
        error:
          (err instanceof Error && err.message) ||
          t("policies.assign.error", "Failed to update assignments."),
      }));
    }
  };

  // -------- Push / deactivate -------------------------------------------

  const handlePush = async (policy: FederationPolicy) => {
    setBusyPolicyId(policy.id);
    try {
      await doPushFederationPolicy(policy.id);
      setToast(
        t("policies.push.success", "Push triggered for '{{name}}'.", {
          name: policy.name,
        }),
      );
    } catch (err) {
      setToast(
        (err instanceof Error && err.message) ||
          t("policies.push.error", "Failed to push policy."),
      );
    } finally {
      setBusyPolicyId(null);
    }
  };

  const handleDeactivate = async (policy: FederationPolicy) => {
    setBusyPolicyId(policy.id);
    try {
      await doDeactivateFederationPolicy(policy.id);
      setToast(
        t("policies.deactivate.success", "'{{name}}' deactivated.", {
          name: policy.name,
        }),
      );
      await fetchPolicies();
    } catch (err) {
      setToast(
        (err instanceof Error && err.message) ||
          t("policies.deactivate.error", "Failed to deactivate policy."),
      );
    } finally {
      setBusyPolicyId(null);
    }
  };

  const distinctTypes = useMemo(() => {
    const types = new Set<string>(KNOWN_POLICY_TYPES);
    for (const p of state.policies) types.add(p.policy_type);
    return Array.from(types).sort((a, b) => a.localeCompare(b));
  }, [state.policies]);

  // ----- Render branches -----

  if (state.loading) {
    return (
      <Box sx={{ p: 3, display: "flex", justifyContent: "center" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (state.error) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{state.error}</Alert>
      </Box>
    );
  }

  if (state.licensed === false) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="info">
          <Typography variant="subtitle1" component="div">
            {t(
              "sites.enterpriseRequired.title",
              "Multi-site federation requires Enterprise",
            )}
          </Typography>
          <Typography variant="body2">
            {t(
              "sites.enterpriseRequired.body",
              "Federation lets you manage many SysManage servers from one coordinator. " +
                "Upgrade to an Enterprise license to enroll subordinate sites here.",
            )}
          </Typography>
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 2,
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <Box>
          <Typography variant="h5" component="h1">
            {t("policies.title", "Federation Policies")}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t(
              "policies.subtitle",
              "Centrally-defined policies pushed to subordinate sites.",
            )}
          </Typography>
        </Box>
        <Button
          variant="contained"
          onClick={() => setCreateDialog({ ...EMPTY_CREATE, open: true })}
          data-testid="create-policy-button"
        >
          {t("policies.create.button", "New Policy")}
        </Button>
      </Box>

      {/* Operator-configurable rollup-alert thresholds (Phase 12.1). */}
      <FederationAlertConfig />

      {/* Filter row */}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="policy-type-filter-label">
              {t("policies.filters.type", "Policy type")}
            </InputLabel>
            <Select
              labelId="policy-type-filter-label"
              label={t("policies.filters.type", "Policy type")}
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
            >
              <MenuItem value="">
                <em>{t("policies.filters.allTypes", "All types")}</em>
              </MenuItem>
              {distinctTypes.map((tp) => (
                <MenuItem key={tp} value={tp}>
                  {tp}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControlLabel
            control={
              <Switch
                checked={activeOnly}
                onChange={(e) => setActiveOnly(e.target.checked)}
              />
            }
            label={t("policies.filters.activeOnly", "Active only")}
          />
        </Stack>
      </Paper>

      {/* Table */}
      {state.policies.length === 0 ? (
        <Alert severity="info">
          {t(
            "policies.empty",
            "No policies have been defined yet. Click 'New Policy' to create one.",
          )}
        </Alert>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" data-testid="policies-table">
            <TableHead>
              <TableRow>
                <TableCell>{t("policies.columns.name", "Name")}</TableCell>
                <TableCell>{t("policies.columns.type", "Type")}</TableCell>
                <TableCell>{t("policies.columns.version", "Version")}</TableCell>
                <TableCell>{t("policies.columns.active", "Active")}</TableCell>
                <TableCell>{t("policies.columns.actions", "Actions")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {state.policies.map((policy) => (
                <TableRow key={policy.id} hover>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {policy.name}
                    </Typography>
                    {policy.description && (
                      <Typography variant="caption" color="text.secondary">
                        {policy.description}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={policy.policy_type}
                      size="small"
                      variant="outlined"
                    />
                  </TableCell>
                  {/* eslint-disable-next-line i18next/no-literal-string -- version prefix is not translatable */}
                  <TableCell>v{policy.version}</TableCell>
                  <TableCell>
                    {policy.is_active ? (
                      <Chip
                        label={t("policies.active", "active")}
                        color="success"
                        size="small"
                      />
                    ) : (
                      <Chip
                        label={t("policies.inactive", "inactive")}
                        size="small"
                      />
                    )}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1}>
                      <Button
                        size="small"
                        disabled={!policy.is_active}
                        onClick={() => openEditDialog(policy)}
                      >
                        {t("policies.actions.edit", "Edit")}
                      </Button>
                      <Button
                        size="small"
                        disabled={!policy.is_active}
                        onClick={() => openAssignDialog(policy)}
                      >
                        {t("policies.actions.assign", "Assign")}
                      </Button>
                      <Button
                        size="small"
                        disabled={
                          !policy.is_active || busyPolicyId === policy.id
                        }
                        onClick={() => handlePush(policy)}
                      >
                        {t("policies.actions.push", "Push now")}
                      </Button>
                      {policy.is_active && (
                        <Button
                          size="small"
                          color="error"
                          disabled={busyPolicyId === policy.id}
                          onClick={() => handleDeactivate(policy)}
                        >
                          {t(
                            "policies.actions.deactivate",
                            "Deactivate",
                          )}
                        </Button>
                      )}
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* --- Create dialog ------------------------------------------- */}
      <Dialog
        open={createDialog.open}
        onClose={() =>
          !createDialog.submitting && setCreateDialog(EMPTY_CREATE)
        }
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          {t("policies.create.title", "Create policy")}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {createDialog.error && (
              <Alert severity="error">{createDialog.error}</Alert>
            )}
            <FormControl fullWidth>
              <InputLabel id="policy-type-create-label">
                {t("policies.create.type", "Policy type")}
              </InputLabel>
              <Select
                labelId="policy-type-create-label"
                label={t("policies.create.type", "Policy type")}
                value={createDialog.policy_type}
                onChange={(e) =>
                  setCreateDialog((prev) => ({
                    ...prev,
                    policy_type: e.target.value,
                  }))
                }
              >
                {KNOWN_POLICY_TYPES.map((tp) => (
                  <MenuItem key={tp} value={tp}>
                    {tp}
                  </MenuItem>
                ))}
                <MenuItem value={POLICY_TYPE_OTHER}>
                  <em>{t("policies.create.typeOther", "Other...")}</em>
                </MenuItem>
              </Select>
            </FormControl>
            {createDialog.policy_type === POLICY_TYPE_OTHER && (
              <TextField
                label={t(
                  "policies.create.customType",
                  "Custom policy type",
                )}
                value={createDialog.custom_policy_type}
                onChange={(e) =>
                  setCreateDialog((prev) => ({
                    ...prev,
                    custom_policy_type: e.target.value,
                  }))
                }
                fullWidth
              />
            )}
            <TextField
              label={t("policies.create.name", "Name")}
              value={createDialog.name}
              onChange={(e) =>
                setCreateDialog((prev) => ({
                  ...prev,
                  name: e.target.value,
                }))
              }
              fullWidth
              required
            />
            <TextField
              label={t("policies.create.description", "Description")}
              value={createDialog.description}
              onChange={(e) =>
                setCreateDialog((prev) => ({
                  ...prev,
                  description: e.target.value,
                }))
              }
              fullWidth
              multiline
              rows={2}
            />
            <TextField
              label={t("policies.create.definition", "Definition (JSON)")}
              value={createDialog.definition_text}
              onChange={(e) =>
                setCreateDialog((prev) => ({
                  ...prev,
                  definition_text: e.target.value,
                }))
              }
              fullWidth
              multiline
              minRows={6}
              slotProps={{
                input: { sx: { fontFamily: "monospace", fontSize: "0.85rem" } },
              }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setCreateDialog(EMPTY_CREATE)}
            disabled={createDialog.submitting}
          >
            {t("policies.create.cancel", "Cancel")}
          </Button>
          <Button
            variant="contained"
            onClick={handleSubmitCreate}
            disabled={
              createDialog.submitting || !createDialog.name.trim()
            }
          >
            {t("policies.create.submit", "Create")}
          </Button>
        </DialogActions>
      </Dialog>

      {/* --- Edit dialog --------------------------------------------- */}
      <Dialog
        open={editDialog.open}
        onClose={() =>
          !editDialog.submitting &&
          setEditDialog((prev) => ({ ...prev, open: false }))
        }
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{t("policies.edit.title", "Edit policy")}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {editDialog.error && (
              <Alert severity="error">{editDialog.error}</Alert>
            )}
            <TextField
              label={t("policies.create.name", "Name")}
              value={editDialog.name}
              onChange={(e) =>
                setEditDialog((prev) => ({
                  ...prev,
                  name: e.target.value,
                }))
              }
              fullWidth
            />
            <TextField
              label={t("policies.create.description", "Description")}
              value={editDialog.description}
              onChange={(e) =>
                setEditDialog((prev) => ({
                  ...prev,
                  description: e.target.value,
                }))
              }
              fullWidth
              multiline
              rows={2}
            />
            <TextField
              label={t("policies.create.definition", "Definition (JSON)")}
              value={editDialog.definition_text}
              onChange={(e) =>
                setEditDialog((prev) => ({
                  ...prev,
                  definition_text: e.target.value,
                }))
              }
              fullWidth
              multiline
              minRows={6}
              slotProps={{
                input: { sx: { fontFamily: "monospace", fontSize: "0.85rem" } },
              }}
            />
            <DialogContentText>
              {t(
                "policies.edit.versionNote",
                "Saving will bump the policy's version; sites pick up the new version on the next push cycle.",
              )}
            </DialogContentText>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() =>
              setEditDialog((prev) => ({ ...prev, open: false }))
            }
            disabled={editDialog.submitting}
          >
            {t("policies.create.cancel", "Cancel")}
          </Button>
          <Button
            variant="contained"
            onClick={handleSubmitEdit}
            disabled={editDialog.submitting}
          >
            {t("policies.edit.submit", "Save")}
          </Button>
        </DialogActions>
      </Dialog>

      {/* --- Assign dialog ------------------------------------------- */}
      <Dialog
        open={assignDialog.open}
        onClose={() =>
          !assignDialog.submitting &&
          setAssignDialog((prev) => ({ ...prev, open: false }))
        }
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          {t("policies.assign.title", "Assign to sites")}
        </DialogTitle>
        <DialogContent>
          {assignDialog.error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {assignDialog.error}
            </Alert>
          )}
          {assignDialog.loadingSites && (
            <Box sx={{ display: "flex", justifyContent: "center", p: 2 }}>
              <CircularProgress />
            </Box>
          )}
          {!assignDialog.loadingSites && assignDialog.sites.length === 0 && (
            <DialogContentText>
              {t(
                "policies.assign.noSites",
                "No federation sites are enrolled.  Enroll a site first.",
              )}
            </DialogContentText>
          )}
          {!assignDialog.loadingSites && assignDialog.sites.length > 0 && (
            <List dense>
              {assignDialog.sites.map((site) => {
                const checked = assignDialog.selected.has(site.id);
                const assignment = assignDialog.existingAssignments.find(
                  (a) => a.site_id === site.id,
                );
                // Phase 12.10 hardening: surface retry counts +
                // dead-letter state so the operator can see WHY a
                // push isn't landing instead of just "still pending".
                let secondary: React.ReactNode;
                if (assignment) {
                  const attempts = assignment.push_attempts ?? 0;
                  const statusLine =
                    attempts > 0
                      ? t(
                          "policies.assign.statusLineWithAttempts",
                          "Push status: {{status}} ({{attempts}} attempts)",
                          { status: assignment.push_status, attempts },
                        )
                      : t(
                          "policies.assign.statusLine",
                          "Push status: {{status}}",
                          { status: assignment.push_status },
                        );
                  secondary = (
                    <>
                      {statusLine}
                      {assignment.last_push_error && (
                        <Typography
                          variant="caption"
                          color="error.main"
                          component="div"
                          sx={{ mt: 0.25, wordBreak: "break-word" }}
                        >
                          {assignment.last_push_error}
                        </Typography>
                      )}
                    </>
                  );
                } else {
                  secondary = site.location_label || site.url;
                }
                const isDead = assignment?.push_status === "dead";
                return (
                  <ListItem key={site.id} disablePadding>
                    <ListItemButton
                      onClick={() => handleToggleAssignSite(site.id)}
                    >
                      <Checkbox edge="start" checked={checked} tabIndex={-1} />
                      <ListItemText
                        primary={
                          <Stack direction="row" spacing={1} alignItems="center">
                            <span>{site.name}</span>
                            {isDead && (
                              <Chip
                                label={t("policies.deadLetter", "dead-letter")}
                                color="error"
                                size="small"
                              />
                            )}
                          </Stack>
                        }
                        secondary={secondary}
                      />
                    </ListItemButton>
                  </ListItem>
                );
              })}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() =>
              setAssignDialog((prev) => ({ ...prev, open: false }))
            }
            disabled={assignDialog.submitting}
          >
            {t("policies.create.cancel", "Cancel")}
          </Button>
          <Button
            variant="contained"
            onClick={handleSubmitAssign}
            disabled={
              assignDialog.submitting || assignDialog.loadingSites
            }
          >
            {t("policies.assign.submit", "Save assignments")}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={toast !== null}
        onClose={() => setToast(null)}
        message={toast ?? ""}
        autoHideDuration={4000}
      />
    </Box>
  );
};

export default FederationPolicies;
