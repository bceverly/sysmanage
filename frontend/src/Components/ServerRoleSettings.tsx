/**
 * Settings → Server Role.
 *
 * Lets an operator pick this server's air-gap topology role without
 * hand-editing sysmanage.yaml.  Three mutually-exclusive choices, each
 * with an inline explanation of what it means and how it's used, so the
 * operator can make an informed decision.  Backed by the
 * GET/PUT /api/v1/server-role endpoints (server_configuration singleton).
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  FormControl,
  FormControlLabel,
  Grid,
  Radio,
  RadioGroup,
  Snackbar,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

import axiosInstance from '../Services/api';
import {
  CollectorPublicKeyCard,
  ImportDeviceCard,
  TrustedCollectorsCard,
} from './AirgapKeyManagement';
import FederationRoleCard from './FederationRoleCard';

type ServerRole = 'standard' | 'collector' | 'repository';

const ROLE_URL = '/api/v1/server-role';

interface ServerRoleResponse {
  role: string;
  valid_roles: string[];
}

const ServerRoleSettings: React.FC = () => {
  const { t } = useTranslation();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [currentRole, setCurrentRole] = useState<ServerRole>('standard');
  const [selectedRole, setSelectedRole] = useState<ServerRole>('standard');
  const [error, setError] = useState<string | null>(null);
  const [snackOpen, setSnackOpen] = useState(false);

  const fetchRole = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axiosInstance.get<ServerRoleResponse>(ROLE_URL);
      const role = (r.data.role as ServerRole) || 'standard';
      setCurrentRole(role);
      setSelectedRole(role);
      setError(null);
    } catch {
      setError(
        t('serverRole.loadError', 'Could not load the current server role.'),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchRole();
  }, [fetchRole]);

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
      setError(detail || t('serverRole.saveError', 'Could not save the server role.'));
    } finally {
      setSaving(false);
    }
  };

  // One descriptor per role: heading + what-it-means + how-it's-used.
  // Kept as data so the radio list and the explanatory copy stay in
  // lockstep and every string is a single i18n key.
  const roleOptions: Array<{
    value: ServerRole;
    title: string;
    description: string;
  }> = [
    {
      value: 'standard',
      title: t('serverRole.standard.title', 'Standard (no air gap)'),
      description: t(
        'serverRole.standard.description',
        'The default. This server manages hosts directly over the network with no air-gap separation. Choose this for any ordinary deployment — it is what every server runs as unless you specifically need one half of an air-gapped pair.',
      ),
    },
    {
      value: 'collector',
      title: t('serverRole.collector.title', 'Air-Gap Collector (online side)'),
      description: t(
        'serverRole.collector.description',
        'The internet-connected half of an air-gap pair. It mirrors upstream package repositories, gathers CVE and compliance feeds, and bundles them into signed ISO images that you physically carry across the air gap. Choose this on the server that has internet access and builds the media.',
      ),
    },
    {
      value: 'repository',
      title: t(
        'serverRole.repository.title',
        'Air-Gap Repository (disconnected side)',
      ),
      description: t(
        'serverRole.repository.description',
        'The isolated half of an air-gap pair, with no internet access. It ingests the ISO media produced by the Collector, verifies its signature, and serves the packages to managed hosts on the private network so they can update normally. Choose this on the server inside the air-gapped enclave.',
      ),
    },
  ];

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Grid container spacing={2} alignItems="flex-start">
        {/* Left card: air-gap topology role (existing). */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
      <Typography variant="h6" gutterBottom>
        {t('serverRole.heading', 'Air-Gap Role')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t(
          'serverRole.intro',
          'Choose how this SysManage server participates in an air-gapped deployment. Most servers should stay on Standard. The role takes effect after the next server restart.',
        )}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <FormControl component="fieldset" sx={{ width: '100%' }}>
        <RadioGroup
          value={selectedRole}
          onChange={(e) => setSelectedRole(e.target.value as ServerRole)}
        >
          {roleOptions.map((opt) => (
            <Box
              key={opt.value}
              sx={{
                border: 1,
                borderColor:
                  selectedRole === opt.value ? 'primary.main' : 'divider',
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
                        {t('serverRole.currentTag', '(current)')}
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

      <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving || selectedRole === currentRole}
          startIcon={saving ? <CircularProgress size={16} /> : undefined}
        >
          {saving
            ? t('serverRole.saving', 'Saving…')
            : t('serverRole.save', 'Save Role')}
        </Button>
        {selectedRole !== currentRole && (
          <Typography variant="caption" color="warning.main">
            {t(
              'serverRole.restartHint',
              'Restart the SysManage server after saving for the new role to take full effect.',
            )}
          </Typography>
        )}
      </Box>

      {/* Role-specific key management. Keyed on the *saved* role
          (currentRole), not the radio selection, so the cards reflect
          what the server actually is until a new role is saved. */}
      {currentRole === 'collector' && <CollectorPublicKeyCard />}
      {currentRole === 'repository' && (
        <>
          <ImportDeviceCard />
          <TrustedCollectorsCard />
        </>
      )}
            </CardContent>
          </Card>
        </Grid>

        {/* Right card: federation role (independent axis). */}
        <Grid size={{ xs: 12, md: 6 }}>
          <FederationRoleCard />
        </Grid>
      </Grid>

      <Snackbar
        open={snackOpen}
        autoHideDuration={5000}
        onClose={() => setSnackOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert severity="success" variant="filled" onClose={() => setSnackOpen(false)}>
          {t(
            'serverRole.saved',
            'Server role saved. Restart the server for it to take full effect.',
          )}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default ServerRoleSettings;
