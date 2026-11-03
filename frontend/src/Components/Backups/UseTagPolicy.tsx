// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Use the tag policy" (Pro+ 24.6, 2026-11-03): hand a host on its own
// policy back to the tag policy that covers it.  Its policy is kept -- the
// repository, encryption keys, snapshots and history stay -- and only the
// settings a tag policy controls change; the confirmation names the rule
// and every setting it replaces.  Configure makes it the host's own again.

import React, { useState } from 'react';
import {
    Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, List, ListItem, Typography,
} from '@mui/material';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { handOverToTagPolicy, previewTagPolicyHandover } from '../../Services/backups';
import type { PolicySource, TagPolicyHandover } from '../../Services/backups';
import { apiDetail } from './backupLabels';

/** The policy dialog's label for one setting a tag policy controls. */
const settingLabel = (t: TFunction, key: string): string => {
    const labels: Record<string, string> = {
        enabled: t('backups.policy.enabled', 'Back up this host on a schedule'),
        interval_hours: t('backups.policy.intervalHours', 'Every (hours)'),
        window_start_hour: t('backups.policy.windowStart', 'Start hour (UTC, optional)'),
        keep_last: t('backups.policy.keepLast', 'Snapshots to keep'),
        check_interval_days: t('backups.policy.checkDays', 'Check the repository every (days)'),
        quiesce: t('backups.policy.quiesce', 'Pause services while reading their data'),
        keep_daily: t('backups.policy.keepDaily', 'Days to keep'),
        keep_weekly: t('backups.policy.keepWeekly', 'Weeks to keep'),
        keep_monthly: t('backups.policy.keepMonthly', 'Months to keep'),
        keep_yearly: t('backups.policy.keepYearly', 'Years to keep'),
        verify_interval_days: t('backups.verify.field', 'Read the whole repository back every (days)'),
        quiesce_with: t('backups.policy.quiesceWithPick', 'Services to pause'),
        keep_paths: t('backups.policy.keepPaths', 'Also back up (one path pattern per line)'),
        skip_paths: t('backups.policy.skipPaths', 'Leave out (one path pattern per line)'),
    };
    return labels[key] ?? key;
};

const shown = (t: TFunction, value: unknown): string => {
    if (value === null || value === undefined || value === '') return t('backups.useTag.none', '(none)');
    if (typeof value === 'boolean') return value ? t('common.yes', 'Yes') : t('common.no', 'No');
    if (Array.isArray(value)) return value.length ? value.join(', ') : t('backups.useTag.none', '(none)');
    return String(value);
};

interface Props {
    hostId: string;
    source?: PolicySource | null;
    onDone: () => void;
}

/** The button and its confirmation; nothing unless a tag policy covers a
 *  host that is on its own policy. */
export const UseTagPolicyButton: React.FC<Props> = ({ hostId, source, onDone }) => {
    const { t } = useTranslation();
    const [preview, setPreview] = useState<TagPolicyHandover | null>(null);
    const [error, setError] = useState<string | null>(null);
    const available = source?.kind === 'own' ? source.tag_policy_available : undefined;
    if (!available) return null;

    const open = async () => {
        setError(null);
        try {
            setPreview(await previewTagPolicyHandover(hostId));
        } catch (err) {
            setError(apiDetail(err, t('backups.useTag.previewError', 'The tag policy could not be checked.')));
        }
    };
    const confirm = async () => {
        try {
            await handOverToTagPolicy(hostId);
            setPreview(null);
            onDone();
        } catch (err) {
            setError(apiDetail(err, t('backups.useTag.error', 'The host could not be handed to its tag policy.')));
        }
    };

    return (
        <>
            <AsyncButton size="small" onClick={open}>
                {t('backups.useTag.button', 'Use the tag policy')}
            </AsyncButton>
            {error && !preview && <Alert severity="error">{error}</Alert>}
            {preview && (
                <Dialog open onClose={() => setPreview(null)} maxWidth="sm" fullWidth>
                    <DialogTitle>{t('backups.useTag.title', 'Use the tag policy')}</DialogTitle>
                    <DialogContent>
                        <Typography variant="body2" sx={{ mb: 1 }}>
                            {t('backups.useTag.intro',
                                'This host will follow the tag policy {{name}} (priority {{priority}}). Its repository, encryption keys, snapshots and history stay as they are.',
                                { name: preview.tag_policy.name, priority: preview.tag_policy.priority })}
                        </Typography>
                        {preview.changes.length ? (
                            <>
                                <Typography variant="body2">
                                    {t('backups.useTag.replaces', 'These settings of this host are replaced:')}
                                </Typography>
                                <List dense>
                                    {preview.changes.map(change => (
                                        <ListItem key={change.key} disableGutters>
                                            {t('backups.useTag.change', '{{setting}}: {{from}} -> {{to}}', {
                                                setting: settingLabel(t, change.key),
                                                from: shown(t, change.from),
                                                to: shown(t, change.to),
                                            })}
                                        </ListItem>
                                    ))}
                                </List>
                            </>
                        ) : (
                            <Typography variant="body2">
                                {t('backups.useTag.same', 'Its settings already match the tag policy.')}
                            </Typography>
                        )}
                        {error && <Alert severity="error">{error}</Alert>}
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={() => setPreview(null)}>{t('common.cancel', 'Cancel')}</Button>
                        <AsyncButton variant="contained" onClick={confirm}>
                            {t('backups.useTag.confirm', 'Use the tag policy')}
                        </AsyncButton>
                    </DialogActions>
                </Dialog>
            )}
        </>
    );
};

export default UseTagPolicyButton;
