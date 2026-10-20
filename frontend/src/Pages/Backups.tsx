// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Backups (Phase 24, Community): the target, every host's backup standing
// with Back up now and Restore files, and the recent jobs.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Box, Chip, CircularProgress, Paper, Snackbar, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { BACKUP_STATUS_ORDER, getBackupOverview } from '../Services/backups';
import type { BackupOverview } from '../Services/backups';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import BackupTargetCard from '../Components/Backups/BackupTargetCard';
import BackupHostsTable from '../Components/Backups/BackupHostsTable';
import BackupRunsList from '../Components/Backups/BackupRunsList';
import { statusColor, statusLabel } from '../Components/Backups/backupLabels';
import { useVisiblePolling } from '../hooks/useVisiblePolling';

const Backups: React.FC = () => {
    const { t } = useTranslation();
    const [data, setData] = useState<BackupOverview | null>(null);
    const [error, setError] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const [canManage, setCanManage] = useState(false);
    const [canRestore, setCanRestore] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);

    const load = useCallback(async () => {
        try {
            setData(await getBackupOverview());
            setError(false);
        } catch {
            setError(true);
        }
    }, []);

    useEffect(() => {
        void load();
        Promise.all([hasPermission(SecurityRoles.MANAGE_BACKUPS), hasPermission(SecurityRoles.RESTORE_FILES)])
            .then(([manage, restore]) => {
                setCanManage(manage);
                setCanRestore(restore);
            })
            .catch(() => undefined);
    }, [load]);
    useVisiblePolling(load, 15000, true);

    const changed = useCallback(() => {
        void load();
        setRefreshKey(k => k + 1);
    }, [load]);
    const hostNames = useMemo(
        () => Object.fromEntries((data?.hosts ?? []).map(h => [h.host_id, h.fqdn])),
        [data],
    );

    if (!data) {
        return error ? (
            <Alert severity="error">{t('backups.loadError', 'Could not load the backups.')}</Alert>
        ) : (
            <Box display="flex" justifyContent="center" sx={{ mt: 4 }}><CircularProgress /></Box>
        );
    }

    return (
        <Box>
            <Typography variant="h5" sx={{ mb: 2 }}>{t('backups.title', 'Backups')}</Typography>
            <BackupTargetCard target={data.target} hosts={data.hosts} versions={data.restate_versions}
                canManage={canManage} onChanged={changed} />
            <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', rowGap: 1 }}>
                {BACKUP_STATUS_ORDER.filter(s => data.counts[s]).map(s => (
                    <Chip key={s} variant="outlined" color={statusColor(s)}
                        label={`${statusLabel(t, s)}: ${data.counts[s]}`} />
                ))}
            </Stack>
            <Paper variant="outlined" sx={{ p: 2, mb: 3, overflowX: 'auto' }}>
                {data.hosts.length === 0 ? (
                    <Alert severity="info">{t('backups.empty', 'There are no approved hosts yet.')}</Alert>
                ) : (
                    <BackupHostsTable rows={data.hosts} hasTarget={data.target !== null} canManage={canManage}
                        canRestore={canRestore} onChanged={changed} onError={setMessage} />
                )}
            </Paper>
            <Paper variant="outlined" sx={{ p: 2, overflowX: 'auto' }}>
                <Typography variant="h6" sx={{ mb: 1 }}>{t('backups.runs.title', 'Recent jobs')}</Typography>
                <BackupRunsList hostNames={hostNames} refreshKey={refreshKey} />
            </Paper>
            <Snackbar open={message !== null} autoHideDuration={6000} onClose={() => setMessage(null)}>
                <Alert severity="error" onClose={() => setMessage(null)}>{message}</Alert>
            </Snackbar>
        </Box>
    );
};

export default Backups;
