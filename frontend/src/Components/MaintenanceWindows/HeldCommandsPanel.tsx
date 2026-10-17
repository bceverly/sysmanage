// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';

import { HeldCommand, maintenanceWindowsService } from '../../Services/maintenanceWindows';
import { formatUTCTimestamp } from '../../utils/dateUtils';
import EmergencyOverrideDialog from '../EmergencyOverrideDialog';
import { heldCommandText, releaseText } from './heldCommandText';

const PAGE_SIZE = 25;

const refusal = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

/**
 * Every command a maintenance window is holding in this tenant: what it is,
 * when it was queued and which window releases it -- with "release now"
 * (the emergency override for that host) and "cancel" for one command.
 */
const HeldCommandsPanel: React.FC = () => {
    const { t } = useTranslation();
    const [items, setItems] = useState<HeldCommand[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [releaseHost, setReleaseHost] = useState<string | null>(null);
    const [cancelItem, setCancelItem] = useState<HeldCommand | null>(null);

    const load = useCallback(async () => {
        try {
            const out = await maintenanceWindowsService.listHeld(PAGE_SIZE, page * PAGE_SIZE);
            setItems(out.items);
            setTotal(out.total);
        } catch (err) {
            setError(refusal(err, t('maintenanceWindows.held.loadFailed', 'The held commands could not be loaded.')));
        }
    }, [page, t]);

    useEffect(() => { void load(); }, [load]);

    const confirmCancel = async () => {
        if (!cancelItem) return;
        try {
            await maintenanceWindowsService.cancelHeld(cancelItem.id);
            setCancelItem(null);
            void load();
        } catch (err) {
            setCancelItem(null);
            setError(refusal(err, t('maintenanceWindows.held.cancelFailed', 'The command could not be canceled.')));
        }
    };

    return (
        <Box sx={{ mt: 3 }} data-testid="held-commands-panel">
            <Typography variant="h6">{t('maintenanceWindows.held.title', 'Held commands')}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {t('maintenanceWindows.held.intro',
                    'Commands waiting for a maintenance window. They run when the window opens, or now if you release the host.')}
            </Typography>
            {error && <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>{error}</Alert>}
            {total === 0 ? (
                <Typography variant="body2">{t('maintenanceWindows.held.none', 'No commands are waiting for a window.')}</Typography>
            ) : (
                <TableContainer component={Paper}>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>{t('maintenanceWindows.held.col.host', 'Host')}</TableCell>
                                <TableCell>{t('maintenanceWindows.held.col.command', 'Command')}</TableCell>
                                <TableCell>{t('maintenanceWindows.held.col.queued', 'Waiting since')}</TableCell>
                                <TableCell>{t('maintenanceWindows.held.col.runs', 'Will run')}</TableCell>
                                <TableCell>{t('maintenanceWindows.held.col.expires', 'Expires')}</TableCell>
                                <TableCell align="right">{t('maintenanceWindows.held.col.actions', 'Actions')}</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {items.map((item) => (
                                <TableRow key={item.id}>
                                    <TableCell>
                                        {item.host_id ? (
                                            <Link component={RouterLink} to={`/hosts/${item.host_id}`}>{item.fqdn ?? item.host_id}</Link>
                                        ) : '-'}
                                    </TableCell>
                                    <TableCell>{heldCommandText(t, item)}</TableCell>
                                    <TableCell>{formatUTCTimestamp(item.queued_at ?? '')}</TableCell>
                                    <TableCell>{releaseText(t, item)}</TableCell>
                                    <TableCell>{formatUTCTimestamp(item.expires_at ?? '')}</TableCell>
                                    <TableCell align="right">
                                        {item.host_id && (
                                            <Button size="small" onClick={() => setReleaseHost(item.host_id)}>
                                                {t('maintenanceWindows.held.release', 'Release host now')}
                                            </Button>
                                        )}
                                        <Button size="small" color="error" onClick={() => setCancelItem(item)}>
                                            {t('maintenanceWindows.held.cancel', 'Cancel command')}
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                    <TablePagination
                        component="div"
                        count={total}
                        page={page}
                        rowsPerPage={PAGE_SIZE}
                        rowsPerPageOptions={[PAGE_SIZE]}
                        onPageChange={(_e, next) => setPage(next)}
                    />
                </TableContainer>
            )}
            {releaseHost && (
                <EmergencyOverrideDialog
                    hostId={releaseHost}
                    open
                    onClose={() => setReleaseHost(null)}
                    onDone={() => { void load(); }}
                />
            )}
            <Dialog open={cancelItem !== null} onClose={() => setCancelItem(null)}>
                <DialogTitle>{t('maintenanceWindows.held.cancelTitle', 'Cancel this command?')}</DialogTitle>
                <DialogContent>
                    <Typography variant="body2">
                        {cancelItem ? heldCommandText(t, cancelItem) : ''}
                        {cancelItem?.fqdn ? ` -- ${cancelItem.fqdn}` : ''}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        {t('maintenanceWindows.held.cancelExplain', 'It will not run. This is audited.')}
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setCancelItem(null)}>{t('maintenanceWindows.held.keep', 'Keep it')}</Button>
                    <Button color="error" variant="contained" onClick={() => { void confirmCancel(); }}>
                        {t('maintenanceWindows.held.cancel', 'Cancel command')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default HeldCommandsPanel;
