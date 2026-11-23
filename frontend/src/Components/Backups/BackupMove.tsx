// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * A host moving to another target with its backups (ROADMAP 27.3): its
 * repository is copied to the new target, checked there, and only then does
 * the host switch.  Until the switch it backs up where it is, and the move
 * can be canceled.  After it, the old repository is kept as it is for a
 * while (14 days, or the old target's seal retention when longer), then the
 * old storage host removes it; a manager can remove it sooner or keep it.
 */

import React, { useState } from 'react';
import { Alert, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { cancelMove, keepOldRepository, removeOldRepository } from '../../Services/backups';
import type { BackupMove } from '../../Services/backups';
import { apiDetail, formatTime } from './backupLabels';

const MOVING = new Set(['copying', 'verifying']);

const OldRepository: React.FC<{
    move: BackupMove;
    canManage: boolean;
    onChanged: () => void;
}> = ({ move, canManage, onChanged }) => {
    const { t } = useTranslation();
    const [error, setError] = useState<string | null>(null);
    const from = move.from_target ?? '?';
    const act = async (call: (id: string) => Promise<void>, fallback: string) => {
        setError(null);
        try {
            await call(move.id);
            onChanged();
        } catch (err) {
            setError(apiDetail(err, fallback));
        }
    };
    if (move.status === 'retiring') {
        return (
            <Typography variant="body2" data-testid="host-move">
                {t('backups.move.removing', 'Moved from {{from}}; removing its old repository there.', { from })}
            </Typography>
        );
    }
    return (
        <>
            <Typography variant="body2" data-testid="host-move">
                {move.keep_until
                    ? t('backups.move.kept', 'Moved from {{from}}; its old repository there is kept until {{date}}.',
                        { from, date: formatTime(move.keep_until) })
                    : t('backups.move.keptForGood', 'Moved from {{from}}; its old repository there is kept.', { from })}
                {canManage && !move.removable_from && (
                    <Button size="small" sx={{ ml: 1 }} onClick={() => void act(removeOldRepository,
                        t('backups.move.removeError', 'The old repository could not be removed.'))}>
                        {t('backups.move.removeNow', 'Remove now')}
                    </Button>
                )}
                {canManage && move.keep_until && (
                    <Button size="small" sx={{ ml: 1 }} onClick={() => void act(keepOldRepository,
                        t('backups.move.keepError', 'The old repository could not be kept.'))}>
                        {t('backups.move.keep', 'Keep')}
                    </Button>
                )}
            </Typography>
            {move.removable_from && (
                <Typography variant="body2" color="text.secondary">
                    {t('backups.move.sealed', 'The old target seals its backups, so the old repository can be removed from {{date}}.',
                        { date: formatTime(move.removable_from) })}
                </Typography>
            )}
            {move.error && (
                <Alert severity="warning" sx={{ my: 0.5 }}>
                    {t('backups.move.removeFailed', 'The old repository was not removed: {{error}}. It is tried again later.',
                        { error: move.error })}
                </Alert>
            )}
            {error && <Alert severity="error" sx={{ my: 0.5 }}>{error}</Alert>}
        </>
    );
};

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
    if (move.status === 'switched' || move.status === 'retiring') {
        return <OldRepository move={move} canManage={canManage} onChanged={onChanged} />;
    }
    const copied = Math.max(0, move.total - move.behind);
    return (
        <>
            <Typography variant="body2" data-testid="host-move">
                {move.status === 'verifying'
                    ? t('backups.move.checking', 'Moving to {{target}}: checking the copy', { target })
                    : t('backups.move.copying', 'Moving to {{target}}: snapshots copied {{copied}} of {{total}}',
                        { target, copied, total: move.total })}
                {canManage && MOVING.has(move.status) && (
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
