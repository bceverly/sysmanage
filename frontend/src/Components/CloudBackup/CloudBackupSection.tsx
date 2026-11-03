// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Cloud backup on the Backups page (ROADMAP 24.12, Community): iCloud Photos
// downloaded to the backup storage by the target's storage host.  Enable it
// once, then add accounts, sign each in (Connect, then the two-factor code)
// and let the schedule run.  Hidden on an air-gapped server.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle,
    Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
    connectCloudAccount, deleteCloudAccount, getCloudOverview, listCloudLibraries, runCloudAccountNow,
} from '../../Services/cloudBackup';
import type { CloudAccount, CloudOverview } from '../../Services/cloudBackup';
import { hasPermission, SecurityRoles } from '../../Services/permissions';
import { useVisiblePolling } from '../../hooks/useVisiblePolling';
import { apiDetail, formatBytes, formatTime } from '../Backups/backupLabels';
import CloudAccountDialog from './CloudAccountDialog';
import CloudCodeDialog from './CloudCodeDialog';
import CloudEnablePanel from './CloudEnablePanel';
import { accountStatusColor, accountStatusLabel, actionLabel, reasonText } from './cloudBackupLabels';

const busyStatus = (account: CloudAccount): boolean =>
    account.status === 'running' || account.status === 'waiting_code';

const CloudBackupSection: React.FC<{ onError: (message: string) => void }> = ({ onError }) => {
    const { t } = useTranslation();
    const [data, setData] = useState<CloudOverview | null>(null);
    const [canManage, setCanManage] = useState(false);
    const [editing, setEditing] = useState<CloudAccount | null | undefined>(undefined);
    const [codeFor, setCodeFor] = useState<CloudAccount | null>(null);
    const [deleting, setDeleting] = useState<CloudAccount | null>(null);

    const load = useCallback(async () => {
        try {
            setData(await getCloudOverview());
        } catch {
            setData(null);
        }
    }, []);
    useEffect(() => {
        void load();
        hasPermission(SecurityRoles.MANAGE_CLOUD_BACKUPS).then(setCanManage).catch(() => undefined);
    }, [load]);
    const active = Boolean(data?.enable?.status === 'running' || data?.accounts.some(busyStatus));
    useVisiblePolling(load, active ? 4000 : 20000, true);

    if (!data?.available) return null;  // an air-gapped server: no internet, no iCloud

    const act = async (job: () => Promise<unknown>, failed: string) => {
        try {
            await job();
            await load();
        } catch (err) {
            onError(apiDetail(err, failed));
        }
    };
    const remove = async () => {
        if (!deleting) return;
        const account = deleting;
        setDeleting(null);
        await act(() => deleteCloudAccount(account.id), t('cloudBackup.account.deleteFailed', 'The account could not be deleted.'));
    };
    const host = data.storage_host?.fqdn ?? '';

    return (
        <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6">{t('cloudBackup.title', 'Cloud backup')}</Typography>
                {canManage && data.enabled && (
                    <Button variant="outlined" onClick={() => setEditing(null)} data-testid="cloud-add">
                        {t('cloudBackup.account.add', 'Add iCloud account')}
                    </Button>
                )}
            </Stack>
            {!data.target || !data.storage_host ? (
                <Alert severity="info">
                    {t('cloudBackup.noTarget', 'iCloud Photos are downloaded by the backup storage host. Set up the backup target with a storage host first.')}
                </Alert>
            ) : (
                <>
                    <CloudEnablePanel data={data} canManage={canManage} onChanged={() => void load()} />
                    {data.accounts.length > 0 && (
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    <TableCell>{t('cloudBackup.table.account', 'Account')}</TableCell>
                                    <TableCell>{t('cloudBackup.table.status', 'Status')}</TableCell>
                                    <TableCell>{t('cloudBackup.table.lastGood', 'Last download')}</TableCell>
                                    <TableCell>{t('cloudBackup.table.stored', 'Stored')}</TableCell>
                                    <TableCell>{t('cloudBackup.table.signIn', 'Sign-in ends')}</TableCell>
                                    <TableCell align="right">{t('cloudBackup.table.actions', 'Actions')}</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {data.accounts.map(account => (
                                    <CloudAccountRow key={account.id} account={account} canManage={canManage}
                                        onConnect={() => void act(() => connectCloudAccount(account.id),
                                            t('cloudBackup.account.connectFailed', 'The sign-in could not be started.'))}
                                        onRun={() => void act(() => runCloudAccountNow(account.id),
                                            t('cloudBackup.account.runFailed', 'The download could not be started.'))}
                                        onLibraries={() => void act(() => listCloudLibraries(account.id),
                                            t('cloudBackup.account.librariesFailed', 'The libraries could not be listed.'))}
                                        onCode={() => setCodeFor(account)} onEdit={() => setEditing(account)}
                                        onDelete={() => setDeleting(account)} />
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </>
            )}
            <CloudAccountDialog open={editing !== undefined} account={editing ?? null} storageHost={host}
                onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); void load(); }} />
            <CloudCodeDialog runId={codeFor?.current_run?.id ?? null} accountName={codeFor?.display_name ?? ''}
                onClose={() => setCodeFor(null)} onSent={() => { setCodeFor(null); void load(); }} />
            <Dialog open={deleting !== null} onClose={() => setDeleting(null)}>
                <DialogTitle>{t('cloudBackup.account.deleteTitle', 'Delete this iCloud account?')}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t('cloudBackup.account.deleteHelp',
                            'SysManage forgets the password and the sign-in for {{account}}. The photos already downloaded stay on the backup storage.',
                            { account: deleting?.display_name ?? '' })}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDeleting(null)}>{t('common.cancel', 'Cancel')}</Button>
                    <Button color="error" variant="contained" onClick={() => void remove()}>{t('common.delete', 'Delete')}</Button>
                </DialogActions>
            </Dialog>
        </Paper>
    );
};

interface RowProps {
    account: CloudAccount;
    canManage: boolean;
    onConnect: () => void;
    onRun: () => void;
    onLibraries: () => void;
    onCode: () => void;
    onEdit: () => void;
    onDelete: () => void;
}

const CloudAccountRow: React.FC<RowProps> = ({ account, canManage, onConnect, onRun, onLibraries, onCode, onEdit, onDelete }) => {
    const { t } = useTranslation();
    const run = account.current_run ?? account.last_run;
    const busy = busyStatus(account);
    const signedIn = account.session_created_at !== null;
    const problem = account.status === 'needs_sign_in' || account.status === 'failed';
    const progress = account.current_run?.progress;
    return (
        <TableRow>
            <TableCell>
                <Typography variant="body2">{account.display_name}</Typography>
                <Typography variant="caption" color="text.secondary">
                    {t('cloudBackup.table.identity', '{{appleId}}, library {{library}}', { appleId: account.apple_id, library: account.library })}
                </Typography>
                {account.auto_delete && (
                    <Typography variant="caption" color="warning.main" sx={{ display: 'block' }}>
                        {t('cloudBackup.table.autoDelete', 'Deletes from iCloud after download')}
                    </Typography>
                )}
            </TableCell>
            <TableCell>
                <Chip size="small" color={accountStatusColor(account.status)} label={accountStatusLabel(t, account.status)} />
                {busy && account.current_run && (
                    <Typography variant="caption" sx={{ display: 'block' }}>
                        {t('cloudBackup.table.progress', '{{action}}: {{n}} downloaded',
                            { action: actionLabel(t, account.current_run.action), n: progress?.downloaded ?? 0 })}
                    </Typography>
                )}
                {problem && (
                    <Typography variant="caption" color="error" sx={{ display: 'block', maxWidth: 360 }}>
                        {reasonText(t, run?.reason ?? null, account.state_message)}
                    </Typography>
                )}
                {!busy && run && run.status === 'ok' && run.action !== 'connect' && run.action !== 'libraries' && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        {t('cloudBackup.table.lastRun', 'Last run: {{downloaded}} new, {{present}} already present, {{failed}} failed',
                            { downloaded: run.downloaded ?? 0, present: run.present ?? 0, failed: run.failed ?? 0 })}
                    </Typography>
                )}
            </TableCell>
            <TableCell>{formatTime(account.last_good_at)}</TableCell>
            <TableCell>
                {account.photos_local == null ? '-' : t('cloudBackup.table.storedValue', '{{n}} items, {{size}}',
                    { n: account.photos_local, size: formatBytes(account.bytes_local) })}
            </TableCell>
            <TableCell>
                {signedIn ? formatTime(account.session_expires_at) : '-'}
                {account.session_expiring && account.status !== 'needs_sign_in' && (
                    <Typography variant="caption" color="warning.main" sx={{ display: 'block' }}>
                        {t('cloudBackup.table.expiring', 'Ends soon: press Connect')}
                    </Typography>
                )}
            </TableCell>
            <TableCell align="right">
                {canManage && (
                    <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ flexWrap: 'wrap', rowGap: 1 }}>
                        {account.status === 'waiting_code' && (
                            <Button size="small" variant="contained" onClick={onCode} data-testid="cloud-enter-code">
                                {t('cloudBackup.account.enterCode', 'Enter code')}
                            </Button>
                        )}
                        <Button size="small" variant={signedIn && !problem ? 'text' : 'contained'} disabled={busy} onClick={onConnect}>
                            {t('cloudBackup.account.connect', 'Connect')}
                        </Button>
                        <Button size="small" disabled={busy || !signedIn} onClick={onRun}>{t('cloudBackup.account.runNow', 'Run now')}</Button>
                        <Button size="small" disabled={busy || !signedIn} onClick={onLibraries}>
                            {t('cloudBackup.account.libraries', 'List libraries')}
                        </Button>
                        <Button size="small" onClick={onEdit}>{t('common.edit', 'Edit')}</Button>
                        <Button size="small" color="error" onClick={onDelete}>{t('common.delete', 'Delete')}</Button>
                    </Stack>
                )}
            </TableCell>
        </TableRow>
    );
};

export default CloudBackupSection;
