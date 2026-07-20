// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Collapse,
  CircularProgress,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import RestoreIcon from '@mui/icons-material/Restore';
import { useTranslation } from 'react-i18next';
import {
  listSnapshots,
  MirrorRepository,
  MirrorSnapshot,
  restoreMirror,
} from '../../Services/repositoryMirroring';
import { formatBytes } from './helpers';

// ---------------------------------------------------------------------
// Snapshot expand row
//
// One inline collapsible per mirror row showing the snapshots-list
// API result with a Restore icon-button per snapshot.  Loads lazily
// when expanded and re-polls every 10s while expanded so a fresh
// snapshot appears without a manual refresh.
// ---------------------------------------------------------------------

interface SnapshotsExpandRowProps {
  mirror: MirrorRepository;
  colSpan: number;
  expanded: boolean;
  onRestoreDispatched: () => void;
}

const SnapshotsExpandRow: React.FC<SnapshotsExpandRowProps> = ({
  mirror, colSpan, expanded, onRestoreDispatched,
}) => {
  const { t } = useTranslation();
  const [snapshots, setSnapshots] = useState<MirrorSnapshot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const fetchSnapshots = React.useCallback(async () => {
    try {
      const data = await listSnapshots(mirror.id);
      setSnapshots(data);
      setError(null);
    } catch {
      setError(t('mirror.snapshots.loadError', 'Could not load snapshots.'));
    }
  }, [mirror.id, t]);

  // Lazy-load on first expansion, then poll every 10s while expanded.
  // The polling also picks up size_bytes/file_count once a fresh
  // snapshot's result handler runs server-side.
  useEffect(() => {
    if (!expanded) return;
    fetchSnapshots();
    const handle = setInterval(fetchSnapshots, 10_000);
    return () => clearInterval(handle);
  }, [expanded, fetchSnapshots]);

  const handleRestore = async (snap: MirrorSnapshot) => {
    if (!globalThis.confirm(
      t(
        'mirror.snapshots.restoreConfirm',
        'Restore the mirror tree from snapshot {{id}}? The live tree will be overwritten.',
        { id: snap.snapshot_id },
      ),
    )) return;
    setRestoringId(snap.id);
    try {
      await restoreMirror(mirror.id, snap.snapshot_id);
      onRestoreDispatched();
    } catch {
      setError(t('mirror.snapshots.restoreError', 'Restore dispatch failed.'));
    } finally {
      setRestoringId(null);
    }
  };

  return (
    <TableRow>
      <TableCell colSpan={colSpan} sx={{ py: 0, borderBottom: expanded ? undefined : 'none' }}>
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          <Box sx={{ py: 1, pl: 4, pr: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {t('mirror.snapshots.title', 'Snapshots for {{name}}', { name: mirror.name })}
            </Typography>
            {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
            {snapshots?.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                {t('mirror.snapshots.empty', 'No snapshots yet. Click the camera icon to take one.')}
              </Typography>
            )}
            {snapshots && snapshots.length > 0 && (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('mirror.snapshots.col.id', 'Snapshot')}</TableCell>
                    <TableCell>{t('mirror.snapshots.col.taken', 'Taken at')}</TableCell>
                    <TableCell align="right">{t('mirror.snapshots.col.size', 'Size')}</TableCell>
                    <TableCell align="right">{t('mirror.snapshots.col.files', 'Files')}</TableCell>
                    <TableCell align="right">{t('mirror.snapshots.col.actions', 'Actions')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {snapshots.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{s.snapshot_id}</TableCell>
                      <TableCell>{s.taken_at ? new Date(s.taken_at).toLocaleString() : '—'}</TableCell>
                      <TableCell align="right">{formatBytes(s.size_bytes)}</TableCell>
                      <TableCell align="right">{s.file_count?.toLocaleString() ?? '—'}</TableCell>
                      <TableCell align="right">
                        <Tooltip
                          title={t(
                            'mirror.snapshots.restore',
                            'Restore live tree to this snapshot',
                          )}
                          arrow
                        >
                          <span>
                            <IconButton
                              size="small"
                              disabled={restoringId === s.id}
                              onClick={() => handleRestore(s)}
                            >
                              {restoringId === s.id ? (
                                <CircularProgress size={16} />
                              ) : (
                                <RestoreIcon fontSize="small" />
                              )}
                            </IconButton>
                          </span>
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

export default SnapshotsExpandRow;
