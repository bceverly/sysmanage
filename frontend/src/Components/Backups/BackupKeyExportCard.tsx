// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Break-glass key export without the Pro+ engine (2026-11-03): "please don't
// hold someone's safety hostage".  When encrypted backups exist and the Pro+
// Encryption panel is not loaded (a lapsed license), this card still lets an
// operator take the keys out, sealed to their own OpenPGP public key -- the
// same file the Pro+ panel makes.  Making, rotating and turning on
// encryption stay Pro+.

import React, { useEffect, useState } from 'react';
import {
    Alert, Button, Card, CardContent, Dialog, DialogActions, DialogContent,
    DialogTitle, Stack, TextField, Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useModuleLicensed } from '../../hooks/useModuleLicensed';
import { exportBreakGlass, getBreakGlassInfo, BreakGlassInfo } from '../../Services/backups';
import { apiDetail } from './backupLabels';

const saveBlob = (blob: Blob, name: string): void => {
    const url = globalThis.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    globalThis.URL.revokeObjectURL(url);
};

const BackupKeyExportCard: React.FC<{ refreshKey?: number }> = ({ refreshKey }) => {
    const { t } = useTranslation();
    const licensed = useModuleLicensed('backup_engine');
    const [info, setInfo] = useState<BreakGlassInfo | null>(null);
    const [open, setOpen] = useState(false);
    const [reason, setReason] = useState('');
    const [key, setKey] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        let live = true;
        if (!licensed) {
            getBreakGlassInfo().then(found => { if (live) setInfo(found); }).catch(() => undefined);
        }
        return () => { live = false; };
    }, [licensed, refreshKey]);

    // Licensed: the Pro+ Encryption panel does this (and more).
    if (licensed || !info?.available) return null;

    const run = async () => {
        setBusy(true);
        setError('');
        try {
            const { blob, name } = await exportBreakGlass(reason, key);
            saveBlob(blob, name);
            setOpen(false);
            setReason('');
            setKey('');
        } catch (err) {
            setError(apiDetail(err, t('backups.breakGlass.failed', 'The keys could not be exported.')));
        } finally {
            setBusy(false);
        }
    };

    return (
        <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
                <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between">
                    <Typography variant="body2">
                        {t('backups.breakGlass.community',
                            '{{count}} host(s) have encrypted backups. Without the Professional+ license they keep backing up encrypted and can still be restored, and you can export their keys here, sealed to your own OpenPGP public key, for a restore with the SysManage server down.',
                            { count: info.encrypted_hosts })}
                    </Typography>
                    <Button variant="outlined" onClick={() => setOpen(true)}>
                        {t('backups.breakGlass.button', 'Break-glass key export')}
                    </Button>
                </Stack>
            </CardContent>
            <Dialog open={open} onClose={() => setOpen(false)} maxWidth="md" fullWidth>
                <DialogTitle>{t('backups.breakGlass.title', 'Break-glass key export')}</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        {error && <Alert severity="error">{error}</Alert>}
                        <Alert severity="warning">
                            {t('backups.breakGlass.warning',
                                'The file holds the SECRET keys of every encrypted backup. Keep it offline, away from the backups and the server, and destroy it when a newer export replaces it.')}
                        </Alert>
                        <TextField multiline minRows={6} value={key} onChange={e => setKey(e.target.value)}
                            label={t('backups.breakGlass.key', 'Your OpenPGP PUBLIC key (armored)')}
                            helperText={info.escrow_key_fingerprint
                                ? t('backups.breakGlass.saved', 'Leave empty to use the saved escrow key {{fingerprint}}.',
                                    { fingerprint: info.escrow_key_fingerprint })
                                : 'gpg --armor --export you@example.com'} />
                        <TextField value={reason} onChange={e => setReason(e.target.value)}
                            label={t('backups.breakGlass.reason', 'Why (goes in the audit log and the README)')} />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
                    <Button variant="contained" disabled={busy || reason.trim().length < 10
                        || (!key.trim() && !info.escrow_key_fingerprint)} onClick={() => void run()}>
                        {t('backups.breakGlass.download', 'Export and download')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Card>
    );
};

export default BackupKeyExportCard;
