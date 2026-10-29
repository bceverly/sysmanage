// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Every approved host's backup standing (Phase 24), worst first, with what
// an operator can do about it: configure, back up now (one host, or the
// picked ones through the bulk bar), restore files.

import React, { useEffect, useMemo, useState } from 'react';
import {
    Button,
    Checkbox,
    Chip,
    LinearProgress,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Tooltip,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import AsyncButton from '../AsyncButton';
import { backupNow, BACKUP_STATUS_ORDER } from '../../Services/backups';
import type { BackupHost } from '../../Services/backups';
import BackupBulkBar from './BackupBulkBar';
import BackupPolicyDialog from './BackupPolicyDialog';
import RestoreFilesDialog from './RestoreFilesDialog';
import {
    apiDetail,
    coverageLabel,
    formatBytes,
    formatTime,
    heldNote,
    reasonLabel,
    statusColor,
    statusLabel,
    unreadableOf,
} from './backupLabels';
import EquipForBackup from './EquipForBackup';
import { FirstFitCaption } from './BackupFirstFit';
import { VerificationCaption } from './VerificationStatus';

const rank = (row: BackupHost) => BACKUP_STATUS_ORDER.indexOf(row.status);

/** A host the bulk "Back up now" can take: configured, idle, not waiting. */
export const canBackUp = (row: BackupHost): boolean =>
    row.equipped && !!row.policy?.configured && row.running?.action !== 'capture' && !row.capture_requested;

/** A host the bulk "Equip for backup" can take: the server offers it. */
export const canEquip = (row: BackupHost): boolean => !row.equipped && row.equip_blocker === null;

/** A host the bulk "Set up backups" can take: equipped, with no policy. */
export const canSetUp = (row: BackupHost): boolean => row.equipped && !row.policy;

/** A host the bulk bar can act on at all. */
const canPick = (row: BackupHost): boolean => canBackUp(row) || canEquip(row) || canSetUp(row);

/** Why a host's checkbox is off, shown on hover: a disabled box with no
 *  reason looked broken (Bryan, 2026-10-29). */
export const pickBlocked = (t: TFunction, row: BackupHost): string | null => {
    if (canPick(row)) return null;
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

export const sortHosts = (rows: BackupHost[]): BackupHost[] =>
    [...rows].sort((a, b) => rank(a) - rank(b) || a.fqdn.localeCompare(b.fqdn));

const Progress: React.FC<{ row: BackupHost }> = ({ row }) => {
    const { t } = useTranslation();
    const progress = row.running?.progress;
    if (!row.running) return null;
    return (
        <Tooltip title={progress?.phase ?? ''}>
            <Stack spacing={0.5} sx={{ mt: 0.5, minWidth: 140 }}>
                <LinearProgress />
                <Typography variant="caption" color="text.secondary">
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

// Files the last backup skipped because it could not read them; the first
// ones in the tooltip, so "Incomplete" says what is missing.
const Unreadable: React.FC<{ row: BackupHost }> = ({ row }) => {
    const { t } = useTranslation();
    const skipped = unreadableOf(row.last_good_capture);
    if (!skipped) return null;
    return (
        <Tooltip title={skipped.first.join('\n')} placement="bottom-start">
            <Typography variant="caption" display="block" color="warning.main" sx={{ whiteSpace: 'pre-line' }}>
                {t('backups.hosts.unreadable', 'Files not read: {{n}}', { n: skipped.count })}
            </Typography>
        </Tooltip>
    );
};

const StatusCell: React.FC<{ row: BackupHost; canManage: boolean; onChanged: () => void }> = ({
    row,
    canManage,
    onChanged,
}) => {
    const { t } = useTranslation();
    return (
        <TableCell>
            <Chip size="small" color={statusColor(row.status)} label={statusLabel(t, row.status)} />
            {!row.equipped && row.reason && (
                <>
                    <Typography variant="caption" display="block" color="warning.main">
                        {reasonLabel(t, row.reason)}
                    </Typography>
                    <EquipForBackup hostId={row.host_id} equip={row.equip} blocker={row.equip_blocker}
                        canManage={canManage} onChanged={onChanged} />
                </>
            )}
            <Progress row={row} />
            <Unreadable row={row} />
            <FirstFitCaption fit={row.first_fit} />
            <VerificationCaption verification={row.verification} />
            {heldNote(t, row) && (
                <Typography variant="caption" display="block" color="text.secondary">
                    {heldNote(t, row)}
                </Typography>
            )}
            {row.capture_requested && !row.running && (
                <Typography variant="caption" display="block" color="text.secondary">
                    {t('backups.hosts.waiting', 'Waiting for a free slot')}
                </Typography>
            )}
        </TableCell>
    );
};

const BackupHostsTable: React.FC<{
    rows: BackupHost[];
    hasTarget: boolean;
    canManage: boolean;
    canRestore: boolean;
    onChanged: () => void;
    onError: (message: string) => void;
}> = ({ rows, hasTarget, canManage, canRestore, onChanged, onError }) => {
    const { t } = useTranslation();
    const [editing, setEditing] = useState<BackupHost | null>(null);
    const [restoring, setRestoring] = useState<BackupHost | null>(null);
    const [picked, setPicked] = useState<Set<string>>(new Set());
    const pickable = useMemo(() => rows.filter(canPick).map(r => r.host_id), [rows]);
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

    const runNow = async (row: BackupHost) => {
        try {
            await backupNow(row.host_id);
            onChanged();
        } catch (err) {
            onError(apiDetail(err, t('backups.hosts.backupNowError', 'The backup could not be started.')));
        }
    };

    return (
        <>
            {canManage && (
                <BackupBulkBar selected={Array.from(picked)} rows={rows} onClear={() => setPicked(new Set())} onDone={onChanged} />
            )}
            <Table size="small">
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
                        <TableCell>{t('backups.hosts.status', 'Status')}</TableCell>
                        <TableCell>{t('backups.hosts.lastBackup', 'Last backup')}</TableCell>
                        <TableCell>{t('backups.hosts.nextDue', 'Next due')}</TableCell>
                        <TableCell>{t('backups.hosts.size', 'Repository')}</TableCell>
                        <TableCell>{t('backups.hosts.coverage', 'Coverage')}</TableCell>
                        <TableCell align="right">{t('backups.hosts.actions', 'Actions')}</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {sortHosts(rows).map(row => (
                        <TableRow key={row.host_id} selected={picked.has(row.host_id)}>
                            {canManage && (
                                <TableCell padding="checkbox">
                                    <Tooltip title={pickBlocked(t, row) ?? ''}>
                                        {/* a span: a disabled control takes no hover */}
                                        <span>
                                            <Checkbox size="small" checked={picked.has(row.host_id)}
                                                disabled={!canPick(row)} onChange={() => toggle(row.host_id)}
                                                slotProps={{ input: { 'aria-label': t('backups.bulk.selectHost', 'Select {{host}}', { host: row.fqdn }) } }} />
                                        </span>
                                    </Tooltip>
                                </TableCell>
                            )}
                            <TableCell>
                                <Typography variant="body2">{row.fqdn}</Typography>
                                {row.policy?.restate_version && (
                                    <Typography variant="caption" color="text.secondary">
                                        {t('backups.hosts.restateVersion', 'restate {{version}}', {
                                            version: row.policy.restate_version,
                                        })}
                                    </Typography>
                                )}
                            </TableCell>
                            <StatusCell row={row} canManage={canManage} onChanged={onChanged} />
                            <TableCell>
                                {formatTime(row.last_good_capture?.finished_at)}
                                {row.snapshot_count > 0 && (
                                    <Typography variant="caption" display="block" color="text.secondary">
                                        {t('backups.hosts.snapshots', 'Snapshots: {{n}}', { n: row.snapshot_count })}
                                    </Typography>
                                )}
                            </TableCell>
                            <TableCell>{formatTime(row.next_due)}</TableCell>
                            <TableCell>{formatBytes(row.policy?.repository_bytes)}</TableCell>
                            <TableCell>{coverageLabel(t, row.coverage)}</TableCell>
                            <TableCell align="right">
                                <Stack direction="row" spacing={1} justifyContent="flex-end">
                                    {canManage && hasTarget && (
                                        <Button size="small" onClick={() => setEditing(row)}>
                                            {t('backups.hosts.configure', 'Configure')}
                                        </Button>
                                    )}
                                    {canManage && row.policy && (
                                        <AsyncButton size="small" variant="outlined"
                                            disabled={!row.equipped || !row.policy.configured || row.running?.action === 'capture'}
                                            onClick={() => runNow(row)}
                                            busyLabel={t('backups.hosts.starting', 'Starting...')}>
                                            {t('backups.hosts.backupNow', 'Back up now')}
                                        </AsyncButton>
                                    )}
                                    {canRestore && row.snapshot_count > 0 && (
                                        <Button size="small" onClick={() => setRestoring(row)}>
                                            {t('backups.hosts.restore', 'Restore files')}
                                        </Button>
                                    )}
                                </Stack>
                            </TableCell>
                        </TableRow>
                    ))}
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
