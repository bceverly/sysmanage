// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// What an operator can do about "Not equipped" (ROADMAP Phase 24).
//
// "Equip for backup" has the host's agent install restate where it is
// packaged for a host the agent backs up (Ubuntu's PPA, FreeBSD's release
// package); the agent decides how.  The row shows "Equipping" until it
// answers (or that it waits for the host's maintenance window), and the
// reason when it failed.
//
// "Check again" asks the agent for a fresh capability report: it reported
// whether it can run restate only when it registered, so restate installed
// by hand left the host "not equipped" until its agent restarted
// (production, 2026-10-25).

import React, { useEffect, useRef, useState } from 'react';
import { Button, CircularProgress, Stack, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { equipBackup, recheckBackup } from '../../Services/backups';
import type { BackupEquipState } from '../../Services/backups';
import { useVisiblePolling } from '../../hooks/useVisiblePolling';
import { apiDetail } from './backupLabels';

// How long the agent usually takes to answer "Check again" before the view
// re-reads, and how often the view re-reads while equipping.
const RECHECK_WAIT_MS = 4000;
const EQUIPPING_POLL_MS = 10000;
// After a good install, how long to wait for the agent's confirmation before
// treating the host as needing a look (Check again is always there).
const CONFIRM_WINDOW_MS = 5 * 60 * 1000;

/** Why an Equip for backup failed, as something to act on. */
export const equipFailureLabel = (t: TFunction, reason: string | null): string => {
    switch (reason) {
        case 'unsupported':
            return t('backups.equip.failUnsupported', 'restate has no package the agent can install on this system');
        case 'no_release':
            return t('backups.equip.failNoRelease', 'restate has no package for this release of the operating system');
        case 'download_failed':
            return t('backups.equip.failDownload', 'The package could not be downloaded');
        case 'checksum_mismatch':
            return t('backups.equip.failChecksum', 'The downloaded package did not match its published checksum, so it was not installed');
        case 'no_answer':
            return t('backups.equip.failNoAnswer', 'The agent did not answer within an hour');
        default:
            return t('backups.equip.failInstall', 'The install did not finish');
    }
};

/** Why Equip for backup is not offered, when that is worth saying. */
const blockerLabel = (t: TFunction, blocker: string | null | undefined): string | null => {
    switch (blocker) {
        case 'agent_outdated':
            return t('backups.equip.blockedAgent', 'Upgrade the agent to equip this host from here');
        case 'not_applicable':
            return t('backups.equip.blockedPlatform', 'Install restate by hand on this system (build it from source)');
        default:
            return null;
    }
};

const EquipForBackup: React.FC<{
    hostId: string;
    equip: BackupEquipState | null | undefined;
    blocker: string | null | undefined;
    canManage: boolean;
    onChanged: () => void;
}> = ({ hostId, equip, blocker, canManage, onChanged }) => {
    const { t } = useTranslation();
    const [busy, setBusy] = useState(false);
    const [note, setNote] = useState<string | null>(null);
    const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    const equipping = equip?.status === 'running';
    // Installed, but the agent's fresh capability report (asked for at once)
    // has not landed yet: wait for it rather than offer Equip again.
    const installed =
        equip?.status === 'ok' &&
        Date.now() - Date.parse(equip.finished_at ?? '') < CONFIRM_WINDOW_MS;

    useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
    // While the agent installs, re-read so "Equipping" turns into the result.
    useVisiblePolling(onChanged, EQUIPPING_POLL_MS, equipping || installed);

    if (!canManage) return null;

    const act = async (call: () => Promise<unknown>, waiting: string, failed: string, wait = 0) => {
        setBusy(true);
        setNote(null);
        try {
            await call();
            setNote(waiting);
            timer.current = setTimeout(() => {
                setBusy(false);
                onChanged();
            }, wait);
        } catch (err) {
            setNote(apiDetail(err, failed));
            setBusy(false);
        }
    };

    const equipNow = () => act(
        () => equipBackup(hostId),
        t('backups.equip.started', 'Installing restate; this can take a few minutes.'),
        t('backups.equip.error', 'Equip for backup could not be started.'),
    );
    const recheck = () => act(
        () => recheckBackup(hostId),
        t('backups.equip.checking', 'Asked the agent; the status updates in a few seconds.'),
        t('backups.equip.recheckError', 'The check could not be requested.'),
        RECHECK_WAIT_MS,
    );
    const blocked = blockerLabel(t, blocker);

    return (
        <Stack spacing={0.5} sx={{ mt: 0.5 }}>
            {equipping && (
                <Stack direction="row" spacing={1} alignItems="center">
                    <CircularProgress size={14} />
                    <Typography variant="caption">
                        {equip?.held
                            ? t('backups.equip.held', "Waiting for this host's maintenance window to install restate")
                            : t('backups.equip.running', 'Equipping: installing restate...')}
                    </Typography>
                </Stack>
            )}
            {installed && (
                <Typography variant="caption" color="text.secondary">
                    {t('backups.equip.installed', 'restate installed; waiting for the agent to confirm.')}
                </Typography>
            )}
            {equip?.status === 'failed' && (
                <Tooltip title={equip.detail ?? ''} placement="bottom-start">
                    <Typography variant="caption" color="error">
                        {t('backups.equip.failed', 'Equip for backup failed: {{why}}', { why: equipFailureLabel(t, equip.reason) })}
                    </Typography>
                </Tooltip>
            )}
            {blocked && <Typography variant="caption" color="text.secondary">{blocked}</Typography>}
            <Stack direction="row" spacing={1} alignItems="center">
                {blocker === null && !installed && (
                    <Button size="small" variant="contained" disabled={busy} onClick={() => void equipNow()}>
                        {t('backups.equip.button', 'Equip for backup')}
                    </Button>
                )}
                {!equipping && (
                    <Button size="small" variant="outlined" disabled={busy} onClick={() => void recheck()}>
                        {t('backups.equip.recheck', 'Check again')}
                    </Button>
                )}
            </Stack>
            {note && <Typography variant="caption" color="text.secondary">{note}</Typography>}
        </Stack>
    );
};

export default EquipForBackup;
