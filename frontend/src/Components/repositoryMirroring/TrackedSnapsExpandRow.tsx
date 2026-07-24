// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import {
  listTrackedSnaps,
  trackSnap,
  untrackSnap,
  MirrorRepository,
  MirrorSnapContent,
  SnapCaptureStatus,
} from '../../Services/repositoryMirroring';

// ---------------------------------------------------------------------
// Tracked-snaps expand row (Phase 17.1 — snap store proxy)
//
// One inline collapsible per mirror listing the snaps tracked for capture
// (name + channel + capture status), with a small "track snap" form and an
// untrack action per row.  Loads lazily on expand and re-polls every 10s so a
// DISPATCHED -> CAPTURED transition (after "Capture snaps") appears without a
// manual refresh.  Modeled on SnapshotsExpandRow.
// ---------------------------------------------------------------------

const STATUS_COLOR: Record<
  SnapCaptureStatus,
  'default' | 'info' | 'success' | 'error'
> = {
  TRACKED: 'default',
  DISPATCHED: 'info',
  CAPTURED: 'success',
  FAILED: 'error',
};

interface TrackedSnapsExpandRowProps {
  mirror: MirrorRepository;
  colSpan: number;
  expanded: boolean;
}

const TrackedSnapsExpandRow: React.FC<TrackedSnapsExpandRowProps> = ({
  mirror,
  colSpan,
  expanded,
}) => {
  const { t } = useTranslation();
  const [snaps, setSnaps] = useState<MirrorSnapContent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [channel, setChannel] = useState('latest/stable');
  const [busy, setBusy] = useState(false);

  const fetchSnaps = React.useCallback(async () => {
    try {
      setSnaps(await listTrackedSnaps(mirror.id));
      setError(null);
    } catch {
      setError(t('mirror.snap.loadError', 'Could not load tracked snaps.'));
    }
  }, [mirror.id, t]);

  useEffect(() => {
    if (!expanded) return undefined;
    fetchSnaps();
    const handle = setInterval(fetchSnaps, 10_000);
    return () => clearInterval(handle);
  }, [expanded, fetchSnaps]);

  const add = async () => {
    const snapName = name.trim();
    if (!snapName) return;
    setBusy(true);
    try {
      await trackSnap(mirror.id, {
        snap_name: snapName,
        channel: channel.trim() || 'latest/stable',
      });
      setName('');
      await fetchSnaps();
    } catch {
      setError(
        t(
          'mirror.snap.trackError',
          'Could not track that snap. Names are lowercase letters, digits, and hyphens.',
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async (snap: MirrorSnapContent) => {
    try {
      await untrackSnap(mirror.id, snap.id);
      await fetchSnaps();
    } catch {
      setError(t('mirror.snap.untrackError', 'Could not untrack that snap.'));
    }
  };

  return (
    <TableRow>
      <TableCell
        colSpan={colSpan}
        sx={{ py: 0, borderBottom: expanded ? undefined : 'none' }}
      >
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          <Box sx={{ py: 1, pl: 4, pr: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {t('mirror.snap.title', 'Tracked snaps for {{name}}', {
                name: mirror.name,
              })}
            </Typography>
            {error && (
              <Alert severity="error" sx={{ mb: 1 }}>
                {error}
              </Alert>
            )}
            <Stack
              direction="row"
              spacing={1}
              sx={{ mb: 1 }}
              alignItems="center"
            >
              <TextField
                size="small"
                label={t('mirror.snap.name', 'Snap name')}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="hello"
              />
              <TextField
                size="small"
                label={t('mirror.snap.channel', 'Channel')}
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                placeholder="latest/stable"
              />
              <Button
                size="small"
                variant="outlined"
                startIcon={<AddIcon />}
                disabled={busy || !name.trim()}
                onClick={add}
              >
                {t('mirror.snap.track', 'Track')}
              </Button>
            </Stack>
            {snaps?.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                {t(
                  'mirror.snap.empty',
                  'No snaps tracked yet. Add one above, then use "Capture snaps".',
                )}
              </Typography>
            )}
            {snaps && snaps.length > 0 && (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('mirror.snap.col.name', 'Snap')}</TableCell>
                    <TableCell>
                      {t('mirror.snap.col.channel', 'Channel')}
                    </TableCell>
                    <TableCell>
                      {t('mirror.snap.col.status', 'Capture')}
                    </TableCell>
                    <TableCell align="right">
                      {t('mirror.snap.col.actions', 'Actions')}
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {snaps.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell sx={{ fontFamily: 'monospace' }}>
                        {s.snap_name}
                      </TableCell>
                      <TableCell>{s.channel}</TableCell>
                      <TableCell>
                        <Tooltip
                          title={s.error_message || ''}
                          arrow
                          disableHoverListener={!s.error_message}
                        >
                          <Chip
                            size="small"
                            label={s.capture_status}
                            color={STATUS_COLOR[s.capture_status]}
                          />
                        </Tooltip>
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip
                          title={t(
                            'mirror.snap.untrack',
                            'Stop tracking this snap',
                          )}
                          arrow
                        >
                          <IconButton size="small" onClick={() => remove(s)}>
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Box>
        </Collapse>
      </TableCell>
    </TableRow>
  );
};

export default TrackedSnapsExpandRow;
