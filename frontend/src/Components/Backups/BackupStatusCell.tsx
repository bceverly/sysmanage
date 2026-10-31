// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A Backups row's status (Phase 24): one chip and at most ONE line under it,
// the most important thing to know, with the long story in a tooltip.  The
// cell used to stack a chip, a reason, an error and two buttons (Bryan,
// 2026-10-31); the buttons are now the row's actions.

import React from 'react';
import { Chip, CircularProgress, LinearProgress, Stack, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { BackupHost } from '../../Services/backups';
import {
    formatBytes,
    heldNote,
    reachMessage,
    reasonLabel,
    statusColor,
    statusLabel,
    unreachable,
    unreadableOf,
} from './backupLabels';
import { blockerLabel, equipFailureLabel } from './EquipForBackup';
import { FirstFitCaption } from './BackupFirstFit';
import { VerificationCaption } from './VerificationStatus';

const ONE_LINE = { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 320 } as const;

/** A caption on one line; the full text (and more) on hover. */
const Line: React.FC<{ text: string; tip?: string; color: string; busy?: boolean }> = ({ text, tip, color, busy }) => (
    <Tooltip title={tip ?? text} placement="bottom-start">
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mt: 0.5 }}>
            {busy && <CircularProgress size={12} />}
            <Typography variant="caption" color={color} sx={ONE_LINE}>{text}</Typography>
        </Stack>
    </Tooltip>
);

const Progress: React.FC<{ row: BackupHost }> = ({ row }) => {
    const { t } = useTranslation();
    const progress = row.running?.progress;
    return (
        <Tooltip title={progress?.phase ?? ''}>
            <Stack spacing={0.5} sx={{ mt: 0.75, width: 220 }}>
                <LinearProgress />
                <Typography variant="caption" color="text.secondary" sx={ONE_LINE}>
                    {progress
                        ? t('backups.hosts.progress', '{{paths}} paths, {{size}} read', {
                              paths: progress.paths ?? 0,
                              size: formatBytes(progress.read_bytes ?? 0),
                          })
                        : t('backups.run.queued', 'Queued')}
                </Typography>
            </Stack>
        </Tooltip>
    );
};

/** The one line under a not-equipped host's chip: installing, the failed
 *  install, or what to do about it. */
const equipLine = (t: TFunction, row: BackupHost): React.ReactElement | null => {
    const equip = row.equip;
    if (equip?.status === 'running') {
        const text = equip.held
            ? t('backups.equip.held', "Waiting for this host's maintenance window to install restate")
            : t('backups.equip.running', 'Equipping: installing restate...');
        return <Line text={text} color="text.secondary" busy />;
    }
    const reason = row.reason ? reasonLabel(t, row.reason) : '';
    if (equip?.status === 'failed') {
        const failed = t('backups.equip.failed', 'Equip for backup failed: {{why}}', {
            why: equipFailureLabel(t, equip.reason),
        });
        return <Line text={equipFailureLabel(t, equip.reason)} color="error"
            tip={[failed, reason, equip.detail].filter(Boolean).join('\n')} />;
    }
    // When Equip cannot do it, say what will (build restate by hand, upgrade
    // the agent) rather than only what is missing.
    const blocked = blockerLabel(t, row.equip_blocker);
    if (blocked) return <Line text={blocked} tip={[reason, blocked].filter(Boolean).join('\n')} color="text.secondary" />;
    return reason ? <Line text={reason} color="warning.main" /> : null;
};

const detailLine = (t: TFunction, row: BackupHost): React.ReactElement | null => {
    if (row.running) return <Progress row={row} />;
    if (row.reach && unreachable(row)) {
        return <Line text={reasonLabel(t, 'storage_unreachable')} tip={reachMessage(t, row.reach)} color="warning.main" />;
    }
    if (!row.equipped) return equipLine(t, row);
    if (row.capture_requested) return <Line text={t('backups.hosts.waiting', 'Waiting for a free slot')} color="text.secondary" />;
    const held = heldNote(t, row);
    if (held) return <Line text={held} color="text.secondary" />;
    const skipped = unreadableOf(row.last_good_capture);
    if (skipped) {
        return <Line text={t('backups.hosts.unreadable', 'Files not read: {{n}}', { n: skipped.count })}
            tip={skipped.first.join('\n')} color="warning.main" />;
    }
    return null;
};

const BackupStatusCell: React.FC<{ row: BackupHost; storageHost: boolean }> = ({ row, storageHost }) => {
    const { t } = useTranslation();
    if (storageHost) {
        return <Chip size="small" variant="outlined" label={t('backups.target.storageHost', 'Storage host')} />;
    }
    const detail = detailLine(t, row);
    return (
        <>
            <Chip size="small" color={statusColor(row.status)} label={statusLabel(t, row.status)} />
            {detail ?? (
                // Nothing more urgent: the first-fit warning, else verification's.
                <Stack sx={{ '& > *': ONE_LINE }}>
                    {row.first_fit && !row.first_fit.fits
                        ? <FirstFitCaption fit={row.first_fit} />
                        : <VerificationCaption verification={row.verification} />}
                </Stack>
            )}
        </>
    );
};

export default BackupStatusCell;
