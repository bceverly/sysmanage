// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Every approved host's backup standing (Phase 24), worst first, with what
// an operator can do about it: one primary action per row and the rest in a
// "More" menu (BackupRowActions), the status as one chip and one line
// (BackupStatusCell), compact dates with the full time on hover.  The
// target's storage host is listed last, as such, with no host actions.

import React, { useEffect, useMemo, useState } from 'react';
import {
    Checkbox,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Tooltip,
    Typography,
} from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { BACKUP_STATUS_ORDER } from '../../Services/backups';
import type { BackupHost } from '../../Services/backups';
import BackupBulkBar from './BackupBulkBar';
import BackupPolicyDialog from './BackupPolicyDialog';
import RestoreFilesDialog from './RestoreFilesDialog';
import BackupRowActions from './BackupRowActions';
import BackupStatusCell from './BackupStatusCell';
import {
    coverageLabel,
    formatBytes,
    formatShortTime,
    formatTime,
    reachMessage,
    reasonLabel,
    unreachable,
} from './backupLabels';

const rank = (row: BackupHost) => BACKUP_STATUS_ORDER.indexOf(row.status);

/** A host the bulk "Back up now" can take: configured, idle, not waiting. */
export const canBackUp = (row: BackupHost): boolean =>
    row.equipped && !!row.policy?.configured && row.running?.action !== 'capture' && !row.capture_requested
    && !unreachable(row);

/** A host the bulk "Equip for backup" can take: the server offers it. */
export const canEquip = (row: BackupHost): boolean =>
    !row.equipped && row.equip_blocker === null && !unreachable(row);

/** A host the bulk "Set up backups" can take: equipped, with no policy. */
export const canSetUp = (row: BackupHost): boolean => row.equipped && !row.policy && !unreachable(row);

/** The target's storage host, with no backup policy of its own: it holds the
 *  backups, so it is not offered host actions. */
export const isStorageHost = (row: BackupHost, storageHostId: string | null | undefined): boolean =>
    !!storageHostId && row.host_id === storageHostId && !row.policy;

/** A host the bulk bar can act on at all. */
const canPick = (row: BackupHost): boolean => canBackUp(row) || canEquip(row) || canSetUp(row);

/** Why a host's checkbox is off, shown on hover: a disabled box with no
 *  reason looked broken (Bryan, 2026-10-29). */
export const pickBlocked = (t: TFunction, row: BackupHost): string | null => {
    if (canPick(row)) return null;
    if (row.reach && unreachable(row)) return reachMessage(t, row.reach);
    if (!row.equipped) {
        switch (row.equip_blocker) {
            case 'agent_outdated':
                return t('backups.equip.blockedAgent', 'Upgrade the agent to equip this host from here');
            case 'not_applicable':
                return t('backups.bulk.skipEquipPlatform', 'restate has no package the agent can install here');
            case 'in_progress':
                return t('backups.bulk.skipEquipping', 'Already equipping');
            default:
                return row.reason ? reasonLabel(t, row.reason) : null;
        }
    }
    if (row.running?.action === 'capture') return t('backups.bulk.skipRunning', 'Already backing up');
    if (row.capture_requested) return t('backups.hosts.waiting', 'Waiting for a free slot');
    if (row.policy && !row.policy.configured) {
        return t('backups.bulk.skipNotConfigured', 'Job files not confirmed by the host yet');
    }
    return null;
};

export const sortHosts = (rows: BackupHost[], storageHostId?: string | null): BackupHost[] =>
    [...rows].sort((a, b) =>
        Number(isStorageHost(a, storageHostId)) - Number(isStorageHost(b, storageHostId))
        || rank(a) - rank(b) || a.fqdn.localeCompare(b.fqdn));

const NOWRAP = { whiteSpace: 'nowrap' } as const;

/** A time in a table: short, with the full one on hover. */
const When: React.FC<{ iso: string | null | undefined }> = ({ iso }) => (
    <Tooltip title={iso ? formatTime(iso) : ''}>
        <span>{formatShortTime(iso)}</span>
    </Tooltip>
);

const HostCell: React.FC<{ row: BackupHost }> = ({ row }) => {
    const { t } = useTranslation();
    return (
        <TableCell sx={{ maxWidth: 280 }}>
            <Stack direction="row" spacing={0.5} alignItems="center">
                <Tooltip title={row.fqdn}>
                    <Typography variant="body2" noWrap>{row.fqdn}</Typography>
                </Tooltip>
                {row.coverage !== 'full' && (
                    // Only the exception is shown: full coverage is the norm.
                    <Tooltip title={coverageLabel(t, row.coverage)}>
                        <InfoOutlinedIcon fontSize="inherit" color="warning" titleAccess={coverageLabel(t, row.coverage)} />
                    </Tooltip>
                )}
            </Stack>
            {row.policy?.restate_version && (
                <Typography variant="caption" color="text.secondary" sx={NOWRAP}>
                    {t('backups.hosts.restateVersion', 'restate {{version}}', { version: row.policy.restate_version })}
                </Typography>
            )}
        </TableCell>
    );
};

const BackupHostsTable: React.FC<{
    rows: BackupHost[];
    hasTarget: boolean;
    storageHostId?: string | null;
    canManage: boolean;
    canRestore: boolean;
    onChanged: () => void;
    onError: (message: string) => void;
    onNotice?: (message: string) => void;
}> = ({ rows, hasTarget, storageHostId, canManage, canRestore, onChanged, onError, onNotice }) => {
    const { t } = useTranslation();
    const [editing, setEditing] = useState<BackupHost | null>(null);
    const [restoring, setRestoring] = useState<BackupHost | null>(null);
    const [picked, setPicked] = useState<Set<string>>(new Set());
    const pickable = useMemo(
        () => rows.filter(r => canPick(r) && !isStorageHost(r, storageHostId)).map(r => r.host_id),
        [rows, storageHostId],
    );
    // A refresh drops picks that can no longer back up (started, say).
    useEffect(() => {
        const still = new Set(pickable);
        setPicked(prev => {
            const kept = Array.from(prev).filter(id => still.has(id));
            return kept.length === prev.size ? prev : new Set(kept);
        });
    }, [pickable]);
    const allPicked = pickable.length > 0 && pickable.every(id => picked.has(id));
    const toggle = (id: string) =>
        setPicked(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });

    return (
        <>
            {canManage && (
                <BackupBulkBar selected={Array.from(picked)} rows={rows} onClear={() => setPicked(new Set())} onDone={onChanged} />
            )}
            <Table size="small" sx={{ '& td, & th': { verticalAlign: 'middle' } }}>
                <TableHead>
                    <TableRow>
                        {canManage && (
                            <TableCell padding="checkbox">
                                <Checkbox size="small" checked={allPicked}
                                    indeterminate={picked.size > 0 && !allPicked} disabled={pickable.length === 0}
                                    onChange={() => setPicked(allPicked ? new Set() : new Set(pickable))}
                                    slotProps={{ input: { 'aria-label': t('backups.bulk.selectAllActionable', 'Select every host that can be backed up or equipped now') } }} />
                            </TableCell>
                        )}
                        <TableCell>{t('backups.hosts.host', 'Host')}</TableCell>
                        <TableCell sx={{ width: 260 }}>{t('backups.hosts.status', 'Status')}</TableCell>
                        <TableCell sx={NOWRAP}>{t('backups.hosts.lastBackup', 'Last backup')}</TableCell>
                        <TableCell sx={NOWRAP}>{t('backups.hosts.nextDue', 'Next due')}</TableCell>
                        <TableCell sx={NOWRAP}>{t('backups.hosts.size', 'Repository')}</TableCell>
                        <TableCell align="right" sx={{ ...NOWRAP, width: 200 }}>{t('backups.hosts.actions', 'Actions')}</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {sortHosts(rows, storageHostId).map(row => {
                        const storage = isStorageHost(row, storageHostId);
                        return (
                            <TableRow key={row.host_id} selected={picked.has(row.host_id)}>
                                {canManage && (
                                    <TableCell padding="checkbox">
                                        <Tooltip title={storage ? t('backups.target.storageHost', 'Storage host') : pickBlocked(t, row) ?? ''}>
                                            {/* a span: a disabled control takes no hover */}
                                            <span>
                                                <Checkbox size="small" checked={picked.has(row.host_id)}
                                                    disabled={storage || !canPick(row)} onChange={() => toggle(row.host_id)}
                                                    slotProps={{ input: { 'aria-label': t('backups.bulk.selectHost', 'Select {{host}}', { host: row.fqdn }) } }} />
                                            </span>
                                        </Tooltip>
                                    </TableCell>
                                )}
                                <HostCell row={row} />
                                <TableCell><BackupStatusCell row={row} storageHost={storage} /></TableCell>
                                <TableCell sx={NOWRAP}>
                                    <When iso={row.last_good_capture?.finished_at} />
                                    {row.snapshot_count > 0 && (
                                        <Typography variant="caption" display="block" color="text.secondary">
                                            {t('backups.hosts.snapshots', 'Snapshots: {{n}}', { n: row.snapshot_count })}
                                        </Typography>
                                    )}
                                </TableCell>
                                <TableCell sx={NOWRAP}>
                                    {row.running?.action === 'capture'
                                        ? t('backups.run.running', 'Running')
                                        : <When iso={row.next_due} />}
                                </TableCell>
                                <TableCell sx={NOWRAP}>{formatBytes(row.policy?.repository_bytes)}</TableCell>
                                <TableCell align="right">
                                    <BackupRowActions row={row}
                                        ctx={{ canManage, canRestore, hasTarget, storageHost: storage }}
                                        onConfigure={setEditing} onRestore={setRestoring}
                                        onChanged={onChanged} onError={onError} onNotice={onNotice ?? (() => undefined)} />
                                </TableCell>
                            </TableRow>
                        );
                    })}
                </TableBody>
            </Table>
            {editing && (
                <BackupPolicyDialog open hostId={editing.host_id} fqdn={editing.fqdn} policy={editing.policy}
                    onClose={() => setEditing(null)} onSaved={onChanged} />
            )}
            {restoring && (
                <RestoreFilesDialog open hostId={restoring.host_id} fqdn={restoring.fqdn}
                    canBrowse={!!restoring.policy?.abilities?.includes('list')}
                    onClose={() => setRestoring(null)} />
            )}
        </>
    );
};

export default BackupHostsTable;
