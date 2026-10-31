// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A Backups row's actions (Phase 24): ONE primary button chosen by the
// host's state, the same size on every row, and the rest in a "More" menu.
// Rows had grown three differently styled buttons that wrapped ("CONFIGU
// RE"), with Equip and Check again stacked in the status cell (Bryan,
// 2026-10-31: "the ux is getting really crappy").

import React, { useEffect, useRef, useState } from 'react';
import { Button, IconButton, Menu, MenuItem, Stack, Tooltip } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { backupNow, checkBackupReach, equipBackup, recheckBackup } from '../../Services/backups';
import type { BackupHost } from '../../Services/backups';
import { apiDetail, reachMessage, unreachable } from './backupLabels';

export type HostAction = 'reach' | 'equip' | 'recheck' | 'configure' | 'backupNow' | 'restore';

export interface ActionContext {
    canManage: boolean;
    canRestore: boolean;
    hasTarget: boolean;
    /** The target's storage host, shown without host actions. */
    storageHost: boolean;
}

// After a good install, how long the agent's confirmation may take before
// Equip is offered again (Check again is always there).
const CONFIRM_WINDOW_MS = 5 * 60 * 1000;

/** Equip for backup is offered: the server allows it, nothing is installing,
 *  and no install just finished waiting for the agent to confirm. */
export const equipOffered = (row: BackupHost, now = Date.now()): boolean => {
    if (row.equipped || row.equip_blocker !== null || row.equip?.status === 'running') return false;
    const installed = row.equip?.status === 'ok'
        && now - Date.parse(row.equip.finished_at ?? '') < CONFIRM_WINDOW_MS;
    return !installed;
};

/** What an operator who manages backups may do here, in display order. */
const manageActions = (row: BackupHost, hasTarget: boolean): HostAction[] => {
    const offered: HostAction[] = [];
    if (unreachable(row)) offered.push('reach');
    if (!row.equipped) {
        if (equipOffered(row)) offered.push('equip');
        offered.push('recheck');
    }
    if (hasTarget) offered.push('configure');
    if (row.policy) offered.push('backupNow');
    return offered;
};

/** The action a ready host leads with: Back up now once it has a policy,
 *  Configure before.  None for an unreachable or unequipped host, which keeps
 *  its first action (Check again, Equip for backup). */
const leadAction = (row: BackupHost): HostAction | undefined => {
    if (unreachable(row) || !row.equipped) return undefined;
    return row.policy ? 'backupNow' : 'configure';
};

/** Every action this row offers, the primary one first. */
export const hostActions = (row: BackupHost, ctx: ActionContext): HostAction[] => {
    if (ctx.storageHost) return [];
    const all = ctx.canManage ? manageActions(row, ctx.hasTarget) : [];
    if (ctx.canRestore && row.snapshot_count > 0) all.push('restore');
    const lead = leadAction(row);
    return lead && all.includes(lead) ? [lead, ...all.filter(a => a !== lead)] : all;
};

/** Why an action is off right now, or null when it can run. */
export const actionBlocked = (t: TFunction, row: BackupHost, action: HostAction): string | null => {
    if (action === 'reach' || action === 'recheck') return null;
    if (row.reach && unreachable(row)) return reachMessage(t, row.reach);
    if (action !== 'backupNow') return null;
    if (row.running?.action === 'capture') return t('backups.bulk.skipRunning', 'Already backing up');
    if (!row.equipped || !row.policy?.configured) {
        return t('backups.bulk.skipNotConfigured', 'Job files not confirmed by the host yet');
    }
    return null;
};

const label = (t: TFunction, action: HostAction): string => {
    switch (action) {
        case 'reach':
        case 'recheck':
            return t('backups.equip.recheck', 'Check again');
        case 'equip':
            return t('backups.equip.button', 'Equip for backup');
        case 'configure':
            return t('backups.hosts.configure', 'Configure');
        case 'backupNow':
            return t('backups.hosts.backupNow', 'Back up now');
        default:
            return t('backups.hosts.restore', 'Restore files');
    }
};

// How long the agent usually takes to answer a check before the view re-reads.
const RECHECK_WAIT_MS = 5000;

const BackupRowActions: React.FC<{
    row: BackupHost;
    ctx: ActionContext;
    onConfigure: (row: BackupHost) => void;
    onRestore: (row: BackupHost) => void;
    onChanged: () => void;
    onError: (message: string) => void;
    onNotice: (message: string) => void;
}> = ({ row, ctx, onConfigure, onRestore, onChanged, onError, onNotice }) => {
    const { t } = useTranslation();
    const [busy, setBusy] = useState(false);
    const [anchor, setAnchor] = useState<HTMLElement | null>(null);
    const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
    const actions = hostActions(row, ctx);
    if (actions.length === 0) return null;
    const [primary, ...more] = actions;

    const call = async (request: () => Promise<unknown>, notice: string | null, failed: string, wait = 0) => {
        setBusy(true);
        try {
            await request();
            if (notice) onNotice(notice);
            if (timer.current) clearTimeout(timer.current);
            timer.current = setTimeout(() => {
                setBusy(false);
                onChanged();
            }, wait);
        } catch (err) {
            onError(apiDetail(err, failed));
            setBusy(false);
        }
    };

    const run = (action: HostAction) => {
        setAnchor(null);
        switch (action) {
            case 'configure':
                onConfigure(row);
                return;
            case 'restore':
                onRestore(row);
                return;
            case 'backupNow':
                void call(() => backupNow(row.host_id), null,
                    t('backups.hosts.backupNowError', 'The backup could not be started.'));
                return;
            case 'equip':
                void call(() => equipBackup(row.host_id),
                    t('backups.equip.started', 'Installing restate; this can take a few minutes.'),
                    t('backups.equip.error', 'Equip for backup could not be started.'));
                return;
            case 'recheck':
                void call(() => recheckBackup(row.host_id),
                    t('backups.equip.checking', 'Asked the agent; the status updates in a few seconds.'),
                    t('backups.equip.recheckError', 'The check could not be requested.'), RECHECK_WAIT_MS);
                return;
            default:
                void call(() => checkBackupReach(row.host_id),
                    t('backups.equip.checking', 'Asked the agent; the status updates in a few seconds.'),
                    t('backups.equip.recheckError', 'The check could not be requested.'), RECHECK_WAIT_MS);
        }
    };

    const primaryBlocked = actionBlocked(t, row, primary);
    return (
        <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
            <Tooltip title={primaryBlocked ?? ''}>
                {/* a span: a disabled button takes no hover */}
                <span>
                    <Button size="small" variant="outlined" disabled={busy || primaryBlocked !== null}
                        onClick={() => run(primary)}
                        sx={{ whiteSpace: 'nowrap', minWidth: 150 }}>
                        {label(t, primary)}
                    </Button>
                </span>
            </Tooltip>
            {more.length > 0 ? (
                <>
                    <IconButton size="small" onClick={e => setAnchor(e.currentTarget)}
                        aria-label={`${t('common.moreActions', 'More')}: ${row.fqdn}`}
                        aria-haspopup="true" aria-expanded={anchor !== null}>
                        <MoreVertIcon fontSize="small" />
                    </IconButton>
                    <Menu anchorEl={anchor} open={anchor !== null} onClose={() => setAnchor(null)}>
                        {more.map(action => {
                            const blocked = actionBlocked(t, row, action);
                            return (
                                <MenuItem key={action} disabled={busy || blocked !== null} onClick={() => run(action)}
                                    title={blocked ?? undefined}>
                                    {label(t, action)}
                                </MenuItem>
                            );
                        })}
                    </Menu>
                </>
            ) : (
                // Keeps the primary buttons aligned with the rows that have a menu.
                <span style={{ width: 34, display: 'inline-block' }} />
            )}
        </Stack>
    );
};

export default BackupRowActions;
