// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Scheduled verification (ROADMAP 24.6, Pro+ backup engine): restate's
// `check --read-all` on the backed-up host every N days -- a test restore
// that writes nothing.  The policy dialog's cadence field (read-only without
// the engine, like the retention counts), the host card's line, and the
// hosts table's caption when a pass failed or none passed in time.

import React from 'react';
import { TextField, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { Verification } from '../../Services/backups';
import { useModuleLicensed } from '../../hooks/useModuleLicensed';
import { formatTime } from './backupLabels';

export const verificationText = (t: TFunction, v: Verification): string => {
    switch (v.state) {
        case 'verified':
            return t('backups.verify.verified', 'Verified (last passed {{when}})',
                { when: formatTime(v.last_good_at) });
        case 'running':
            return t('backups.verify.running', 'Running now');
        case 'failed':
            return t('backups.verify.failed', 'The last pass failed');
        default:
            return v.last_good_at
                ? t('backups.verify.unverified', 'Not verified in {{days}} days (last passed {{when}})',
                    { days: v.interval_days, when: formatTime(v.last_good_at) })
                : t('backups.verify.never', 'Not verified yet');
    }
};

/** The host card's line; nothing when verification is off. */
export const VerificationLine: React.FC<{ verification?: Verification | null }> = ({ verification }) => {
    const { t } = useTranslation();
    if (!verification || verification.state === 'off') {
        return null;
    }
    const failed = verification.state === 'failed';
    return (
        <Typography variant="body2" color={failed ? 'error.main' : undefined}>
            {t('backups.verify.title', 'Full-read verification')}: {verificationText(t, verification)}
            {failed && verification.last_message ? ` - ${verification.last_message}` : ''}
        </Typography>
    );
};

/** The hosts table's caption, only when attention is needed. */
export const VerificationCaption: React.FC<{ verification?: Verification | null }> = ({ verification }) => {
    const { t } = useTranslation();
    if (!verification || !['failed', 'unverified'].includes(verification.state)) {
        return null;
    }
    return (
        <Typography variant="caption" display="block"
            color={verification.state === 'failed' ? 'error.main' : 'warning.main'}>
            {t('backups.verify.title', 'Full-read verification')}: {verificationText(t, verification)}
        </Typography>
    );
};

/** The policy dialog's cadence (days, 0 = off). */
export const VerificationField: React.FC<{
    days: number;
    onChange: (days: number) => void;
}> = ({ days, onChange }) => {
    const { t } = useTranslation();
    const licensed = useModuleLicensed('backup_engine');
    if (!licensed) {
        return days > 0 ? (
            <Typography variant="body2" color="text.secondary">
                {t('backups.verify.readOnly',
                    'Reads the whole repository back every {{days}} days (changing this needs Professional+).',
                    { days })}
            </Typography>
        ) : null;
    }
    return (
        <TextField type="number" value={days}
            label={t('backups.verify.field', 'Read the whole repository back every (days)')}
            helperText={t('backups.verify.help',
                '0 = off. Each pass reads the whole repository over the network, so weeks rather than days.')}
            slotProps={{ htmlInput: { min: 0, max: 365 } }}
            onChange={e => onChange(e.target.value === '' ? 0 : Math.max(0, Math.floor(Number(e.target.value))))} />
    );
};
