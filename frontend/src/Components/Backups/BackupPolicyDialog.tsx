// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// One host's backup policy (Phase 24): how often, when, how many snapshots
// the storage host keeps, how often it checks the repository, and which
// services restate pauses while it reads.

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControlLabel,
    Stack,
    Switch,
    TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { savePolicy } from '../../Services/backups';
import type { BackupPolicy, PolicyInput } from '../../Services/backups';
import { apiDetail } from './backupLabels';

const DEFAULTS: PolicyInput = {
    enabled: true,
    interval_hours: 24,
    window_start_hour: null,
    keep_last: 14,
    check_interval_days: 7,
    quiesce: false,
    quiesce_with: [],
};

const toInput = (policy: BackupPolicy | null): PolicyInput =>
    policy
        ? {
              enabled: policy.enabled,
              interval_hours: policy.interval_hours,
              window_start_hour: policy.window_start_hour,
              keep_last: policy.keep_last,
              check_interval_days: policy.check_interval_days,
              quiesce: policy.quiesce,
              quiesce_with: policy.quiesce_with,
          }
        : DEFAULTS;

const BackupPolicyDialog: React.FC<{
    open: boolean;
    hostId: string;
    fqdn: string;
    policy: BackupPolicy | null;
    onClose: () => void;
    onSaved: () => void;
}> = ({ open, hostId, fqdn, policy, onClose, onSaved }) => {
    const { t } = useTranslation();
    const [form, setForm] = useState<PolicyInput>(toInput(policy));
    const [hooks, setHooks] = useState('');
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (open) {
            const input = toInput(policy);
            setForm(input);
            setHooks(input.quiesce_with.join(', '));
            setError(null);
        }
    }, [open, policy]);

    const set = (patch: Partial<PolicyInput>) => setForm(f => ({ ...f, ...patch }));
    const number = (value: string) => (value === '' ? 0 : Number(value));

    const save = async () => {
        const quiesce_with = hooks.split(',').map(h => h.trim()).filter(Boolean);
        try {
            await savePolicy(hostId, { ...form, quiesce_with });
            onSaved();
            onClose();
        } catch (err) {
            setError(apiDetail(err, t('backups.policy.saveError', 'The backup policy could not be saved.')));
        }
    };

    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>{t('backups.policy.title', 'Backup policy for {{host}}', { host: fqdn })}</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    {error && <Alert severity="error">{error}</Alert>}
                    <FormControlLabel
                        control={<Switch checked={form.enabled} onChange={e => set({ enabled: e.target.checked })} />}
                        label={t('backups.policy.enabled', 'Back up this host on a schedule')}
                    />
                    <TextField type="number" label={t('backups.policy.intervalHours', 'Every (hours)')}
                        value={form.interval_hours} inputProps={{ min: 1, max: 720 }}
                        onChange={e => set({ interval_hours: number(e.target.value) })} />
                    <TextField type="number" label={t('backups.policy.windowStart', 'Start hour (UTC, optional)')}
                        value={form.window_start_hour ?? ''} inputProps={{ min: 0, max: 23 }}
                        helperText={t('backups.policy.windowHelp', 'Backups start only in the six hours from this hour.')}
                        onChange={e => set({ window_start_hour: e.target.value === '' ? null : Number(e.target.value) })} />
                    <TextField type="number" label={t('backups.policy.keepLast', 'Snapshots to keep')}
                        value={form.keep_last} inputProps={{ min: 1, max: 1000 }}
                        onChange={e => set({ keep_last: number(e.target.value) })} />
                    <TextField type="number" label={t('backups.policy.checkDays', 'Check the repository every (days)')}
                        value={form.check_interval_days} inputProps={{ min: 1, max: 90 }}
                        onChange={e => set({ check_interval_days: number(e.target.value) })} />
                    <FormControlLabel
                        control={<Switch checked={form.quiesce} onChange={e => set({ quiesce: e.target.checked })} />}
                        label={t('backups.policy.quiesce', 'Pause services while reading their data')}
                    />
                    {form.quiesce && (
                        <TextField label={t('backups.policy.quiesceWith', 'Hooks (comma separated)')} value={hooks}
                            onChange={e => setHooks(e.target.value)}
                            helperText={t('backups.policy.quiesceHelp', 'For example: postgres, nextcloud')} />
                    )}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <AsyncButton variant="contained" onClick={save}>{t('common.save', 'Save')}</AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

export default BackupPolicyDialog;
