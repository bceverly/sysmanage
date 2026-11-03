// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Create or change a backup policy by tag (Pro+ 24.6): which tag, its
// priority (the lowest wins where several cover a host), and the settings
// every tagged host gets -- the same fields as a host's own policy, which
// always beats a tag policy.

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
    MenuItem,
    Stack,
    Switch,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import type { PolicyInput } from '../../Services/backups';
import { createTagPolicy, updateTagPolicy } from '../../Services/backupTagPolicies';
import type { HostTag, TagPolicy, TagPolicyInput } from '../../Services/backupTagPolicies';
import { BUILTIN_HOOKS, DEFAULTS, GFS_DEFAULTS } from './BackupPolicyDialog';
import { apiDetail } from './backupLabels';
import { localWindow } from './windowLocalTime';

const lines = (text: string): string[] =>
    text.split('\n').map(line => line.trim()).filter(Boolean);

const number = (text: string): number => (text === '' ? 0 : Math.max(0, Math.floor(Number(text))));

const TagPolicyDialog: React.FC<{
    open: boolean;
    tags: HostTag[];
    existing: TagPolicy | null;
    onClose: () => void;
    onSaved: (message: string) => void;
}> = ({ open, tags, existing, onClose, onSaved }) => {
    const { t, i18n } = useTranslation();
    const [name, setName] = useState('');
    const [tagId, setTagId] = useState('');
    const [priority, setPriority] = useState(100);
    const [enabled, setEnabled] = useState(true);
    const [settings, setSettings] = useState<PolicyInput>({ ...DEFAULTS, ...GFS_DEFAULTS, window_start_hour: 5 });
    const [keep, setKeep] = useState('');
    const [skip, setSkip] = useState('');
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!open) return;
        setError(null);
        if (existing) {
            setName(existing.name);
            setTagId(existing.tag_id);
            setPriority(existing.priority);
            setEnabled(existing.enabled);
            setSettings({ ...DEFAULTS, ...existing.settings });
            setKeep((existing.settings.keep_paths ?? []).join('\n'));
            setSkip((existing.settings.skip_paths ?? []).join('\n'));
        } else {
            setName('');
            setTagId(tags[0]?.id ?? '');
            setPriority(100);
            setEnabled(true);
            setSettings({ ...DEFAULTS, ...GFS_DEFAULTS, window_start_hour: 5 });
            setKeep('');
            setSkip('');
        }
    }, [open, existing, tags]);

    const set = (part: Partial<PolicyInput>) => setSettings(current => ({ ...current, ...part }));
    const local = localWindow(settings.window_start_hour, i18n.language);

    const save = async () => {
        setError(null);
        const input: TagPolicyInput = {
            name: name.trim(),
            tag_id: tagId,
            priority,
            enabled,
            settings: { ...settings, keep_paths: lines(keep), skip_paths: lines(skip) },
        };
        try {
            const result = existing
                ? await updateTagPolicy(existing.id, input)
                : await createTagPolicy(input);
            onSaved(t('backups.tagPolicies.saved', 'Saved. Hosts following it: {{n}}.',
                { n: result.tag_policy.hosts_applied }));
            onClose();
        } catch (err) {
            setError(apiDetail(err, t('backups.tagPolicies.saveError', 'The tag policy could not be saved.')));
        }
    };

    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>
                {existing
                    ? t('backups.tagPolicies.editTitle', 'Change tag policy')
                    : t('backups.tagPolicies.addTitle', 'Add a tag policy')}
            </DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    {error && <Alert severity="error">{error}</Alert>}
                    <TextField label={t('backups.tagPolicies.name', 'Name')} value={name}
                        onChange={e => setName(e.target.value)} required />
                    <TextField select label={t('backups.tagPolicies.tag', 'Hosts with the tag')} value={tagId}
                        onChange={e => setTagId(e.target.value)} required>
                        {tags.map(tag => <MenuItem key={tag.id} value={tag.id}>{tag.name}</MenuItem>)}
                    </TextField>
                    <TextField type="number" label={t('backups.tagPolicies.priority', 'Priority')} value={priority}
                        slotProps={{ htmlInput: { min: 0, max: 1000 } }}
                        helperText={t('backups.tagPolicies.priorityHelp',
                            'Where several tag policies cover a host, the lowest number wins. A host\'s own policy always wins.')}
                        onChange={e => setPriority(number(e.target.value))} />
                    <FormControlLabel
                        control={<Switch checked={enabled} onChange={e => setEnabled(e.target.checked)} />}
                        label={t('backups.tagPolicies.enabled', 'Apply this tag policy')}
                    />
                    <Typography variant="subtitle2">{t('backups.tagPolicies.settings', 'Settings for every tagged host')}</Typography>
                    <FormControlLabel
                        control={<Switch checked={settings.enabled} onChange={e => set({ enabled: e.target.checked })} />}
                        label={t('backups.policy.enabled', 'Back up this host on a schedule')}
                    />
                    <TextField type="number" label={t('backups.policy.intervalHours', 'Every (hours)')}
                        value={settings.interval_hours} slotProps={{ htmlInput: { min: 1, max: 720 } }}
                        onChange={e => set({ interval_hours: number(e.target.value) || 1 })} />
                    <TextField type="number" label={t('backups.policy.windowStart', 'Start hour (UTC, optional)')}
                        value={settings.window_start_hour ?? ''} slotProps={{ htmlInput: { min: 0, max: 23 } }}
                        helperText={local
                            ? t('backups.policy.windowLocal', 'In your time zone: {{start}} to {{end}}.', local)
                            : t('backups.policy.windowHelp', 'Backups start only in the six hours from this hour.')}
                        onChange={e => set({ window_start_hour: e.target.value === '' ? null : Number(e.target.value) })} />
                    <Stack direction="row" spacing={1}>
                        <TextField type="number" label={t('backups.policy.keepLast', 'Snapshots to keep')}
                            value={settings.keep_last} onChange={e => set({ keep_last: number(e.target.value) || 1 })} />
                        <TextField type="number" label={t('backups.policy.keepDaily', 'Days to keep')}
                            value={settings.keep_daily} onChange={e => set({ keep_daily: number(e.target.value) })} />
                        <TextField type="number" label={t('backups.policy.keepWeekly', 'Weeks to keep')}
                            value={settings.keep_weekly} onChange={e => set({ keep_weekly: number(e.target.value) })} />
                    </Stack>
                    <Stack direction="row" spacing={1}>
                        <TextField type="number" label={t('backups.policy.keepMonthly', 'Months to keep')}
                            value={settings.keep_monthly} onChange={e => set({ keep_monthly: number(e.target.value) })} />
                        <TextField type="number" label={t('backups.policy.keepYearly', 'Years to keep')}
                            value={settings.keep_yearly} onChange={e => set({ keep_yearly: number(e.target.value) })} />
                        <TextField type="number" label={t('backups.tagPolicies.verifyDays', 'Full-read check every (days, 0 = off)')}
                            value={settings.verify_interval_days}
                            onChange={e => set({ verify_interval_days: number(e.target.value) })} />
                    </Stack>
                    <FormControlLabel
                        control={<Switch checked={settings.quiesce} onChange={e => set({ quiesce: e.target.checked })} />}
                        label={t('backups.policy.quiesce', 'Pause services while reading their data')}
                    />
                    {settings.quiesce && (
                        <Autocomplete multiple freeSolo options={BUILTIN_HOOKS} value={settings.quiesce_with}
                            onChange={(_e, value) => set({ quiesce_with: value.map(v => String(v).trim()).filter(Boolean) })}
                            renderInput={params => (
                                <TextField {...params} label={t('backups.policy.quiesceWithPick', 'Services to pause')}
                                    helperText={t('backups.tagPolicies.quiesceHelp', 'A service a host does not have is skipped there.')} />
                            )} />
                    )}
                    <TextField multiline minRows={2} label={t('backups.policy.keepPaths', 'Also back up (one path pattern per line)')}
                        value={keep} onChange={e => setKeep(e.target.value)} />
                    <TextField multiline minRows={2} label={t('backups.policy.skipPaths', 'Leave out (one path pattern per line)')}
                        value={skip} onChange={e => setSkip(e.target.value)} />
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <AsyncButton variant="contained" onClick={save} disabled={!name.trim() || !tagId}>
                    {t('common.save', 'Save')}
                </AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

export default TagPolicyDialog;
