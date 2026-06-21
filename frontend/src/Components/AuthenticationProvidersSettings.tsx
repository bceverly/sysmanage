/**
 * Settings panel for the Pro+ External IdP feature (Phase 10.5).
 *
 * Cross-provider settings card on top, provider list below.  The
 * per-provider create/edit dialog branches its body on ``type`` —
 * LDAP form vs. OIDC form — to keep the field set focused.  Role
 * mappings are managed through a sub-dialog opened from each
 * provider row.
 */

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import GroupWorkIcon from '@mui/icons-material/GroupWork';
import { useTranslation } from 'react-i18next';

import {
  createProvider,
  createRoleMapping,
  deleteProvider,
  deleteRoleMapping,
  getIdpSettings,
  IdpProvider,
  IdpProviderCreate,
  IdpRoleMapping,
  IdpSettings,
  listProviders,
  listRoleMappings,
  updateIdpSettings,
  updateProvider,
} from '../Services/externalIdp';

const DEFAULT_DRAFT: IdpProviderCreate = {
  name: '',
  type: 'ldap',
  enabled: true,
  ldap_connection_timeout: 10,
  oidc_scopes: 'openid profile email',
  oidc_group_claim: 'groups',
};

const AuthenticationProvidersSettings: React.FC = () => {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<IdpProvider[]>([]);
  const [settings, setSettings] = useState<IdpSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [draft, setDraft] = useState<IdpProviderCreate>({ ...DEFAULT_DRAFT });
  const [editingId, setEditingId] = useState<string | null>(null);
  // Role-mapping dialog state.
  const [mapDialogOpen, setMapDialogOpen] = useState(false);
  const [mapProviderId, setMapProviderId] = useState<string | null>(null);
  const [mappings, setMappings] = useState<IdpRoleMapping[]>([]);
  const [newMapGroup, setNewMapGroup] = useState('');
  const [newMapRole, setNewMapRole] = useState('');
  const [newMapDefault, setNewMapDefault] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, s] = await Promise.all([listProviders(), getIdpSettings()]);
      setProviders(p);
      setSettings(s);
    } catch {
      setError(t('idp.loadError', 'Could not load Identity Providers.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // refresh is stable; mount-only fetch is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openCreate = () => {
    setDraft({ ...DEFAULT_DRAFT });
    setEditingId(null);
    setDialogOpen(true);
  };

  const openEdit = (p: IdpProvider) => {
    // Coerce nulls to undefined so the draft type matches IdpProviderCreate.
    const coerce = (v: string | null | undefined) => v ?? undefined;
    setDraft({
      name: p.name,
      type: p.type,
      enabled: p.enabled,
      ldap_server_url: coerce(p.ldap_server_url),
      ldap_bind_dn: coerce(p.ldap_bind_dn),
      ldap_bind_password_secret_id: coerce(p.ldap_bind_password_secret_id),
      ldap_user_search_base: coerce(p.ldap_user_search_base),
      ldap_user_search_filter: coerce(p.ldap_user_search_filter),
      ldap_group_search_base: coerce(p.ldap_group_search_base),
      ldap_group_search_filter: coerce(p.ldap_group_search_filter),
      ldap_tls_ca_bundle_path: coerce(p.ldap_tls_ca_bundle_path),
      ldap_connection_timeout: p.ldap_connection_timeout ?? 10,
      oidc_issuer_url: coerce(p.oidc_issuer_url),
      oidc_client_id: coerce(p.oidc_client_id),
      oidc_client_secret_secret_id: coerce(p.oidc_client_secret_secret_id),
      oidc_redirect_uri: coerce(p.oidc_redirect_uri),
      oidc_scopes: p.oidc_scopes ?? 'openid profile email',
      oidc_discovery_url: coerce(p.oidc_discovery_url),
      oidc_group_claim: p.oidc_group_claim ?? 'groups',
    });
    setEditingId(p.id);
    setDialogOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      if (editingId) {
        await updateProvider(editingId, draft);
      } else {
        await createProvider(draft);
      }
      setDialogOpen(false);
      await refresh();
    } catch {
      setError(t('idp.saveError', 'Could not save provider — check the form.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!globalThis.confirm(t('idp.deleteConfirm', 'Delete this provider?'))) return;
    try {
      await deleteProvider(id);
      await refresh();
    } catch {
      setError(t('idp.deleteError', 'Could not delete provider.'));
    }
  };

  const handleSettingsSave = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateIdpSettings(settings);
      setSettings(updated);
    } catch {
      setError(t('idp.settingsSaveError', 'Could not save settings.'));
    } finally {
      setSaving(false);
    }
  };

  const openMappings = async (providerId: string) => {
    setMapProviderId(providerId);
    setMapDialogOpen(true);
    try {
      setMappings(await listRoleMappings(providerId));
    } catch {
      setMappings([]);
    }
  };

  const addMapping = async () => {
    if (!mapProviderId || !newMapGroup.trim() || !newMapRole.trim()) return;
    try {
      await createRoleMapping(mapProviderId, {
        external_group: newMapGroup.trim(),
        role_name: newMapRole.trim(),
        default_for_unmapped: newMapDefault,
      });
      setNewMapGroup('');
      setNewMapRole('');
      setNewMapDefault(false);
      setMappings(await listRoleMappings(mapProviderId));
    } catch {
      setError(t('idp.mapAddError', 'Could not add mapping.'));
    }
  };

  const removeMapping = async (mappingId: string) => {
    if (!mapProviderId) return;
    try {
      await deleteRoleMapping(mapProviderId, mappingId);
      setMappings(await listRoleMappings(mapProviderId));
    } catch {
      setError(t('idp.mapDeleteError', 'Could not delete mapping.'));
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {settings && (
        <Card variant="outlined" sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 2 }}>
              {t('idp.settingsTitle', 'Authentication Settings')}
            </Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="center">
              <FormControlLabel
                control={
                  <Switch
                    checked={settings.local_account_fallback}
                    onChange={(e) =>
                      setSettings({ ...settings, local_account_fallback: e.target.checked })
                    }
                  />
                }
                label={t('idp.fallback', 'Allow local-password fallback (break-glass admin)')}
              />
              <TextField
                label={t('idp.maxFailures', 'Max failed external attempts before lockout')}
                type="number"
                value={settings.max_failed_attempts}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    max_failed_attempts: Number.parseInt(e.target.value, 10) || 5,
                  })
                }
                sx={{ width: 280 }}
              />
              <Button variant="contained" disabled={saving} onClick={handleSettingsSave}>
                {saving ? <CircularProgress size={20} /> : t('common.save', 'Save')}
              </Button>
            </Stack>
          </CardContent>
        </Card>
      )}

      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="h6">
              {t('idp.providersTitle', 'Identity Providers')}
            </Typography>
            <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
              {t('idp.add', 'Add Provider')}
            </Button>
          </Stack>
          {providers.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('idp.empty', 'No identity providers configured yet.')}
            </Typography>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('idp.col.name', 'Name')}</TableCell>
                    <TableCell>{t('idp.col.type', 'Type')}</TableCell>
                    <TableCell>{t('idp.col.endpoint', 'Endpoint / Issuer')}</TableCell>
                    <TableCell>{t('idp.col.enabled', 'Enabled')}</TableCell>
                    <TableCell>{t('idp.col.actions', 'Actions')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {providers.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell>{p.name}</TableCell>
                      <TableCell>
                        <Chip
                          label={p.type.toUpperCase()}
                          size="small"
                          color={p.type === 'oidc' ? 'primary' : 'default'}
                        />
                      </TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                        {p.type === 'ldap' ? p.ldap_server_url : p.oidc_issuer_url}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={p.enabled ? 'on' : 'off'}
                          size="small"
                          color={p.enabled ? 'success' : 'default'}
                        />
                      </TableCell>
                      <TableCell>
                        <IconButton size="small" onClick={() => openMappings(p.id)} title={t('idp.action.mappings', 'Role mappings')}>
                          <GroupWorkIcon fontSize="small" />
                        </IconButton>
                        <IconButton size="small" onClick={() => openEdit(p)} title={t('idp.action.edit', 'Edit')}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                        <IconButton size="small" onClick={() => handleDelete(p.id)} title={t('idp.action.delete', 'Delete')}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Create/Edit dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingId ? t('idp.editTitle', 'Edit Provider') : t('idp.addTitle', 'Add Provider')}
        </DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Stack spacing={2}>
            <TextField
              label={t('idp.field.name', 'Display name')}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              required
              fullWidth
              autoFocus
            />
            <FormControl fullWidth>
              <InputLabel>{t('idp.field.type', 'Type')}</InputLabel>
              <Select
                value={draft.type}
                label={t('idp.field.type', 'Type')}
                onChange={(e) =>
                  setDraft({ ...draft, type: e.target.value })
                }
                disabled={!!editingId}
              >
                <MenuItem value="ldap">{t('idp.type.ldap', 'LDAP / Active Directory')}</MenuItem>
                <MenuItem value="oidc">{t('idp.type.oidc', 'OIDC')}</MenuItem>
              </Select>
            </FormControl>
            <FormControlLabel
              control={
                <Switch
                  checked={!!draft.enabled}
                  onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
                />
              }
              label={t('idp.field.enabled', 'Enabled')}
            />

            {draft.type === 'ldap' && (
              <>
                <TextField
                  label={t('idp.field.ldapServer', 'LDAP server URL (ldaps://...)')}
                  value={draft.ldap_server_url ?? ''}
                  onChange={(e) => setDraft({ ...draft, ldap_server_url: e.target.value })}
                  fullWidth
                  required
                />
                <TextField
                  label={t('idp.field.bindDn', 'Bind DN (service account)')}
                  value={draft.ldap_bind_dn ?? ''}
                  onChange={(e) => setDraft({ ...draft, ldap_bind_dn: e.target.value })}
                  fullWidth
                />
                <TextField
                  label={t('idp.field.bindSecret', 'Bind password (Vault secret id)')}
                  helperText={t('idp.field.bindSecretHelp', 'Reference like vault:secret/path or literal:plaintext')}
                  value={draft.ldap_bind_password_secret_id ?? ''}
                  onChange={(e) =>
                    setDraft({ ...draft, ldap_bind_password_secret_id: e.target.value })
                  }
                  fullWidth
                />
                <TextField
                  label={t('idp.field.userBase', 'User search base')}
                  value={draft.ldap_user_search_base ?? ''}
                  onChange={(e) =>
                    setDraft({ ...draft, ldap_user_search_base: e.target.value })
                  }
                  fullWidth
                  required
                />
                <TextField
                  label={t('idp.field.userFilter', 'User search filter')}
                  helperText={t('idp.field.userFilterHelp', 'Must contain %s for the username, e.g. (sAMAccountName=%s)')}
                  value={draft.ldap_user_search_filter ?? ''}
                  onChange={(e) =>
                    setDraft({ ...draft, ldap_user_search_filter: e.target.value })
                  }
                  fullWidth
                  required
                />
                <TextField
                  label={t('idp.field.groupBase', 'Group search base (optional)')}
                  value={draft.ldap_group_search_base ?? ''}
                  onChange={(e) =>
                    setDraft({ ...draft, ldap_group_search_base: e.target.value })
                  }
                  fullWidth
                />
                <TextField
                  label={t('idp.field.groupFilter', 'Group search filter (optional)')}
                  helperText={t('idp.field.groupFilterHelp', 'e.g. (member=%s) — %s is the user DN')}
                  value={draft.ldap_group_search_filter ?? ''}
                  onChange={(e) =>
                    setDraft({ ...draft, ldap_group_search_filter: e.target.value })
                  }
                  fullWidth
                />
                <TextField
                  label={t('idp.field.caBundle', 'TLS CA bundle path (optional)')}
                  value={draft.ldap_tls_ca_bundle_path ?? ''}
                  onChange={(e) =>
                    setDraft({ ...draft, ldap_tls_ca_bundle_path: e.target.value })
                  }
                  fullWidth
                />
                <TextField
                  label={t('idp.field.timeout', 'Connection timeout (s)')}
                  type="number"
                  value={draft.ldap_connection_timeout ?? 10}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      ldap_connection_timeout:
                        Number.parseInt(e.target.value, 10) || 10,
                    })
                  }
                  fullWidth
                />
              </>
            )}

            {draft.type === 'oidc' && (
              <>
                <TextField
                  label={t('idp.field.issuer', 'OIDC issuer URL')}
                  value={draft.oidc_issuer_url ?? ''}
                  onChange={(e) => setDraft({ ...draft, oidc_issuer_url: e.target.value })}
                  fullWidth
                  required
                />
                <TextField
                  label={t('idp.field.clientId', 'Client ID')}
                  value={draft.oidc_client_id ?? ''}
                  onChange={(e) => setDraft({ ...draft, oidc_client_id: e.target.value })}
                  fullWidth
                  required
                />
                <TextField
                  label={t('idp.field.clientSecret', 'Client secret (Vault secret id)')}
                  helperText={t('idp.field.clientSecretHelp', 'Reference like vault:secret/path or literal:plaintext')}
                  value={draft.oidc_client_secret_secret_id ?? ''}
                  onChange={(e) =>
                    setDraft({ ...draft, oidc_client_secret_secret_id: e.target.value })
                  }
                  fullWidth
                />
                <TextField
                  label={t('idp.field.redirect', 'Redirect URI')}
                  value={draft.oidc_redirect_uri ?? ''}
                  onChange={(e) => setDraft({ ...draft, oidc_redirect_uri: e.target.value })}
                  fullWidth
                  required
                />
                <TextField
                  label={t('idp.field.scopes', 'Scopes')}
                  value={draft.oidc_scopes ?? 'openid profile email'}
                  onChange={(e) => setDraft({ ...draft, oidc_scopes: e.target.value })}
                  fullWidth
                />
                <TextField
                  label={t('idp.field.discovery', 'Discovery URL override (optional)')}
                  value={draft.oidc_discovery_url ?? ''}
                  onChange={(e) => setDraft({ ...draft, oidc_discovery_url: e.target.value })}
                  fullWidth
                />
                <TextField
                  label={t('idp.field.groupClaim', 'Group claim name')}
                  value={draft.oidc_group_claim ?? 'groups'}
                  onChange={(e) => setDraft({ ...draft, oidc_group_claim: e.target.value })}
                  fullWidth
                />
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
          <Button variant="contained" disabled={saving || !draft.name} onClick={handleSave}>
            {saving ? <CircularProgress size={20} /> : t('common.save', 'Save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Role mapping dialog */}
      <Dialog
        open={mapDialogOpen}
        onClose={() => setMapDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{t('idp.mappingsTitle', 'Group → Role Mappings')}</DialogTitle>
        <DialogContent>
          <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
            <TextField
              label={t('idp.mapping.group', 'External group')}
              value={newMapGroup}
              onChange={(e) => setNewMapGroup(e.target.value)}
              size="small"
              fullWidth
            />
            <TextField
              label={t('idp.mapping.role', 'sysmanage role name')}
              value={newMapRole}
              onChange={(e) => setNewMapRole(e.target.value)}
              size="small"
              fullWidth
            />
            <FormControlLabel
              control={
                <Switch
                  checked={newMapDefault}
                  onChange={(e) => setNewMapDefault(e.target.checked)}
                />
              }
              label={t('idp.mapping.default', 'Default')}
            />
            <Button variant="contained" onClick={addMapping}>
              {t('common.add', 'Add')}
            </Button>
          </Stack>
          {mappings.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('idp.mapping.empty', 'No mappings yet.')}
            </Typography>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('idp.mapping.col.group', 'External group')}</TableCell>
                    <TableCell>{t('idp.mapping.col.role', 'Role')}</TableCell>
                    <TableCell>{t('idp.mapping.col.default', 'Default?')}</TableCell>
                    <TableCell>{t('idp.col.actions', 'Actions')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {mappings.map((m) => (
                    <TableRow key={m.id}>
                      <TableCell>{m.external_group}</TableCell>
                      <TableCell>{m.role_name}</TableCell>
                      <TableCell>{m.default_for_unmapped ? '✓' : ''}</TableCell>
                      <TableCell>
                        <IconButton size="small" onClick={() => removeMapping(m.id)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMapDialogOpen(false)}>{t('common.close', 'Close')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default AuthenticationProvidersSettings;
