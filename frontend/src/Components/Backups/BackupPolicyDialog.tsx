// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// One host's backup policy (Phase 24): how often, when, how many snapshots
// the storage host keeps (and, Pro+, how many daily / weekly / monthly), how often it checks the repository, which
// services restate pauses while it reads, and which paths to also back up
// or leave out (one restate pattern per line; leave-outs win).

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Autocomplete,
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
import RetentionFields from './RetentionFields';
import { VerificationField } from './VerificationStatus';

const DEFAULTS: PolicyInput = {
    enabled: true,
    interval_hours: 24,
    window_start_hour: null,
    keep_last: 14,
    keep_daily: 0,
    keep_weekly: 0,
    keep_monthly: 0,
    keep_yearly: 0,
    verify_interval_days: 0,
    check_interval_days: 7,
    quiesce: false,
    quiesce_with: [],
    keep_paths: [],
    skip_paths: [],
};

const lines = (text: string): string[] =>
    text.split('\n').map(line => line.trim()).filter(Boolean);

const toInput = (policy: BackupPolicy | null): PolicyInput =>
    policy
        ? {
              enabled: policy.enabled,
              interval_hours: policy.interval_hours,
              window_start_hour: policy.window_start_hour,
              keep_last: policy.keep_last,
              keep_daily: policy.keep_daily ?? 0,
              keep_weekly: policy.keep_weekly ?? 0,
              keep_monthly: policy.keep_monthly ?? 0,
              keep_yearly: policy.keep_yearly ?? 0,
              verify_interval_days: policy.verify_interval_days ?? 0,
              check_interval_days: policy.check_interval_days,
              quiesce: policy.quiesce,
              quiesce_with: policy.quiesce_with,
              keep_paths: policy.keep_paths ?? [],
              skip_paths: policy.skip_paths ?? [],
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
    const [hooks, setHooks] = useState<string[]>([]);
    const [keep, setKeep] = useState('');
    const [skip, setSkip] = useState('');
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (open) {
            const input = toInput(policy);
            setForm(input);
            setHooks(input.quiesce_with);
            setKeep(input.keep_paths.join('\n'));
            setSkip(input.skip_paths.join('\n'));
            setError(null);
        }
    }, [open, policy]);

    const set = (patch: Partial<PolicyInput>) => setForm(f => ({ ...f, ...patch }));
    const available = policy?.available_hooks ?? [];
    const number = (value: string) => (value === '' ? 0 : Number(value));

    const save = async () => {
        const quiesce_with = hooks.map(h => h.trim()).filter(Boolean);
        try {
            await savePolicy(hostId, {
                ...form,
                quiesce_with,
                keep_paths: lines(keep),
                skip_paths: lines(skip),
            });
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
                        value={form.interval_hours} slotProps={{ htmlInput: { min: 1, max: 720 } }}
                        onChange={e => set({ interval_hours: number(e.target.value) })} />
                    <TextField type="number" label={t('backups.policy.windowStart', 'Start hour (UTC, optional)')}
                        value={form.window_start_hour ?? ''} slotProps={{ htmlInput: { min: 0, max: 23 } }}
                        helperText={t('backups.policy.windowHelp', 'Backups start only in the six hours from this hour.')}
                        onChange={e => set({ window_start_hour: e.target.value === '' ? null : Number(e.target.value) })} />
                    <TextField type="number" label={t('backups.policy.keepLast', 'Snapshots to keep')}
                        value={form.keep_last} slotProps={{ htmlInput: { min: 1, max: 1000 } }}
                        onChange={e => set({ keep_last: number(e.target.value) })} />
                    <RetentionFields hostId={hostId} hasPolicy={policy !== null}
                        yearlySupported={policy?.yearly_supported ?? false}
                        counts={{ keep_last: form.keep_last, keep_daily: form.keep_daily,
                            keep_weekly: form.keep_weekly, keep_monthly: form.keep_monthly,
                            keep_yearly: form.keep_yearly }}
                        onChange={counts => set(counts)} />
                    <TextField type="number" label={t('backups.policy.checkDays', 'Check the repository every (days)')}
                        value={form.check_interval_days} slotProps={{ htmlInput: { min: 1, max: 90 } }}
                        onChange={e => set({ check_interval_days: number(e.target.value) })} />
                    <VerificationField days={form.verify_interval_days ?? 0}
                        onChange={days => set({ verify_interval_days: days })} />
                    <FormControlLabel
                        control={<Switch checked={form.quiesce} onChange={e => set({ quiesce: e.target.checked })} />}
                        label={t('backups.policy.quiesce', 'Pause services while reading their data')}
                    />
                    {form.quiesce && (
                        // The hooks restate found on this host (2.1+), and any
                        // name typed in -- older restates report none.
                        <Autocomplete multiple freeSolo options={available}
                            value={hooks} onChange={(_e, value) => setHooks(value as string[])}
                            renderInput={params => (
                                <TextField {...params} label={t('backups.policy.quiesceWithPick', 'Services to pause')}
                                    helperText={available.length
                                        ? t('backups.policy.quiesceFound', 'Found on this host: {{hooks}}', { hooks: available.join(', ') })
                                        : t('backups.policy.quiesceHelp', 'For example: postgres, nextcloud')} />
                            )} />
                    )}
                    <TextField multiline minRows={2} label={t('backups.policy.skipPaths', 'Leave out (one path pattern per line)')}
                        value={skip} onChange={e => setSkip(e.target.value)}
                        helperText={t('backups.policy.skipHelp',
                            'For example: /home/*/.local/share/Trash or **/previews. Caches, Downloads and build output are already left out.')} />
                    <TextField multiline minRows={2} label={t('backups.policy.keepPaths', 'Also back up (one path pattern per line)')}
                        value={keep} onChange={e => setKeep(e.target.value)}
                        helperText={t('backups.policy.keepHelp',
                            'Paths the built-in rules leave out, such as /home/*/Downloads. A path matched by a leave-out pattern is still left out.')} />
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
