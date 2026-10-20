// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The storage side of the backup target (Phase 24.4, 24.5, 24.8): its
// warnings, worst first, and -- when the storage host can run restate -- its
// job files, last seal/prune/check and filesystem.  Hosts only append; if
// nothing seals, prunes or checks on the storage side the repositories just
// grow, so that is never quiet.

import React from 'react';
import { Alert, Box, Stack, Typography } from '@mui/material';
import type { AlertColor } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type {
    BackupHost,
    BackupRun,
    BackupTarget,
    StorageRunBrief,
    TargetWarning,
} from '../../Services/backups';
import { formatTime, reasonLabel, runStatusLabel } from './backupLabels';

export const warningSeverity = (warning: TargetWarning): AlertColor => {
    switch (warning) {
        case 'no_storage_host':
        case 'storage_not_equipped':
        case 'seal_fs_mismatch':
        case 'btrfs_not_subvolume':
            return 'error';
        case 'fs_cannot_snapshot':
        case 'fs_unchecked':
            return 'info';
        default:
            return 'warning';
    }
};

const SEAL_FILESYSTEM: Record<string, string> = { zfs_snapshot: 'ZFS', btrfs_snapshot: 'btrfs' };

const staleHosts = (target: BackupTarget, hosts: BackupHost[], code: TargetWarning): string => {
    const ids = target.storage_status?.stale[code as 'seal_stale'] ?? [];
    const names = new Map(hosts.map(h => [h.host_id, h.fqdn]));
    return ids.map(id => names.get(id) ?? id).join(', ');
};

const warningText = (
    t: TFunction,
    target: BackupTarget,
    hosts: BackupHost[],
    warning: TargetWarning,
): React.ReactNode => {
    const fsType = target.storage_fs.type ?? '';
    switch (warning) {
        case 'no_storage_host':
            return t('backups.warning.noStorageHost',
                'No storage host: backups are never sealed, pruned or checked, and the repositories keep growing.');
        case 'storage_not_equipped':
            return t('backups.warning.storageNotEquipped',
                'The storage host cannot run backup jobs ({{reason}}), so storage jobs cannot run: nothing is sealed, pruned or checked.',
                { reason: reasonLabel(t, target.storage_reason) });
        case 'seal_fs_mismatch':
            return t('backups.warning.sealFsMismatch',
                'The seal mode needs {{needed}}, but the storage path is on {{type}}: every seal will fail.',
                { needed: SEAL_FILESYSTEM[target.seal_mode] ?? target.seal_mode, type: fsType });
        case 'btrfs_not_subvolume':
            return (
                <>
                    {t('backups.warning.btrfsNotSubvolume',
                        'btrfs snapshots need the repository directory to be a subvolume, so every seal will fail. Create it with:')}{' '}
                    {/* eslint-disable-next-line i18next/no-literal-string -- a shell command */}
                    <code>btrfs subvolume create {target.storage_path}</code>
                </>
            );
        case 'seal_stale':
            return t('backups.warning.sealStale', 'Not sealed since the last backup: {{hosts}}',
                { hosts: staleHosts(target, hosts, warning) });
        case 'prune_stale':
            return t('backups.warning.pruneStale', 'Not pruned for more than twice the backup interval: {{hosts}}',
                { hosts: staleHosts(target, hosts, warning) });
        case 'check_stale':
            return t('backups.warning.checkStale', 'Not checked for more than twice the check interval: {{hosts}}',
                { hosts: staleHosts(target, hosts, warning) });
        case 'not_sealed':
            return t('backups.warning.notSealed', 'Not sealed (no immutable copies)');
        case 'fs_cannot_snapshot':
            return t('backups.warning.fsCannotSnapshot',
                'The storage path is on {{type}}, which cannot take snapshots, so backups cannot be sealed against a compromised host. It works, but consider ZFS or btrfs for immutable copies.',
                { type: fsType });
        case 'fs_unchecked':
            return t('backups.warning.fsUnchecked', 'Filesystem not checked yet');
        default:
            return warning;
    }
};

const LastRun: React.FC<{ label: string; run: StorageRunBrief | null }> = ({ label, run }) => {
    const { t } = useTranslation();
    return (
        <Typography variant="body2">
            {label}:{' '}
            {run
                ? `${formatTime(run.finished_at)} (${runStatusLabel(t, { status: run.status, check_label: null } as BackupRun)})`
                : t('backups.storage.never', 'Never')}
        </Typography>
    );
};

const BackupStorageStatus: React.FC<{ target: BackupTarget; hosts: BackupHost[] }> = ({ target, hosts }) => {
    const { t } = useTranslation();
    const status = target.storage_status;
    const fs = target.storage_fs;
    return (
        <Box>
            {status && (
                <Box sx={{ mt: 1 }} data-testid="backup-storage-status">
                    <Typography variant="body2">
                        {t('backups.storage.confirmed', 'Storage job files confirmed: {{confirmed}} of {{total}}',
                            { confirmed: status.confirmed, total: status.policies })}
                    </Typography>
                    <LastRun label={t('backups.storage.lastSeal', 'Last seal')} run={status.last_seal} />
                    <LastRun label={t('backups.storage.lastPrune', 'Last prune')} run={status.last_prune} />
                    <LastRun label={t('backups.storage.lastCheck', 'Last check')} run={status.last_check} />
                    {fs.type && (
                        <Typography variant="body2">
                            {t('backups.storage.filesystem', 'Storage filesystem')}: {fs.type}
                            {fs.mount_point && <> (<code>{fs.mount_point}</code>)</>}
                        </Typography>
                    )}
                </Box>
            )}
            <Stack spacing={1} sx={{ mt: 1 }}>
                {target.warnings.map(w => (
                    <Alert key={w} severity={warningSeverity(w)} variant={w === 'fs_unchecked' ? 'outlined' : 'standard'}>
                        {warningText(t, target, hosts, w)}
                    </Alert>
                ))}
            </Stack>
        </Box>
    );
};

export default BackupStorageStatus;
