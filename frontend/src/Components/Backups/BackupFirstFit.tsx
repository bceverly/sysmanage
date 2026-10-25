// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Will this host's first backup fit on the target? (ROADMAP 24.8)  Before a
// host's first good backup the server compares restate's estimate with the
// storage's free space; a scheduled first backup that would not fit is held,
// and this says why and where to start leaving things out.

import React from 'react';
import { Alert, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { FirstFit } from '../../Services/backups';
import { formatBytes } from './backupLabels';

const largestLines = (fit: FirstFit): string[] =>
    fit.largest.map(dir => `${dir.path} - ${formatBytes(dir.bytes)}`);

/** One line for the hosts table: only when it does not fit. */
export const FirstFitCaption: React.FC<{ fit: FirstFit | null }> = ({ fit }) => {
    const { t } = useTranslation();
    if (!fit || fit.fits) return null;
    return (
        <Tooltip title={largestLines(fit).join('\n')} placement="bottom-start">
            <Typography variant="caption" display="block" color="warning.main" sx={{ whiteSpace: 'pre-line' }}>
                {t('backups.firstFit.short', 'First backup may not fit')}
            </Typography>
        </Tooltip>
    );
};

/** The host card: the estimate, and the warning with the largest folders. */
export const FirstFitNote: React.FC<{ fit: FirstFit | null }> = ({ fit }) => {
    const { t } = useTranslation();
    if (!fit) return null;
    if (fit.fits) {
        return (
            <Typography variant="body2">
                {t('backups.firstFit.estimate', 'First backup: about {{size}} to keep', { size: formatBytes(fit.estimate_bytes) })}
            </Typography>
        );
    }
    return (
        <Alert severity="warning" sx={{ my: 1 }}>
            {t('backups.firstFit.wontFit',
                'The first backup may not fit: about {{size}} to keep and {{free}} free on the storage. It waits until there is room, or until you leave some of it out in the policy\'s Leave out list. Back up now runs it anyway.',
                { size: formatBytes(fit.estimate_bytes), free: formatBytes(fit.available_bytes) })}
            {fit.largest.length > 0 && (
                <>
                    <Typography variant="body2" sx={{ mt: 1 }}>{t('backups.firstFit.largest', 'Largest folders:')}</Typography>
                    {largestLines(fit).map(line => (
                        <Typography key={line} variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>{line}</Typography>
                    ))}
                </>
            )}
        </Alert>
    );
};
