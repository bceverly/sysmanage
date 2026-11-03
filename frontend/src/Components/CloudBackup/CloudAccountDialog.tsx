// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Add or change an iCloud account (ROADMAP 24.12).  The password goes to the
// server once, which keeps it in OpenBAO; the form never shows it again.
// Deleting photos from iCloud after download is off unless it is asked for,
// with a warning and an explicit confirmation.

import React, { useEffect, useState } from 'react';
import {
    Alert, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle,
    FormControlLabel, MenuItem, Stack, Switch, TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { createCloudAccount, updateCloudAccount } from '../../Services/cloudBackup';
import type { CloudAccount } from '../../Services/cloudBackup';
import { apiDetail } from '../Backups/backupLabels';

interface Props {
    open: boolean;
    account: CloudAccount | null;
    storageHost: string;
    onClose: () => void;
    onSaved: () => void;
}

const numberOr = (text: string, fallback: number): number => {
    const value = Number.parseInt(text, 10);
    return Number.isFinite(value) ? value : fallback;
};

const CloudAccountDialog: React.FC<Props> = ({ open, account, storageHost, onClose, onSaved }) => {
    const { t } = useTranslation();
    const [appleId, setAppleId] = useState('');
    const [name, setName] = useState('');
    const [password, setPassword] = useState('');
    const [library, setLibrary] = useState('PrimarySync');
    const [enabled, setEnabled] = useState(true);
    const [intervalHours, setIntervalHours] = useState('24');
    const [windowStart, setWindowStart] = useState('');
    const [untilFound, setUntilFound] = useState('50');
    const [autoDelete, setAutoDelete] = useState(false);
    const [acknowledged, setAcknowledged] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        if (!open) return;
        setAppleId(account?.apple_id ?? '');
        setName(account?.display_name ?? '');
        setPassword('');
        setLibrary(account?.library ?? 'PrimarySync');
        setEnabled(account?.enabled ?? true);
        setIntervalHours(String(account?.interval_hours ?? 24));
        setWindowStart(account?.window_start_hour == null ? '' : String(account.window_start_hour));
        setUntilFound(String(account?.until_found ?? 50));
        setAutoDelete(account?.auto_delete ?? false);
        setAcknowledged(account?.auto_delete ?? false);
        setError('');
    }, [open, account]);

    const libraries = account?.libraries?.length ? account.libraries : [];
    const save = async () => {
        setBusy(true);
        setError('');
        const settings = {
            display_name: name.trim(),
            library,
            enabled,
            interval_hours: numberOr(intervalHours, 24),
            window_start_hour: windowStart === '' ? null : numberOr(windowStart, 0),
            until_found: numberOr(untilFound, 50),
            auto_delete: autoDelete,
            acknowledge_auto_delete: autoDelete && acknowledged,
        };
        try {
            if (account) {
                await updateCloudAccount(account.id, password ? { ...settings, password } : settings);
            } else {
                await createCloudAccount({ ...settings, apple_id: appleId.trim(), password });
            }
            setPassword('');
            onSaved();
        } catch (err) {
            setError(apiDetail(err, t('cloudBackup.account.saveFailed', 'The account could not be saved.')));
        } finally {
            setBusy(false);
        }
    };

    const ready = name.trim() !== '' && (account !== null || (appleId.trim() !== '' && password !== ''))
        && (!autoDelete || acknowledged);

    return (
        <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth>
            <DialogTitle>
                {account
                    ? t('cloudBackup.account.editTitle', 'Change iCloud account')
                    : t('cloudBackup.account.addTitle', 'Add an iCloud account')}
            </DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    <Alert severity="info">
                        {t('cloudBackup.account.where',
                            'Photos are downloaded by your backup storage host, {{host}}, into the backup storage. Nothing is installed on any other host.',
                            { host: storageHost })}
                    </Alert>
                    <TextField label={t('cloudBackup.account.appleId', 'Apple ID (e-mail address)')} value={appleId}
                        onChange={e => setAppleId(e.target.value)} disabled={account !== null} required
                        autoComplete="off" inputProps={{ 'data-testid': 'cloud-apple-id' }} />
                    <TextField label={t('cloudBackup.account.displayName', 'Name shown in SysManage')} value={name}
                        onChange={e => setName(e.target.value)} required inputProps={{ 'data-testid': 'cloud-name' }} />
                    <TextField type="password" label={account
                        ? t('cloudBackup.account.newPassword', 'New Apple ID password (leave empty to keep the current one)')
                        : t('cloudBackup.account.password', 'Apple ID password')}
                        value={password} onChange={e => setPassword(e.target.value)} required={account === null}
                        autoComplete="new-password"
                        helperText={t('cloudBackup.account.passwordHelp',
                            'Kept in OpenBAO, never in the database. It is handed to the storage host for one job at a time and never shown again.')}
                        inputProps={{ 'data-testid': 'cloud-password' }} />
                    {libraries.length > 0 ? (
                        <TextField select label={t('cloudBackup.account.library', 'Library')} value={library}
                            onChange={e => setLibrary(e.target.value)}>
                            {libraries.map(lib => <MenuItem key={lib} value={lib}>{lib}</MenuItem>)}
                        </TextField>
                    ) : (
                        <TextField label={t('cloudBackup.account.library', 'Library')} value={library}
                            onChange={e => setLibrary(e.target.value)}
                            helperText={t('cloudBackup.account.libraryHelp',
                                'PrimarySync is the personal library. After the first sign-in, List libraries shows the shared ones.')} />
                    )}
                    <Stack direction="row" spacing={2}>
                        <TextField type="number" label={t('cloudBackup.account.interval', 'Every (hours)')} value={intervalHours}
                            onChange={e => setIntervalHours(e.target.value)} inputProps={{ min: 1, max: 720 }} fullWidth />
                        <TextField type="number" label={t('cloudBackup.account.windowStart', 'Window start (UTC hour, optional)')}
                            value={windowStart} onChange={e => setWindowStart(e.target.value)}
                            inputProps={{ min: 0, max: 23 }} fullWidth />
                    </Stack>
                    <TextField type="number" label={t('cloudBackup.account.untilFound', 'Stop an incremental download after this many photos already present')}
                        value={untilFound} onChange={e => setUntilFound(e.target.value)} inputProps={{ min: 1, max: 10000 }}
                        helperText={t('cloudBackup.account.untilFoundHelp',
                            'Once a week a full pass checks the whole library whatever this says.')} />
                    <FormControlLabel control={<Switch checked={enabled} onChange={e => setEnabled(e.target.checked)} />}
                        label={t('cloudBackup.account.enabled', 'Download on schedule')} />
                    <FormControlLabel control={<Checkbox checked={autoDelete} onChange={e => setAutoDelete(e.target.checked)} />}
                        label={t('cloudBackup.account.autoDelete', 'Delete photos from iCloud after they are downloaded')} />
                    {autoDelete && (
                        <Alert severity="warning">
                            {t('cloudBackup.account.autoDeleteWarning',
                                'Photos will be removed from iCloud, and from every device signed in to this Apple ID, once they are on the backup storage. The backup storage then holds the only copy. Leave this off unless that is what you want.')}
                            <FormControlLabel sx={{ display: 'block', mt: 1 }}
                                control={<Checkbox checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} />}
                                label={t('cloudBackup.account.autoDeleteConfirm', 'I understand: delete photos from iCloud after download')} />
                        </Alert>
                    )}
                    {error && <Alert severity="error">{error}</Alert>}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={busy}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" onClick={() => void save()} disabled={busy || !ready}>
                    {t('common.save', 'Save')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default CloudAccountDialog;
