// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The host against the fleet NTP policy (Phase 23.3 S5b), on its Clock card.

import React from 'react';
import { Alert, Box, Chip, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { HostNtpPolicy } from '../../Services/timeSync';
import { policyFindingText } from './timeSyncLabels';

export const policyChip = (t: TFunction, compliant: boolean | null, findings: number) => {
    if (compliant === null) {
        return null;
    }
    return compliant ? (
        <Chip size="small" color="success" label={t('timeSync.policy.compliant', 'Follows the policy')} />
    ) : (
        <Chip
            size="small"
            color="warning"
            label={t('timeSync.policy.differences', '{{count}} differences', { count: findings })}
        />
    );
};

const applyText = (t: TFunction, status: string | null): string | null => {
    switch (status) {
        case 'queued':
            return t('timeSync.policy.apply.queued', 'Applying the policy...');
        case 'succeeded':
            return t('timeSync.policy.apply.succeeded', 'The policy was applied.');
        case 'failed':
            return t('timeSync.policy.apply.failed', 'Applying the policy failed; it is retried automatically.');
        default:
            return null;
    }
};

const HostClockPolicy: React.FC<{ verdict: HostNtpPolicy | null }> = ({ verdict }) => {
    const { t } = useTranslation();
    if (!verdict || (!verdict.policy && !verdict.conflict)) {
        return null;
    }
    const applied = applyText(t, verdict.apply_status);
    return (
        <Box sx={{ mt: 2 }}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="subtitle2">{t('timeSync.policy.title', 'NTP policy')}</Typography>
                {policyChip(t, verdict.compliant, verdict.findings.length)}
            </Stack>
            {verdict.policy && (
                <Typography variant="body2" color="text.secondary">
                    {t('timeSync.policy.wants', 'Policy servers: {{servers}}', {
                        servers: verdict.policy.servers.join(', '),
                    })}
                </Typography>
            )}
            {verdict.configured_servers && (
                <Typography variant="body2" color="text.secondary">
                    {t('timeSync.policy.has', 'Configured on the host: {{servers}}', {
                        servers: verdict.configured_servers.join(', ') || '-',
                    })}
                </Typography>
            )}
            {verdict.findings.map(f => (
                <Typography key={f.code} variant="body2">{`- ${policyFindingText(t, f.code)}`}</Typography>
            ))}
            {applied && (
                <Alert severity={verdict.apply_status === 'failed' ? 'warning' : 'info'} sx={{ mt: 1 }}>
                    {applied}
                    {verdict.apply_error && (
                        <Typography variant="caption" component="div" sx={{ fontFamily: 'monospace' }}>
                            {verdict.apply_error}
                        </Typography>
                    )}
                </Alert>
            )}
        </Box>
    );
};

export default HostClockPolicy;
