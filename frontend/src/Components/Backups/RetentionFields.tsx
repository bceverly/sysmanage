// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Grandfather-father-son retention in the backup policy dialog (ROADMAP
// 24.6): beside "Snapshots to keep", the newest snapshot of each of the last
// N days, ISO weeks and months.  Setting them needs the Pro+ backup engine;
// without it a policy that already has them shows them read-only (they are
// still honored).  "Preview the next prune" asks the server which snapshots
// the next prune would keep and remove -- restate's own choice, ported.

import React, { useState } from 'react';
import { Alert, Button, Stack, TextField, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { previewRetention } from '../../Services/backups';
import type { PolicyInput, RetentionPreview } from '../../Services/backups';
import { useModuleLicensed } from '../../hooks/useModuleLicensed';
import { apiDetail } from './backupLabels';

type Counts = Pick<PolicyInput, 'keep_last' | 'keep_daily' | 'keep_weekly' | 'keep_monthly'>;

const SHOWN = 5;

const RetentionFields: React.FC<{
    hostId: string;
    hasPolicy: boolean;
    counts: Counts;
    onChange: (counts: Partial<Counts>) => void;
}> = ({ hostId, hasPolicy, counts, onChange }) => {
    const { t } = useTranslation();
    const licensed = useModuleLicensed('backup_engine');
    const [preview, setPreview] = useState<RetentionPreview | null>(null);
    const [error, setError] = useState<string | null>(null);
    const number = (text: string): number => (text === '' ? 0 : Math.max(0, Math.floor(Number(text))));
    const any = (counts.keep_daily ?? 0) + (counts.keep_weekly ?? 0) + (counts.keep_monthly ?? 0) > 0;

    if (!licensed) {
        return any ? (
            <Typography variant="body2" color="text.secondary">
                {t('backups.policy.gfsReadOnly',
                    'Also keeps the newest of the last {{daily}} days, {{weekly}} weeks and {{monthly}} months (changing these needs Professional+).',
                    { daily: counts.keep_daily ?? 0, weekly: counts.keep_weekly ?? 0, monthly: counts.keep_monthly ?? 0 })}
            </Typography>
        ) : null;
    }

    const runPreview = async () => {
        setError(null);
        try {
            setPreview(await previewRetention(hostId, counts));
        } catch (err) {
            setError(apiDetail(err, t('backups.policy.previewError', 'The preview could not be made.')));
        }
    };

    const field = (key: 'keep_daily' | 'keep_weekly' | 'keep_monthly', label: string, max: number) => (
        <TextField type="number" label={label} value={counts[key] ?? 0}
            slotProps={{ htmlInput: { min: 0, max } }}
            onChange={e => { onChange({ [key]: number(e.target.value) }); setPreview(null); }} />
    );

    return (
        <Stack spacing={1}>
            <Typography variant="body2" color="text.secondary">
                {t('backups.policy.gfsHelp',
                    'Also keep the newest snapshot of each of the last N days, weeks and months that have one (0 = not used).')}
            </Typography>
            <Stack direction="row" spacing={1}>
                {field('keep_daily', t('backups.policy.keepDaily', 'Days to keep'), 3650)}
                {field('keep_weekly', t('backups.policy.keepWeekly', 'Weeks to keep'), 520)}
                {field('keep_monthly', t('backups.policy.keepMonthly', 'Months to keep'), 240)}
            </Stack>
            {hasPolicy && (
                <div>
                    <Button size="small" onClick={() => void runPreview()}>
                        {t('backups.policy.preview', 'Preview the next prune')}
                    </Button>
                </div>
            )}
            {error && <Alert severity="error">{error}</Alert>}
            {preview && (
                <Alert severity={preview.removed.length ? 'warning' : 'info'}>
                    {t('backups.policy.previewResult', 'Next prune: {{kept}} kept, {{removed}} removed.',
                        { kept: preview.kept.length, removed: preview.removed.length })}
                    {preview.removed.length > 0 && (
                        <Typography variant="body2" component="div" sx={{ mt: 0.5, fontFamily: 'monospace' }}>
                            {preview.removed.slice(0, SHOWN).join(', ')}
                            {preview.removed.length > SHOWN
                                ? ` ${t('backups.policy.previewMore', 'and {{n}} more', { n: preview.removed.length - SHOWN })}`
                                : ''}
                        </Typography>
                    )}
                </Alert>
            )}
        </Stack>
    );
};

export default RetentionFields;
