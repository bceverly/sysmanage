// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Back up this SysManage server (ROADMAP 25.9): pick the server's host (the
// one named as this machine is, when found), see what its policy keeps,
// leaves out and never backs up, and set when it runs.  Saved as that host's
// own policy, marked as the server's.

import React, { useEffect, useState } from 'react';
import {
    Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import {
    getServerBackup, saveServerPolicy, type ServerBackupEncryption, type ServerBackupPreset,
} from '../../Services/backups';
import { apiDetail } from './backupLabels';
import { DEFAULTS, GFS_DEFAULTS } from './BackupPolicyDialog';
import { useModuleLicensed } from '../../hooks/useModuleLicensed';

const PathList: React.FC<{ title: string; paths: string[]; help?: string }> = ({ title, paths, help }) => (
    <Box>
        <Typography variant="subtitle2">{title}</Typography>
        {help && <Typography variant="body2" color="text.secondary">{help}</Typography>}
        <Box component="ul" sx={{ m: 0, pl: 3, fontFamily: 'monospace', fontSize: '0.85rem', overflowWrap: 'anywhere' }}>
            {paths.map(path => <li key={path}>{path}</li>)}
        </Box>
    </Box>
);

const BackupServerDialog: React.FC<{
    open: boolean;
    hostId: string | null;
    hosts: { host_id: string; fqdn: string }[];
    onClose: () => void;
    onSaved: () => void;
}> = ({ open, hostId, hosts, onClose, onSaved }) => {
    const { t } = useTranslation();
    const gfsLicensed = useModuleLicensed('backup_engine');
    const [chosen, setChosen] = useState('');
    const [preset, setPreset] = useState<ServerBackupPreset | null>(null);
    const [encryption, setEncryption] = useState<ServerBackupEncryption | null>(null);
    const [every, setEvery] = useState(24);
    const [windowStart, setWindowStart] = useState<number | null>(null);
    const [keepLast, setKeepLast] = useState(DEFAULTS.keep_last);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (open) {
            setChosen(hostId ?? '');
            setEvery(24);
            setWindowStart(null);
            setKeepLast(gfsLicensed ? GFS_DEFAULTS.keep_last ?? DEFAULTS.keep_last : DEFAULTS.keep_last);
            setError(null);
        }
    }, [open, hostId, gfsLicensed]);

    useEffect(() => {
        if (!open || !chosen) {
            setPreset(null);
            return undefined;
        }
        let live = true;
        getServerBackup(chosen)
            .then(found => {
                if (live) {
                    setPreset(found.preset);
                    setEncryption(found.encryption ?? null);
                }
            })
            .catch(() => { if (live) setPreset(null); });
        return () => { live = false; };
    }, [open, chosen]);

    // Pro+ never backs the server up unencrypted, nor to a key in its own OpenBAO.
    const needsEscrow = Boolean(encryption?.available && !encryption.escrow_fingerprint);

    const save = async () => {
        if (!chosen || !preset || needsEscrow) return;
        try {
            await saveServerPolicy(chosen, {
                ...DEFAULTS,
                ...(gfsLicensed ? GFS_DEFAULTS : {}),
                interval_hours: every,
                window_start_hour: windowStart,
                keep_last: keepLast,
                quiesce: true,
                keep_paths: preset.keep_paths,
                skip_paths: preset.skip_paths,
            });
            onSaved();
            onClose();
        } catch (err) {
            setError(apiDetail(err, t('backups.server.saveError', 'The SysManage server backup could not be saved.')));
        }
    };

    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>{t('backups.server.title', 'Back up this SysManage server')}</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    {error && <Alert severity="error">{error}</Alert>}
                    <TextField select label={t('backups.server.host', 'The host this SysManage server runs on')}
                        value={chosen} onChange={e => setChosen(e.target.value)}
                        helperText={hostId ? undefined
                            : t('backups.server.hostHelp', 'No host is named as this server is. Pick the one its agent runs on.')}>
                        {hosts.map(h => <MenuItem key={h.host_id} value={h.host_id}>{h.fqdn}</MenuItem>)}
                    </TextField>
                    {preset && (
                        <>
                            <PathList title={t('backups.server.kept', 'Backed up')} paths={preset.keep_paths}
                                help={t('backups.server.keptHelp',
                                    "The agents' certificate authority and the server identity (lose them and every agent must enroll again), OpenBAO, PostgreSQL, the configuration, the TLS certificates and the license, with the rest of the host.")} />
                            <PathList title={t('backups.server.skipped', 'Left out')} paths={preset.skip_paths}
                                help={t('backups.server.skippedHelp', 'Downloaded again when needed: engine bundles, the GeoIP database, package mirrors and logs.')} />
                            <PathList title={t('backups.server.never', 'Never backed up')} paths={preset.never_paths}
                                help={t('backups.server.neverHelp',
                                    "These hold OpenBAO's unseal or recovery key and the server's OpenBAO token. Keep a copy of them somewhere safe away from the server, such as a password manager, so a stolen backup cannot unseal the OpenBAO copy inside it.")} />
                        </>
                    )}
                    <Alert severity="info">
                        {t('backups.server.pauseNote',
                            'PostgreSQL is stopped while its own files are copied, so SysManage may show errors for that time. Pick a quiet start hour.')}
                    </Alert>
                    {encryption?.available ? (
                        needsEscrow ? (
                            <Alert severity="error">
                                {t('backups.server.needsEscrow',
                                    "Save a break-glass escrow key first, in a host's Encryption panel. The SysManage server's own backup is encrypted to it, so restoring OpenBAO never needs a key kept inside OpenBAO.")}
                            </Alert>
                        ) : (
                            <Alert severity="success">
                                {t('backups.server.escrowEncrypted',
                                    'Encrypted to your break-glass escrow key ({{fingerprint}}). SysManage never holds its secret half, so this backup is restored by hand with that key, as the server recovery runbook describes.',
                                    { fingerprint: encryption.escrow_fingerprint })}
                            </Alert>
                        )
                    ) : (
                        <Alert severity="warning">
                            {t('backups.server.unencrypted',
                                'This backup is not encrypted, and it holds the database password from the configuration. Keep the backup storage as safe as the server itself.')}
                        </Alert>
                    )}
                    <TextField type="number" label={t('backups.policy.intervalHours', 'Every (hours)')}
                        value={every} slotProps={{ htmlInput: { min: 1, max: 720 } }}
                        onChange={e => setEvery(Number(e.target.value) || 0)} />
                    <TextField type="number" label={t('backups.policy.windowStart', 'Start hour (UTC, optional)')}
                        value={windowStart ?? ''} slotProps={{ htmlInput: { min: 0, max: 23 } }}
                        onChange={e => setWindowStart(e.target.value === '' ? null : Number(e.target.value))} />
                    <TextField type="number" label={t('backups.policy.keepLast', 'Snapshots to keep')}
                        value={keepLast} slotProps={{ htmlInput: { min: 1, max: 1000 } }}
                        onChange={e => setKeepLast(Number(e.target.value) || 0)} />
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <AsyncButton variant="contained" onClick={save} disabled={!chosen || !preset || needsEscrow}>
                    {t('common.save', 'Save')}
                </AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

export default BackupServerDialog;
