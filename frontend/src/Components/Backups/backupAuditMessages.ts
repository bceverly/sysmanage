// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The storage host's append-only audit (ROADMAP 24.1 / 24.5), as warnings on
// the target: what is wrong, which hosts it touches, and what to change.  The
// storage host's agent checks; it changes nothing.

import type { AlertColor } from '@mui/material';
import type { TFunction } from 'i18next';
import type { BackupHost, BackupTarget } from '../../Services/backups';

const finding = (target: BackupTarget, code: string) => target.storage_audit?.[code.replace(/^audit_/, '')];

export const auditSeverity = (target: BackupTarget, code: string): AlertColor =>
    finding(target, code)?.level === 'error' ? 'error' : 'warning';

const hostNames = (target: BackupTarget, hosts: BackupHost[], code: string): string => {
    const names = new Map(hosts.map(h => [h.host_id, h.fqdn]));
    return (finding(target, code)?.hosts ?? []).map(id => names.get(id) ?? id).join(', ');
};

export const auditText = (t: TFunction, target: BackupTarget, hosts: BackupHost[], code: string): string => {
    const entry = finding(target, code);
    const params = (entry?.params ?? {}) as Record<string, unknown>;
    const who = hostNames(target, hosts, code);
    switch (code) {
        case 'audit_nfs_server':
            return t('backups.audit.nfsServer', 'The storage host\'s NFS server is not running, or does not start at boot.');
        case 'audit_nfs_v4':
            // The agent could not tell (no rights to read what nfsd serves,
            // and no rpcinfo answer): say so rather than claim it is missing.
            if (params.checked === false) {
                return t('backups.audit.nfsV4Unknown', 'Could not check whether the storage host serves NFSv4, which hosts use to reach their backups.');
            }
            return t('backups.audit.nfsV4', 'The storage host does not serve NFSv4, which hosts use to reach their backups.');
        case 'audit_nfs_v4_only':
            return t('backups.audit.nfsV4Only', 'The storage host still serves NFS versions older than 4. Serve NFSv4 only.');
        case 'audit_nfs_local_locks':
            return t('backups.audit.nfsLocalLocks',
                'The storage host does not show hosts\' locks to its own programs (FreeBSD: set vfs.nfsd.enable_locallocks=1), so a prune could run during a backup.');
        case 'audit_nfs_v4_root':
            return t('backups.audit.nfsV4Root', 'The storage host\'s /etc/exports has no "V4:" root line, so hosts cannot mount over NFSv4.');
        case 'audit_service_account':
            return t('backups.audit.serviceAccount', 'The backup service account {{account}} does not exist on the storage host.',
                { account: typeof params.account === 'string' ? params.account : (target.service_account ?? '') });
        case 'audit_own_filesystem':
            return t('backups.audit.ownFilesystem',
                'Not on their own filesystem: {{hosts}}. Give each host its own ZFS dataset or btrfs subvolume, so each gets its own export.',
                { hosts: who });
        case 'audit_export_shared':
            return t('backups.audit.exportShared',
                'Reachable through a shared export: {{hosts}}. A compromised host could reach other hosts\' backups. Export each host\'s repository on its own.',
                { hosts: who });
        case 'audit_export_own':
            return t('backups.audit.exportOwn', 'Without an export of their own: {{hosts}}.', { hosts: who });
        case 'audit_export_restricted':
            return t('backups.audit.exportRestricted',
                'Exports not limited to the host\'s own address: {{hosts}}.', { hosts: who });
        case 'audit_export_mapping':
            return t('backups.audit.exportMapping',
                'Exports that do not map every client to the backup account: {{hosts}}. FreeBSD: -mapall=ACCOUNT:GROUP; Linux: all_squash with anonuid and anongid.',
                { hosts: who });
        case 'audit_append_only_layout':
            return t('backups.audit.appendOnly',
                'Not append-only: {{hosts}} could delete or overwrite their own finished backups. The protect step after the next backup locks them (restate 2.1.0.1 or later; 2.1.0.3 on FreeBSD with ZFS).',
                { hosts: who });
        default:
            return t('backups.audit.other', 'Storage check: {{code}}', { code: code.replace(/^audit_/, '') });
    }
};
