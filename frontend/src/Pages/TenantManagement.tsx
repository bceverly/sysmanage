/**
 * Tenant Management — the control-plane admin UI (Phase 13.1).
 *
 * Surfaces the multi-tenancy "registry" so operators can manage tenants
 * without hand-calling the API:
 *   - List + create tenants
 *   - Per selected tenant:
 *       - Email-domain allowlist (add / remove)
 *       - Members (email→tenant grants: add by email, change role, revoke)
 *       - DB placement (host/port/dbname/region/tier/openbao_role) + provision
 *
 * Gated on the server's ``multitenancy.enabled``: when disabled (the
 * single-tenant / homelab default) the page shows an info panel instead of
 * the management surface — there's exactly one implicit tenant (the server).
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import FormControlLabel from '@mui/material/FormControlLabel';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

import {
  controlPlaneService,
  EmailDomainSummary,
  GrantSummary,
  PlacementSummary,
  TenantSummary,
} from '../Services/controlPlane';

const PLACEMENT_TIERS = ['silo', 'pool'];

interface Toast {
  message: string;
  severity: 'success' | 'error' | 'info';
}

function errMessage(err: unknown, fallback: string): string {
  if (
    typeof err === 'object' &&
    err !== null &&
    'response' in err &&
    (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
  ) {
    return (err as { response: { data: { detail: string } } }).response.data.detail;
  }
  return fallback;
}

const TenantManagement: React.FC = () => {
  const { t } = useTranslation();

  const [loading, setLoading] = useState(true);
  const [mtEnabled, setMtEnabled] = useState(false);
  const [selfService, setSelfService] = useState(false);
  const [provisionerConfigured, setProvisionerConfigured] = useState(false);
  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [selected, setSelected] = useState<TenantSummary | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  // New-tenant dialog
  const [newOpen, setNewOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newSlug, setNewSlug] = useState('');

  const notify = useCallback((message: string, severity: Toast['severity']) => {
    setToast({ message, severity });
  }, []);

  const loadTenants = useCallback(async () => {
    const list = await controlPlaneService.listTenants();
    setTenants(list);
    return list;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await controlPlaneService.getStatus();
        if (cancelled) return;
        setMtEnabled(status.multitenancy_enabled);
        setSelfService(Boolean(status.self_service_provisioning));
        setProvisionerConfigured(Boolean(status.provisioner_configured));
        if (status.multitenancy_enabled) {
          await loadTenants();
        }
      } catch (err) {
        if (!cancelled) {
          // 404 → the control-plane router isn't mounted (multi-tenancy is
          // disabled); show the disabled panel rather than an error.
          const status =
            typeof err === 'object' &&
            err !== null &&
            'response' in err
              ? (err as { response?: { status?: number } }).response?.status
              : undefined;
          if (status === 404) {
            setMtEnabled(false);
          } else {
            notify(
              errMessage(err, t('tenants.loadError', 'Failed to load tenants')),
              'error',
            );
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadTenants, notify, t]);

  const handleCreateTenant = async () => {
    try {
      const created = await controlPlaneService.createTenant(
        newName.trim(),
        newSlug.trim(),
      );
      setNewOpen(false);
      setNewName('');
      setNewSlug('');
      const list = await loadTenants();
      setSelected(list.find((x) => x.id === created.id) ?? created);
      notify(t('tenants.created', 'Tenant created'), 'success');
    } catch (err) {
      notify(errMessage(err, t('tenants.createError', 'Failed to create tenant')), 'error');
    }
  };

  if (loading) {
    return (
      <Box sx={{ p: 3, display: 'flex', justifyContent: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!mtEnabled) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h4" gutterBottom>
          {t('tenants.title', 'Tenant Management')}
        </Typography>
        <Alert severity="info">
          <Typography variant="subtitle1" component="div">
            {t('tenants.disabledTitle', 'Multi-tenancy is disabled')}
          </Typography>
          {t(
            'tenants.disabledBody',
            'This server runs in single-tenant mode — there is one implicit tenant (the server itself). Enable "multitenancy.enabled" in sysmanage.yaml and restart to manage multiple tenants here.',
          )}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: 2,
        }}
      >
        <Typography variant="h4">{t('tenants.title', 'Tenant Management')}</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setNewOpen(true)}
        >
          {t('tenants.new', 'New Tenant')}
        </Button>
      </Box>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
        {/* Tenant list */}
        <Paper sx={{ flex: '0 0 360px', width: { xs: '100%', md: 360 } }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('tenants.name', 'Name')}</TableCell>
                <TableCell>{t('tenants.slug', 'Slug')}</TableCell>
                <TableCell>{t('tenants.status', 'Status')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {tenants.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3}>
                    <Typography variant="body2" color="text.secondary">
                      {t('tenants.none', 'No tenants yet')}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {tenants.map((tenant) => (
                <TableRow
                  key={tenant.id}
                  hover
                  selected={selected?.id === tenant.id}
                  onClick={() => setSelected(tenant)}
                  sx={{ cursor: 'pointer' }}
                >
                  <TableCell>{tenant.name}</TableCell>
                  <TableCell>{tenant.slug}</TableCell>
                  <TableCell>
                    <Chip size="small" label={tenant.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>

        {/* Detail panel */}
        <Box sx={{ flex: 1, minWidth: 0, width: '100%' }}>
          {selected ? (
            <TenantDetail
              tenant={selected}
              notify={notify}
              t={t}
              selfService={selfService}
              provisionerConfigured={provisionerConfigured}
              onDeleted={async () => {
                setSelected(null);
                await loadTenants();
              }}
            />
          ) : (
            <Paper sx={{ p: 3 }}>
              <Typography variant="body2" color="text.secondary">
                {t('tenants.selectPrompt', 'Select a tenant to manage its domains, members, and placement.')}
              </Typography>
            </Paper>
          )}
        </Box>
      </Stack>

      {/* New tenant dialog */}
      <Dialog open={newOpen} onClose={() => setNewOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('tenants.new', 'New Tenant')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('tenants.name', 'Name')}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              fullWidth
              autoFocus
            />
            <TextField
              label={t('tenants.slug', 'Slug')}
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
              helperText={t('tenants.slugHelp', 'Unique, URL-safe identifier (e.g. acme)')}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
          <Button
            variant="contained"
            disabled={!newName.trim() || !newSlug.trim()}
            onClick={handleCreateTenant}
          >
            {t('common.create', 'Create')}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!toast}
        autoHideDuration={5000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {toast ? (
          <Alert severity={toast.severity} onClose={() => setToast(null)}>
            {toast.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </Box>
  );
};

// ---------------------------------------------------------------------------
// Per-tenant detail: email domains, members, placement.
// ---------------------------------------------------------------------------

interface DetailProps {
  tenant: TenantSummary;
  notify: (message: string, severity: Toast['severity']) => void;
  t: TFunction;
}

interface TenantDetailProps extends DetailProps {
  selfService: boolean;
  provisionerConfigured: boolean;
  onDeleted: () => void | Promise<void>;
}

const TenantDetail: React.FC<TenantDetailProps> = ({
  tenant,
  notify,
  t,
  selfService,
  provisionerConfigured,
  onDeleted,
}) => {
  // Bumped after a successful auto-provision so the Placement section remounts
  // and shows the coordinates the server just populated.
  const [placementRefresh, setPlacementRefresh] = useState(0);
  const [deleteOpen, setDeleteOpen] = useState(false);
  return (
    <Stack spacing={2}>
      <Paper
        sx={{
          p: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <Typography variant="h6">{tenant.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            {tenant.slug} · {tenant.id}
          </Typography>
        </div>
        <Button
          color="error"
          variant="outlined"
          startIcon={<DeleteIcon />}
          onClick={() => setDeleteOpen(true)}
        >
          {t('tenants.delete.button', 'Delete')}
        </Button>
      </Paper>

      <DeleteTenantDialog
        tenant={tenant}
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        notify={notify}
        t={t}
        onDeleted={onDeleted}
      />

      {selfService && (
        <AutoProvisionSection
          tenant={tenant}
          notify={notify}
          t={t}
          provisionerConfigured={provisionerConfigured}
          onProvisioned={() => setPlacementRefresh((n) => n + 1)}
        />
      )}
      <EmailDomainSection tenant={tenant} notify={notify} t={t} />
      <MembersSection tenant={tenant} notify={notify} t={t} />
      <PlacementSection
        key={`placement-${tenant.id}-${placementRefresh}`}
        tenant={tenant}
        notify={notify}
        t={t}
      />
    </Stack>
  );
};

interface DeleteDialogProps {
  tenant: TenantSummary;
  open: boolean;
  onClose: () => void;
  notify: (message: string, severity: Toast['severity']) => void;
  t: TFunction;
  onDeleted: () => void | Promise<void>;
}

const DeleteTenantDialog: React.FC<DeleteDialogProps> = ({
  tenant,
  open,
  onClose,
  notify,
  t,
  onDeleted,
}) => {
  const [confirm, setConfirm] = useState('');
  const [dropDatabase, setDropDatabase] = useState(false);
  const [busy, setBusy] = useState(false);

  const close = () => {
    if (busy) return;
    setConfirm('');
    setDropDatabase(false);
    onClose();
  };

  const run = async () => {
    setBusy(true);
    try {
      await controlPlaneService.deleteTenant(tenant.id, {
        confirm,
        dropDatabase,
      });
      notify(
        t('tenants.delete.done', 'Tenant deleted') + ` — ${tenant.slug}`,
        'success',
      );
      setConfirm('');
      setDropDatabase(false);
      onClose();
      await onDeleted();
    } catch (err) {
      notify(errMessage(err, t('tenants.delete.error', 'Failed to delete tenant')), 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm">
      <DialogTitle sx={{ color: 'error.main' }}>
        {t('tenants.delete.title', 'Delete tenant')} — {tenant.slug}
      </DialogTitle>
      <DialogContent>
        <Alert severity="error" sx={{ mb: 2 }}>
          {t(
            'tenants.delete.warning',
            'This permanently removes the tenant, its members, email-domain allowlist, placement, and its OpenBAO credentials role. This cannot be undone.',
          )}
        </Alert>
        <FormControlLabel
          control={
            <Checkbox
              checked={dropDatabase}
              onChange={(e) => setDropDatabase(e.target.checked)}
            />
          }
          label={t(
            'tenants.delete.dropDb',
            'Also DROP the tenant database — irreversible data loss',
          )}
        />
        {dropDatabase && (
          <Alert severity="warning" sx={{ my: 1 }}>
            {t(
              'tenants.delete.dropDbWarn',
              'The entire tenant database and all its data will be destroyed.',
            )}
          </Alert>
        )}
        <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>
          {t('tenants.delete.confirmPrompt', 'Type the tenant slug to confirm:')}{' '}
          <strong>{tenant.slug}</strong>
        </Typography>
        <TextField
          fullWidth
          size="small"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder={tenant.slug}
          autoFocus
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={close} disabled={busy}>
          {t('common.cancel', 'Cancel')}
        </Button>
        <Button
          color="error"
          variant="contained"
          disabled={busy || confirm !== tenant.slug}
          onClick={run}
        >
          {busy
            ? t('tenants.delete.deleting', 'Deleting…')
            : t('tenants.delete.button', 'Delete')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

interface AutoProvisionProps extends DetailProps {
  provisionerConfigured: boolean;
  onProvisioned: () => void;
}

const AutoProvisionSection: React.FC<AutoProvisionProps> = ({
  tenant,
  notify,
  t,
  provisionerConfigured,
  onProvisioned,
}) => {
  const [busy, setBusy] = useState(false);
  const [host, setHost] = useState('localhost');
  const [region, setRegion] = useState('');

  const run = async () => {
    setBusy(true);
    try {
      const res = await controlPlaneService.autoProvision(tenant.id, {
        host: host || null,
        region: region || null,
        tier: 'silo',
      });
      notify(
        t('tenants.autoProvision.done', 'Tenant provisioned') +
          ` — ${res.dbname}` +
          (res.revision ? ` (rev ${res.revision})` : ''),
        'success',
      );
      onProvisioned();
    } catch (err) {
      notify(
        errMessage(err, t('tenants.autoProvision.error', 'Auto-provisioning failed')),
        'error',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Accordion defaultExpanded>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography>{t('tenants.autoProvision.title', 'Auto-Provision')}</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t(
            'tenants.autoProvision.help',
            'Create this tenant’s database and OpenBAO credentials role, set placement, and run migrations — no command line needed.',
          )}
        </Typography>
        {!provisionerConfigured && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t(
              'tenants.autoProvision.notBootstrapped',
              'The provisioner identity is not configured. Run "make provision-bootstrap" once before auto-provisioning.',
            )}
          </Alert>
        )}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
          <TextField
            size="small"
            label={t('tenants.placement.host', 'Host')}
            value={host}
            onChange={(e) => setHost(e.target.value)}
            sx={{ flex: 2 }}
          />
          <TextField
            size="small"
            label={t('tenants.placement.region', 'Region')}
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            sx={{ flex: 1 }}
          />
        </Stack>
        <Button
          variant="contained"
          onClick={run}
          disabled={busy || !provisionerConfigured}
        >
          {busy
            ? t('tenants.autoProvision.running', 'Provisioning…')
            : t('tenants.autoProvision.run', 'Auto-Provision Tenant')}
        </Button>
      </AccordionDetails>
    </Accordion>
  );
};

const EmailDomainSection: React.FC<DetailProps> = ({ tenant, notify, t }) => {
  const [domains, setDomains] = useState<EmailDomainSummary[]>([]);
  const [newDomain, setNewDomain] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDomains(await controlPlaneService.listEmailDomains(tenant.id));
    } catch (err) {
      notify(errMessage(err, t('tenants.domains.loadError', 'Failed to load domains')), 'error');
    } finally {
      setLoading(false);
    }
  }, [tenant.id, notify, t]);

  useEffect(() => {
    load();
  }, [load]);

  const add = async () => {
    try {
      await controlPlaneService.addEmailDomain(tenant.id, newDomain.trim());
      setNewDomain('');
      await load();
      notify(t('tenants.domains.added', 'Domain added'), 'success');
    } catch (err) {
      notify(errMessage(err, t('tenants.domains.addError', 'Failed to add domain')), 'error');
    }
  };

  const remove = async (id: string) => {
    try {
      await controlPlaneService.deleteEmailDomain(tenant.id, id);
      await load();
      notify(t('tenants.domains.removed', 'Domain removed'), 'success');
    } catch (err) {
      notify(errMessage(err, t('tenants.domains.removeError', 'Failed to remove domain')), 'error');
    }
  };

  return (
    <Accordion defaultExpanded>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography>{t('tenants.domains.title', 'Email-Domain Allowlist')}</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t(
            'tenants.domains.help',
            'Users whose email domain is on this list may be granted access to the tenant. An empty list means no domain restriction.',
          )}
        </Typography>
        {loading ? (
          <CircularProgress size={20} />
        ) : (
          <>
            <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
              <TextField
                size="small"
                label={t('tenants.domains.domain', 'Domain')}
                placeholder="acme.com"
                value={newDomain}
                onChange={(e) => setNewDomain(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newDomain.trim()) add();
                }}
              />
              <Button
                variant="outlined"
                startIcon={<AddIcon />}
                disabled={!newDomain.trim()}
                onClick={add}
              >
                {t('common.add', 'Add')}
              </Button>
            </Stack>
            {domains.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('tenants.domains.none', 'No domains — any domain is allowed.')}
              </Typography>
            ) : (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {domains.map((d) => (
                  <Chip
                    key={d.id}
                    label={d.domain}
                    onDelete={() => remove(d.id)}
                    deleteIcon={<DeleteIcon />}
                  />
                ))}
              </Stack>
            )}
          </>
        )}
      </AccordionDetails>
    </Accordion>
  );
};

const MembersSection: React.FC<DetailProps> = ({ tenant, notify, t }) => {
  const [grants, setGrants] = useState<GrantSummary[]>([]);
  const [emails, setEmails] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState('member');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await controlPlaneService.listGrants({ tenant_id: tenant.id });
      setGrants(list);
      // Resolve user emails for display (best-effort, one lookup per user).
      const users = await controlPlaneService.listUsers();
      const map: Record<string, string> = {};
      users.forEach((u) => {
        map[u.id] = u.email;
      });
      setEmails(map);
    } catch (err) {
      notify(errMessage(err, t('tenants.members.loadError', 'Failed to load members')), 'error');
    } finally {
      setLoading(false);
    }
  }, [tenant.id, notify, t]);

  useEffect(() => {
    load();
  }, [load]);

  const add = async () => {
    try {
      const user = await controlPlaneService.ensureUser(newEmail.trim());
      await controlPlaneService.createGrant({
        user_id: user.id,
        tenant_id: tenant.id,
        role: newRole,
      });
      setNewEmail('');
      setNewRole('member');
      await load();
      notify(t('tenants.members.added', 'Member added'), 'success');
    } catch (err) {
      notify(errMessage(err, t('tenants.members.addError', 'Failed to add member')), 'error');
    }
  };

  const revoke = async (grantId: string) => {
    try {
      await controlPlaneService.deleteGrant(grantId);
      await load();
      notify(t('tenants.members.revoked', 'Member revoked'), 'success');
    } catch (err) {
      notify(errMessage(err, t('tenants.members.revokeError', 'Failed to revoke member')), 'error');
    }
  };

  return (
    <Accordion>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography>{t('tenants.members.title', 'Members')}</Typography>
      </AccordionSummary>
      <AccordionDetails>
        {loading ? (
          <CircularProgress size={20} />
        ) : (
          <>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 2 }}>
              <TextField
                size="small"
                label={t('tenants.members.email', 'Email')}
                placeholder="user@acme.com"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                sx={{ flex: 1 }}
              />
              <TextField
                size="small"
                select
                label={t('tenants.members.role', 'Role')}
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                sx={{ minWidth: 140 }}
              >
                <MenuItem value="member">member</MenuItem>
                <MenuItem value="admin">admin</MenuItem>
              </TextField>
              <Button
                variant="outlined"
                startIcon={<AddIcon />}
                disabled={!newEmail.trim()}
                onClick={add}
              >
                {t('common.add', 'Add')}
              </Button>
            </Stack>
            <Divider sx={{ mb: 1 }} />
            {grants.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('tenants.members.none', 'No members yet.')}
              </Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('tenants.members.email', 'Email')}</TableCell>
                    <TableCell>{t('tenants.members.role', 'Role')}</TableCell>
                    <TableCell>{t('tenants.members.expires', 'Expires')}</TableCell>
                    <TableCell align="right" />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {grants.map((g) => (
                    <TableRow key={g.id}>
                      <TableCell>{emails[g.user_id] ?? g.user_id}</TableCell>
                      <TableCell>
                        <Chip size="small" label={g.role} />
                      </TableCell>
                      <TableCell>{g.expires_at ?? '—'}</TableCell>
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          aria-label={t('tenants.members.revoke', 'Revoke')}
                          onClick={() => revoke(g.id)}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </>
        )}
      </AccordionDetails>
    </Accordion>
  );
};

const PlacementSection: React.FC<DetailProps> = ({ tenant, notify, t }) => {
  const [placement, setPlacement] = useState<PlacementSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [provisioning, setProvisioning] = useState(false);
  const [form, setForm] = useState({
    host: '',
    port: '',
    dbname: '',
    region: '',
    tier: 'silo',
    openbao_role: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = await controlPlaneService.getPlacement(tenant.id);
      setPlacement(p);
      if (p) {
        setForm({
          host: p.host ?? '',
          port: p.port != null ? String(p.port) : '',
          dbname: p.dbname ?? '',
          region: p.region ?? '',
          tier: p.tier ?? 'silo',
          openbao_role: p.openbao_role ?? '',
        });
      }
    } catch (err) {
      notify(errMessage(err, t('tenants.placement.loadError', 'Failed to load placement')), 'error');
    } finally {
      setLoading(false);
    }
  }, [tenant.id, notify, t]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      const saved = await controlPlaneService.upsertPlacement(tenant.id, {
        host: form.host || null,
        port: form.port ? Number(form.port) : null,
        dbname: form.dbname || null,
        region: form.region || null,
        tier: form.tier,
        openbao_role: form.openbao_role || null,
      });
      setPlacement(saved);
      notify(t('tenants.placement.saved', 'Placement saved'), 'success');
    } catch (err) {
      notify(errMessage(err, t('tenants.placement.saveError', 'Failed to save placement')), 'error');
    } finally {
      setSaving(false);
    }
  };

  const provision = async () => {
    setProvisioning(true);
    try {
      const res = await controlPlaneService.provisionTenant(tenant.id);
      notify(
        t('tenants.placement.provisioned', 'Provisioned') +
          (res.revision ? ` (rev ${res.revision})` : ''),
        'success',
      );
    } catch (err) {
      notify(errMessage(err, t('tenants.placement.provisionError', 'Provisioning failed')), 'error');
    } finally {
      setProvisioning(false);
    }
  };

  const field = (key: keyof typeof form, label: string, extra?: object) => (
    <TextField
      size="small"
      label={label}
      value={form[key]}
      onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      {...extra}
    />
  );

  return (
    <Accordion>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography>{t('tenants.placement.title', 'Database Placement')}</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t(
            'tenants.placement.help',
            'Database coordinates for this tenant. The password is never stored here — "OpenBAO role" names the dynamic-credentials role that brokers it.',
          )}
        </Typography>
        {loading ? (
          <CircularProgress size={20} />
        ) : (
          <>
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                {field('host', t('tenants.placement.host', 'Host'), { sx: { flex: 2 } })}
                {field('port', t('tenants.placement.port', 'Port'), {
                  type: 'number',
                  sx: { flex: 1 },
                })}
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                {field('dbname', t('tenants.placement.dbname', 'Database'), { sx: { flex: 1 } })}
                {field('region', t('tenants.placement.region', 'Region'), { sx: { flex: 1 } })}
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  size="small"
                  select
                  label={t('tenants.placement.tier', 'Tier')}
                  value={form.tier}
                  onChange={(e) => setForm({ ...form, tier: e.target.value })}
                  sx={{ minWidth: 140 }}
                >
                  {PLACEMENT_TIERS.map((tier) => (
                    <MenuItem key={tier} value={tier}>
                      {tier}
                    </MenuItem>
                  ))}
                </TextField>
                {field('openbao_role', t('tenants.placement.openbaoRole', 'OpenBAO role'), {
                  sx: { flex: 1 },
                })}
              </Stack>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
              <Button variant="contained" onClick={save} disabled={saving}>
                {saving ? t('common.saving', 'Saving…') : t('common.save', 'Save')}
              </Button>
              <Button
                variant="outlined"
                onClick={provision}
                disabled={provisioning || !placement?.openbao_role}
              >
                {provisioning
                  ? t('tenants.placement.provisioning', 'Provisioning…')
                  : t('tenants.placement.provision', 'Provision Database')}
              </Button>
            </Stack>
            {!placement?.openbao_role && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                {t(
                  'tenants.placement.provisionHint',
                  'Set and save an OpenBAO role before provisioning.',
                )}
              </Typography>
            )}
          </>
        )}
      </AccordionDetails>
    </Accordion>
  );
};

export default TenantManagement;
