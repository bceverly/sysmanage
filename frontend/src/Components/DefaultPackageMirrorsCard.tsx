/**
 * Default Package Mirrors card (Phase 10.4.4) — lives on the Host
 * Defaults settings tab.
 *
 * One row per (platform, version_key, os_family) tuple drawn from
 * the pre-populated ``mirror_known_version`` catalog.  For each row
 * the admin picks one of the eligible mirrors (filtered to the
 * right PM + ``last_sync_status == SUCCESS`` so an out-of-sync
 * mirror can't be assigned and break clients) or "Cloud (default)"
 * which reverts the assignment.
 *
 * Saving fires a simultaneous rollout: the server queues an apply
 * (or revert) plan to every active host whose ``platform_release``
 * matches the catalog row's regex.  The plans go through the
 * existing apply_deployment_plan agent path; results land in
 * ``proplus_dispatch._apply_repo_mirror_op_result``.
 */

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  FormControl,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

import {
  HostDefaultMirrorRow,
  listDefaultMirrorAssignments,
  setDefaultMirrorAssignment,
} from '../Services/repositoryMirroring';

const CLOUD_VALUE = '__cloud__';

const DefaultPackageMirrorsCard: React.FC = () => {
  const { t } = useTranslation();
  const [rows, setRows] = useState<HostDefaultMirrorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setRows(await listDefaultMirrorAssignments());
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleChange = async (row: HostDefaultMirrorRow, value: string) => {
    const key = `${row.platform}/${row.version_key}/${row.os_family}`;
    setSaving(key);
    setError(null);
    setSuccess(null);
    try {
      const result = await setDefaultMirrorAssignment(
        row.platform,
        row.version_key,
        row.os_family,
        value === CLOUD_VALUE ? null : value,
      );
      const dispatched = result.dispatched.length;
      setSuccess(
        t(
          'hostDefaults.mirror.saveSuccess',
          'Saved. {{count}} host(s) will be reconfigured.',
          { count: dispatched },
        ),
      );
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
            <CircularProgress size={28} />
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1 }}>
          {t('hostDefaults.mirror.title', 'Default Package Mirrors')}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t(
            'hostDefaults.mirror.subtitle',
            'For each supported (platform, version) pair, pick which mirror new and existing hosts of that family use as their default. Cloud means hosts hit the public upstream directly. Only mirrors that have completed a successful sync are eligible.',
          )}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        {success && (
          <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        )}
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('hostDefaults.mirror.col.platform', 'Platform')}</TableCell>
                <TableCell>{t('hostDefaults.mirror.col.version', 'Version')}</TableCell>
                <TableCell>{t('hostDefaults.mirror.col.osFamily', 'OS Family')}</TableCell>
                <TableCell>{t('hostDefaults.mirror.col.mirror', 'Default Mirror')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => {
                const key = `${row.platform}/${row.version_key}/${row.os_family}`;
                const value = row.current_mirror_id ?? CLOUD_VALUE;
                return (
                  <TableRow key={key}>
                    <TableCell>{row.platform}</TableCell>
                    <TableCell>{row.label}</TableCell>
                    <TableCell>{row.os_family}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <FormControl size="small" sx={{ minWidth: 240 }}>
                          <Select
                            value={value}
                            onChange={(e) => handleChange(row, e.target.value)}
                            disabled={saving === key}
                          >
                            <MenuItem value={CLOUD_VALUE}>
                              {t(
                                'hostDefaults.mirror.cloud',
                                'Cloud (upstream default)',
                              )}
                            </MenuItem>
                            {row.eligible_mirrors.map((m) => (
                              <MenuItem key={m.id} value={m.id}>
                                {m.name}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                        {saving === key && <CircularProgress size={20} />}
                        {row.eligible_mirrors.length === 0 && (
                          <Typography variant="caption" color="text.secondary">
                            {t(
                              'hostDefaults.mirror.noEligible',
                              'No synced mirrors available',
                            )}
                          </Typography>
                        )}
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
};

export default DefaultPackageMirrorsCard;
