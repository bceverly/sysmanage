// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Bandwidth by the hour through restate-proxy (ROADMAP 25.5 limits, 25.7:
// Professional+).  Each rule is restate-proxy's own grant line -- hours of
// the storage host's day and a rate -- and one rate may cover every other
// hour.  Without the license the rules are kept but not applied, so backups
// through the proxy run at full speed.

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    IconButton,
    MenuItem,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { setProxyBandwidth } from '../../Services/backups';
import type { BackupTarget } from '../../Services/backups';
import { apiDetail } from './backupLabels';

interface Row {
    from: string;
    to: string;
    rate: string;
}

const HOURS = Array.from({ length: 25 }, (_v, i) => String(i).padStart(2, '0'));
const RANGED = /^(\d{2})-(\d{2}) (.+)$/;

export const toForm = (rules: string[]): { rows: Row[]; rest: string } => {
    const rows: Row[] = [];
    let rest = '';
    for (const rule of rules) {
        const match = RANGED.exec(rule);
        if (match) {
            rows.push({ from: match[1], to: match[2], rate: match[3] });
        } else {
            rest = rule;
        }
    }
    return { rows, rest };
};

export const toRules = (rows: Row[], rest: string): string[] => [
    ...rows.filter(r => r.rate.trim()).map(r => `${r.from}-${r.to} ${r.rate.trim()}`),
    ...(rest.trim() ? [rest.trim()] : []),
];

export const BandwidthDialog: React.FC<{
    open: boolean;
    target: BackupTarget;
    onClose: () => void;
    onSaved: () => void;
}> = ({ open, target, onClose, onSaved }) => {
    const { t } = useTranslation();
    const [rows, setRows] = useState<Row[]>([]);
    const [rest, setRest] = useState('');
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        if (open) {
            const form = toForm(target.proxy_bandwidth?.rules ?? []);
            setRows(form.rows);
            setRest(form.rest);
            setError(null);
        }
    }, [open, target]);
    const change = (index: number, patch: Partial<Row>) =>
        setRows(current => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
    const save = async (rules: string[]) => {
        setError(null);
        try {
            await setProxyBandwidth(target.id, rules);
            onSaved();
            onClose();
        } catch (err) {
            setError(apiDetail(err, t('backups.bandwidth.saveError', 'The bandwidth limits could not be saved.')));
        }
    };
    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>{t('backups.bandwidth.title', 'Bandwidth through restate-proxy')}</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    {error && <Alert severity="error">{error}</Alert>}
                    <Typography variant="body2" color="text.secondary">
                        {t('backups.bandwidth.intro',
                            'Hold each host to a rate during the hours you name, by the storage host\'s own clock: for example 2MiB/s from 08 to 18, so a backup that runs late stays out of the working day\'s link. Rates are 512KiB/s, 2MiB/s, 1GiB/s or unlimited, and 64KiB/s at the least.')}
                    </Typography>
                    {rows.map((row, index) => (
                        <Box key={index} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                            <TextField select size="small" label={t('backups.bandwidth.from', 'From')} value={row.from}
                                onChange={e => change(index, { from: e.target.value })} sx={{ width: 96 }}>
                                {HOURS.slice(0, 24).map(h => <MenuItem key={h} value={h}>{h}:00</MenuItem>)}
                            </TextField>
                            <TextField select size="small" label={t('backups.bandwidth.to', 'To')} value={row.to}
                                onChange={e => change(index, { to: e.target.value })} sx={{ width: 96 }}>
                                {HOURS.slice(1).map(h => <MenuItem key={h} value={h}>{h}:00</MenuItem>)}
                            </TextField>
                            <TextField size="small" label={t('backups.bandwidth.rate', 'Rate')} value={row.rate}
                                placeholder="2MiB/s" onChange={e => change(index, { rate: e.target.value })}
                                sx={{ flex: 1 }} />
                            <IconButton aria-label={t('backups.bandwidth.removeRule', 'Remove this rule')}
                                onClick={() => setRows(current => current.filter((_r, i) => i !== index))}>
                                <DeleteIcon />
                            </IconButton>
                        </Box>
                    ))}
                    <Box>
                        <Button size="small" onClick={() => setRows(current => [...current, { from: '08', to: '18', rate: '' }])}>
                            {t('backups.bandwidth.addRule', 'Add hours')}
                        </Button>
                    </Box>
                    <TextField size="small" label={t('backups.bandwidth.rest', 'Every other hour (optional)')}
                        value={rest} placeholder="20MiB/s" onChange={e => setRest(e.target.value)}
                        helperText={t('backups.bandwidth.restHelp', 'Left empty, the other hours have no limit.')} />
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={() => save([])}>{t('backups.bandwidth.clear', 'Remove every limit')}</Button>
                <Box sx={{ flex: 1 }} />
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <AsyncButton variant="contained" onClick={() => save(toRules(rows, rest))}>
                    {t('common.save', 'Save')}
                </AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

const BackupProxyBandwidth: React.FC<{
    target: BackupTarget;
    canManage: boolean;
    onChanged: () => void;
    /** false: the card puts the Change button in its own header. */
    inline?: boolean;
}> = ({ target, canManage, onChanged, inline = true }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    if (target.transport?.transport !== 'proxy') {
        return null;
    }
    const view = target.proxy_bandwidth ?? { rules: [], licensed: false, applied: false };
    const rules = view.rules;
    let note: string | null = null;
    if (!view.licensed) {
        note = rules.length
            ? t('backups.bandwidth.unlicensed', 'Not applied: bandwidth limits need Professional+. Backups through the proxy run at full speed.')
            : t('backups.bandwidth.proPlus', 'Bandwidth limits by the hour are a Professional+ feature.');
    } else if (view.reason === 'storage_too_old') {
        note = t('backups.bandwidth.tooOld', 'Not applied yet: the storage host\'s restate is too old to apply bandwidth limits. Upgrade restate on it.');
    }
    return (
        <Typography variant="body2" component="div">
            {t('backups.bandwidth.label', 'Bandwidth')}:{' '}
            {rules.length ? <code>{rules.join(', ')}</code> : t('backups.bandwidth.none', 'no limit')}
            {canManage && inline && view.licensed && (
                <Button size="small" sx={{ ml: 1 }} onClick={() => setOpen(true)}>
                    {t('backups.transport.change', 'Change')}
                </Button>
            )}
            {canManage && inline && !view.licensed && rules.length > 0 && (
                <Button size="small" sx={{ ml: 1 }} onClick={() => setOpen(true)}>
                    {t('backups.bandwidth.clear', 'Remove every limit')}
                </Button>
            )}
            {note && (
                <Typography variant="caption" color="text.secondary" display="block">{note}</Typography>
            )}
            {inline && (
                <BandwidthDialog open={open} target={target} onClose={() => setOpen(false)} onSaved={onChanged} />
            )}
        </Typography>
    );
};

export default BackupProxyBandwidth;
