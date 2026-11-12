// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// How hosts reach the backup storage (ROADMAP 25.5): NFS, or restate-proxy on
// the storage host over HTTPS.  The repositories stay where they are, so the
// target switches either way.  Each host makes its own token for the proxy;
// the server only ever sees its hash.

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Button,
    Checkbox,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControl,
    FormControlLabel,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { setTransport } from '../../Services/backups';
import type { BackupTarget, TransportInput } from '../../Services/backups';
import { apiDetail } from './backupLabels';

const toInput = (target: BackupTarget): TransportInput => ({
    transport: target.transport?.transport ?? 'nfs',
    proxy_host: target.transport?.proxy_host ?? '',
    proxy_port: target.transport?.proxy_port ?? 8443,
    proxy_pin_sha256: target.transport?.proxy_pin_sha256 ?? '',
    proxy_ca_pem: '',
    remove_proxy_ca: false,
});

export const TransportDialog: React.FC<{
    open: boolean;
    target: BackupTarget;
    onClose: () => void;
    onSaved: () => void;
}> = ({ open, target, onClose, onSaved }) => {
    const { t } = useTranslation();
    const [form, setForm] = useState<TransportInput>(toInput(target));
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        if (open) {
            setForm(toInput(target));
            setError(null);
        }
    }, [open, target]);
    const set = (patch: Partial<TransportInput>) => setForm(f => ({ ...f, ...patch }));
    const proxy = form.transport === 'proxy';
    const savedCa = Boolean(target.transport?.proxy_ca);
    const save = async () => {
        setError(null);
        try {
            await setTransport(target.id, {
                transport: form.transport,
                proxy_host: proxy ? form.proxy_host : null,
                proxy_port: proxy ? form.proxy_port : null,
                proxy_pin_sha256: proxy ? form.proxy_pin_sha256 || null : null,
                proxy_ca_pem: proxy ? form.proxy_ca_pem || null : null,
                remove_proxy_ca: Boolean(form.remove_proxy_ca),
            });
            onSaved();
            onClose();
        } catch (err) {
            setError(apiDetail(err, t('backups.transport.saveError', 'How hosts reach the storage could not be saved.')));
        }
    };
    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>{t('backups.transport.title', 'How hosts reach the storage')}</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    {error && <Alert severity="error">{error}</Alert>}
                    <FormControl fullWidth>
                        <InputLabel id="backup-transport">{t('backups.transport.label', 'Reach the storage through')}</InputLabel>
                        <Select labelId="backup-transport" label={t('backups.transport.label', 'Reach the storage through')}
                            value={form.transport}
                            onChange={e => set({ transport: e.target.value as TransportInput['transport'] })}>
                            <MenuItem value="nfs">{t('backups.transport.nfs', 'NFS (each host mounts its own export)')}</MenuItem>
                            <MenuItem value="proxy">{t('backups.transport.proxy', 'restate-proxy (HTTPS to the storage host)')}</MenuItem>
                        </Select>
                    </FormControl>
                    {proxy && (
                        <>
                            <Typography variant="body2" color="text.secondary">
                                {t('backups.transport.proxyIntro',
                                    'Run restate-proxy on the storage host. Each host makes its own token for it, which never leaves the host, and the storage host writes the grants. Backups, restores, browsing and comparisons all go through the proxy, with no NFS mount, once a host\'s restate can capture through it.')}
                            </Typography>
                            <TextField label={t('backups.transport.host', 'Proxy address hosts reach')} value={form.proxy_host ?? ''}
                                onChange={e => set({ proxy_host: e.target.value })}
                                helperText={t('backups.transport.hostHelp',
                                    'The name or address in the proxy\'s certificate, as hosts resolve it.')} />
                            <TextField type="number" label={t('backups.transport.port', 'Port')} value={form.proxy_port ?? ''}
                                slotProps={{ htmlInput: { min: 1, max: 65535 } }}
                                onChange={e => set({ proxy_port: e.target.value === '' ? null : Number(e.target.value) })} />
                            <TextField label={t('backups.transport.pin', 'Pinned key (SHA-256, optional)')}
                                value={form.proxy_pin_sha256 ?? ''}
                                onChange={e => set({ proxy_pin_sha256: e.target.value.trim() })}
                                helperText={t('backups.transport.pinHelp',
                                    'Hosts then accept only a proxy certificate with this public key.')} />
                            <TextField label={t('backups.transport.ca', 'Site CA certificate (PEM, optional)')} multiline minRows={3}
                                value={form.proxy_ca_pem ?? ''}
                                onChange={e => set({ proxy_ca_pem: e.target.value })}
                                helperText={savedCa
                                    ? t('backups.transport.caKept', 'A CA is saved. Paste another to replace it; left empty, the saved one is kept.')
                                    : t('backups.transport.caHelp', 'For a proxy certificate your own CA signed. Hosts trust it for their backups only.')} />
                            {savedCa && !form.proxy_ca_pem && (
                                <FormControlLabel
                                    control={<Checkbox checked={Boolean(form.remove_proxy_ca)}
                                        onChange={e => set({ remove_proxy_ca: e.target.checked })} />}
                                    label={t('backups.transport.caRemove', 'Remove the saved CA and trust the system store')} />
                            )}
                        </>
                    )}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <AsyncButton variant="contained" onClick={save}
                    disabled={proxy && !(form.proxy_host ?? '').trim()}>
                    {t('common.save', 'Save')}
                </AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

const BackupTransport: React.FC<{
    target: BackupTarget;
    canManage: boolean;
    onChanged: () => void;
}> = ({ target, canManage, onChanged }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const proxy = target.transport?.transport === 'proxy';
    const certificate = target.transport?.certificate;
    return (
        <Typography variant="body2" component="div">
            {t('backups.transport.title', 'How hosts reach the storage')}:{' '}
            {proxy
                ? <>{t('backups.transport.viaProxy', 'restate-proxy at')} <code>{target.transport?.url}</code></>
                : t('backups.transport.viaNfs', 'NFS')}
            {proxy && !target.transport?.proxy_ca && (
                <Typography variant="caption" color="text.secondary" display="block">
                    {certificate
                        ? t('backups.transport.certIssued',
                            'Certificate from the SysManage CA, valid until {{date}}',
                            { date: new Date(certificate.expires).toLocaleDateString() })
                        : t('backups.transport.certWaiting',
                            'Waiting for the storage host to ask for its certificate')}
                </Typography>
            )}
            {canManage && (
                <Button size="small" sx={{ ml: 1 }} onClick={() => setOpen(true)}>
                    {t('backups.transport.change', 'Change')}
                </Button>
            )}
            <TransportDialog open={open} target={target} onClose={() => setOpen(false)} onSaved={onChanged} />
        </Typography>
    );
};

export default BackupTransport;
