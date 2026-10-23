// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Recent backup jobs (Phase 24): captures, the storage side's seals, prunes,
// checks and size measurements, and restores -- newest first, a page at a
// time.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    Chip,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TablePagination,
    TableRow,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { getRuns } from '../../Services/backups';
import type { BackupRun } from '../../Services/backups';
import { useVisiblePolling } from '../../hooks/useVisiblePolling';
import { actionLabel, formatTime, pausedServicesOf, runStatusColor, runStatusLabel } from './backupLabels';

const runDetail = (run: BackupRun): string => {
    if (run.snapshot) return run.snapshot;
    return run.message ?? '';
};

// Each service restate paused for this capture, how long, and how it ended:
// a failed pause or resume is why a run is Incomplete.
const PausedServices: React.FC<{ run: BackupRun }> = ({ run }) => {
    const { t } = useTranslation();
    return (
        <>
            {pausedServicesOf(run).map(paused => (
                <Typography key={paused.service} variant="caption" display="block"
                    color={paused.ok ? 'text.secondary' : 'warning.main'}>
                    {paused.ok
                        ? t('backups.runs.paused', 'Paused {{service}} for {{seconds}} s', {
                            service: paused.service, seconds: paused.seconds ?? '?' })
                        : t('backups.runs.pauseFailed', 'Could not pause or resume {{service}}: {{message}}', {
                            service: paused.service, message: paused.message })}
                </Typography>
            ))}
        </>
    );
};

const BackupRunsList: React.FC<{
    hostId?: string;
    hostNames?: Record<string, string>;
    refreshKey?: number;
}> = ({ hostId, hostNames = {}, refreshKey = 0 }) => {
    const { t } = useTranslation();
    const [runs, setRuns] = useState<BackupRun[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(0);
    const [perPage, setPerPage] = useState(25);
    const [error, setError] = useState(false);

    const load = useCallback(async () => {
        try {
            const data = await getRuns({ host_id: hostId, limit: perPage, offset: page * perPage });
            setRuns(data.runs);
            setTotal(data.total);
            setError(false);
        } catch {
            setError(true);
        }
    }, [hostId, page, perPage]);

    useEffect(() => {
        void load();
    }, [load, refreshKey]);
    useVisiblePolling(load, 15000, true);

    if (error) {
        return <Alert severity="error">{t('backups.runs.loadError', 'Could not load the backup jobs.')}</Alert>;
    }
    if (runs.length === 0) {
        return <Typography variant="body2" color="text.secondary">{t('backups.runs.empty', 'No backup jobs yet.')}</Typography>;
    }
    return (
        <>
            <Table size="small">
                <TableHead>
                    <TableRow>
                        <TableCell>{t('backups.runs.queued', 'Queued at')}</TableCell>
                        {!hostId && <TableCell>{t('backups.runs.host', 'Runs on')}</TableCell>}
                        <TableCell>{t('backups.runs.action', 'Job')}</TableCell>
                        <TableCell>{t('backups.runs.status', 'Status')}</TableCell>
                        <TableCell>{t('backups.runs.detail', 'Detail')}</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {runs.map(run => (
                        <TableRow key={run.id}>
                            <TableCell>{formatTime(run.queued_at)}</TableCell>
                            {!hostId && <TableCell>{hostNames[run.host_id] ?? run.host_id}</TableCell>}
                            <TableCell>{actionLabel(t, run.action)}</TableCell>
                            <TableCell>
                                <Chip size="small" color={runStatusColor(run.status)} label={runStatusLabel(t, run)} />
                            </TableCell>
                            <TableCell sx={{ wordBreak: 'break-all' }}>{runDetail(run)}<PausedServices run={run} /></TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
            <TablePagination
                component="div"
                count={total}
                page={page}
                rowsPerPage={perPage}
                rowsPerPageOptions={[25, 50, 100]}
                onPageChange={(_e, p) => setPage(p)}
                onRowsPerPageChange={e => {
                    setPerPage(Number(e.target.value));
                    setPage(0);
                }}
                labelRowsPerPage={t('common.rowsPerPage', 'Rows per page')}
            />
        </>
    );
};

export default BackupRunsList;
