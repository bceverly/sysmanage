// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * A host moving to another target with its backups (ROADMAP 27.3): its
 * repository is copied to the new target, checked there, and only then does
 * the host switch.  Until the switch it backs up where it is, and the move
 * can be canceled.  After it, the old repository is kept as it is for a
 * while (14 days, or the old target's seal retention when longer).
 */

import React, { useState } from 'react';
import { Alert, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { cancelMove } from '../../Services/backups';
import type { BackupMove } from '../../Services/backups';
import { apiDetail, formatTime } from './backupLabels';

const MOVING = ['copying', 'verifying'];

export const HostMove: React.FC<{
    move?: BackupMove | null;
    canManage: boolean;
    onChanged: () => void;
}> = ({ move, canManage, onChanged }) => {
    const { t } = useTranslation();
    const [error, setError] = useState<string | null>(null);
    if (!move) return null;
    const target = move.target ?? '?';
    const cancel = async () => {
        setError(null);
        try {
            await cancelMove(move.id);
            onChanged();
        } catch (err) {
            setError(apiDetail(err, t('backups.move.cancelError', 'The move could not be canceled.')));
        }
    };
    if (move.status === 'failed') {
        return (
            <Alert severity="warning" sx={{ my: 0.5 }} data-testid="host-move">
                {t('backups.move.failed', 'The move to {{target}} stopped: {{error}}. This host still backs up to {{from}}.',
                    { target, error: move.error ?? '?', from: move.from_target ?? '?' })}
            </Alert>
        );
    }
    if (move.status === 'switched') {
        return (
            <Typography variant="body2" data-testid="host-move">
                {move.keep_until
                    ? t('backups.move.kept', 'Moved from {{from}}; its old repository there is kept until {{date}}.',
                        { from: move.from_target ?? '?', date: formatTime(move.keep_until) })
                    : t('backups.move.keptForGood', 'Moved from {{from}}; its old repository there is kept.',
                        { from: move.from_target ?? '?' })}
            </Typography>
        );
    }
    const copied = Math.max(0, move.total - move.behind);
    return (
        <>
            <Typography variant="body2" data-testid="host-move">
                {move.status === 'verifying'
                    ? t('backups.move.checking', 'Moving to {{target}}: checking the copy', { target })
                    : t('backups.move.copying', 'Moving to {{target}}: snapshots copied {{copied}} of {{total}}',
                        { target, copied, total: move.total })}
                {canManage && MOVING.includes(move.status) && (
                    <Button size="small" sx={{ ml: 1 }} onClick={() => void cancel()}>
                        {t('backups.move.cancel', 'Cancel move')}
                    </Button>
                )}
            </Typography>
            {move.error && (
                <Alert severity="warning" sx={{ my: 0.5 }}>
                    {t('backups.move.copyError', 'The last copy did not finish: {{error}}', { error: move.error })}
                </Alert>
            )}
            {error && <Alert severity="error" sx={{ my: 0.5 }}>{error}</Alert>}
        </>
    );
};
