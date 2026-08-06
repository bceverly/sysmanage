// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CircularProgress,
  IconButton,
  MenuItem,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  DataGrid,
  GridColDef,
  GridRenderCellParams,
} from '@mui/x-data-grid';
import {
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';

import axiosInstance from '../Services/api';

const API = '/api/v1/airgap/agent-mirrors';

interface AgentMirror {
  id: string;
  channel: string;
  mirror_url: string;
  enabled: boolean;
  notes: string | null;
  updated_at: string | null;
}

/**
 * Per-channel private mirrors for the AGENT's own install channels.
 *
 * The channel list comes from the server (which reads it from the provisioning
 * engine, the same code that renders the install commands) rather than being
 * hardcoded here — a hardcoded list would let this form offer a channel the
 * renderer ignores, and the only symptom would be a provisioned host that
 * silently never enrolls.
 */
const AgentMirrorsSettings: React.FC = () => {
  const { t } = useTranslation();
  const [mirrors, setMirrors] = useState<AgentMirror[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [channel, setChannel] = useState('');
  const [url, setUrl] = useState('');

  // Deliberately depends on NOTHING.  Taking ``t`` as a dependency makes a new
  // ``load`` on every render, which the mount effect then re-runs — an endless
  // refetch loop.  The load-failure message is rendered from ``loadFailed``
  // below instead, where translating it costs nothing.
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axiosInstance.get(API);
      setMirrors(data.mirrors ?? []);
      setChannels(data.available_channels ?? []);
      setError(null);
      setLoadFailed(false);
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Only offer channels that aren't already configured — a second row for the
  // same channel is rejected server-side anyway (one row per channel), and
  // offering it invites the operator to think they can have two.
  const unconfigured = useMemo(() => {
    const taken = new Set(mirrors.map(m => m.channel));
    return channels.filter(c => !taken.has(c));
  }, [channels, mirrors]);

  const save = useCallback(async () => {
    if (!channel || !url) return;
    setSaving(true);
    try {
      await axiosInstance.put(`${API}/${channel}`, {
        channel,
        mirror_url: url,
        enabled: true,
      });
      setChannel('');
      setUrl('');
      setToast(t('agentMirrors.saved', 'Mirror saved.'));
      await load();
    } catch (err: unknown) {
      // Surface the server's reason verbatim: it is the engine's own
      // validation message, and "invalid URL" without the why is useless when
      // the rule is about shell-unsafe characters.
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(
        detail ?? t('agentMirrors.saveFailed', 'Could not save the mirror.'),
      );
    } finally {
      setSaving(false);
    }
  }, [channel, url, load, t]);

  const remove = useCallback(
    async (row: AgentMirror) => {
      try {
        await axiosInstance.delete(`${API}/${row.channel}`);
        setToast(
          t(
            'agentMirrors.removed',
            'Mirror removed; that channel installs from upstream again.',
          ),
        );
        await load();
      } catch {
        setError(t('agentMirrors.deleteFailed', 'Could not remove the mirror.'));
      }
    },
    [load, t],
  );

  const columns: GridColDef[] = useMemo(
    () => [
      {
        field: 'channel',
        headerName: t('agentMirrors.colChannel', 'Channel'),
        flex: 1,
        minWidth: 140,
      },
      {
        field: 'mirror_url',
        headerName: t('agentMirrors.colUrl', 'Mirror URL'),
        flex: 3,
        minWidth: 260,
      },
      {
        field: 'actions',
        headerName: t('agentMirrors.colActions', 'Actions'),
        sortable: false,
        filterable: false,
        width: 110,
        renderCell: (params: GridRenderCellParams) => (
          <Tooltip title={t('agentMirrors.remove', 'Remove mirror')}>
            <IconButton
              size="small"
              onClick={() => void remove(params.row as AgentMirror)}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        ),
      },
    ],
    [t, remove],
  );

  return (
    <Card>
      <CardHeader
        title={t('agentMirrors.title', 'Agent Install Mirrors')}
        subheader={t(
          'agentMirrors.subtitle',
          'Substitute a private mirror for the channels the agent itself is installed from. Without this, a host provisioned in an air-gapped site cannot reach the public PPA, COPR, OBS, winget or Homebrew tap, so it never installs an agent and never enrolls.',
        )}
        action={
          <Tooltip title={t('agentMirrors.refresh', 'Refresh')}>
            <IconButton onClick={() => void load()}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        }
      />
      <CardContent>
        {loadFailed && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {t(
              'agentMirrors.loadFailed',
              'Could not load the configured agent mirrors.',
            )}
          </Alert>
        )}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
          <TextField
            select
            size="small"
            label={t('agentMirrors.colChannel', 'Channel')}
            value={channel}
            onChange={e => setChannel(e.target.value)}
            sx={{ minWidth: 180 }}
            disabled={unconfigured.length === 0}
          >
            {unconfigured.map(c => (
              <MenuItem key={c} value={c}>
                {c}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            size="small"
            fullWidth
            label={t('agentMirrors.colUrl', 'Mirror URL')}
            placeholder="https://mirror.internal/sysmanage/apt"
            value={url}
            onChange={e => setUrl(e.target.value)}
          />
          <Button
            variant="contained"
            onClick={() => void save()}
            disabled={saving || !channel || !url}
          >
            {t('agentMirrors.add', 'Add')}
          </Button>
        </Stack>

        {channels.length === 0 && !loading && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t(
              'agentMirrors.noEngine',
              'The provisioning engine is not licensed on this server, so there are no channels to configure.',
            )}
          </Typography>
        )}

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          // autoHeight is deprecated in MUI DataGrid; the rest of the codebase
          // sizes grids with a Box wrapper (PackageProfilesSettings, HostCompliancePanel).
          <Box sx={{ height: 400 }}>
            <DataGrid
              rows={mirrors}
              columns={columns}
              getRowId={row => row.id}
              hideFooter={mirrors.length <= 10}
              disableRowSelectionOnClick
            />
          </Box>
        )}
      </CardContent>

      <Snackbar
        open={!!toast}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        message={toast ?? ''}
      />
    </Card>
  );
};

export default AgentMirrorsSettings;
