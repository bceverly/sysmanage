// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Words for the backup codes the server sends (Phase 24).

import type { TFunction } from 'i18next';
import { appLocale } from '../../utils/locale';
import type { BackupRun, BackupStatus, BackupSummary, Coverage } from '../../Services/backups';

type ChipColor = 'default' | 'success' | 'warning' | 'error' | 'info';

export const statusColor = (status: BackupStatus): ChipColor => {
    switch (status) {
        case 'ok':
            return 'success';
        case 'failed':
            return 'error';
        case 'overdue':
        case 'incomplete':
        case 'not_equipped':
            return 'warning';
        case 'never':
        case 'running':
        case 'waiting_window':
            return 'info';
        default:
            return 'default';
    }
};

/** A note under an overdue or failed host whose next backup a closed
 *  maintenance window holds; null otherwise. */
export const heldNote = (t: TFunction, host: { capture_held?: boolean; status: BackupStatus }): string | null =>
    host.capture_held && host.status !== 'waiting_window'
        ? t('backups.hosts.heldNote', "The next backup waits for this host's maintenance window")
        : null;

export const statusLabel = (t: TFunction, status: BackupStatus): string => {
    const labels: Record<BackupStatus, string> = {
        ok: t('backups.status.ok', 'Backed up'),
        incomplete: t('backups.status.incomplete', 'Incomplete'),
        overdue: t('backups.status.overdue', 'Overdue'),
        failed: t('backups.status.failed', 'Failed'),
        running: t('backups.status.running', 'Backing up'),
        waiting_window: t('backups.status.waitingWindow', 'Waiting for window'),
        never: t('backups.status.never', 'Never backed up'),
        not_equipped: t('backups.status.notEquipped', 'Not equipped'),
        disabled: t('backups.status.disabled', 'Disabled'),
        no_policy: t('backups.status.noPolicy', 'Not configured'),
    };
    return labels[status] ?? status;
};

/** Why a host cannot run backups, as something an operator can act on. */
export const reasonLabel = (t: TFunction, reason: string | null): string => {
    switch (reason) {
        case 'missing_tool':
            return t('backups.reason.missingTool', 'Install restate');
        case 'tool_outdated':
            return t('backups.reason.toolOutdated', 'Upgrade restate');
        case 'missing_nfs_client':
            return t('backups.reason.missingNfsClient', 'Install the NFS client');
        case 'agent_outdated':
            return t('backups.reason.agentOutdated', 'Upgrade the agent');
        case 'not_privileged':
            return t('backups.reason.notPrivileged', 'The agent must run as root');
        case 'wrong_platform':
            return t('backups.reason.wrongPlatform', 'Not supported on this OS');
        case 'no_host':
        case 'no_storage_host':
            return t('backups.reason.noStorageHost', 'No storage host is set');
        default:
            return reason ?? '';
    }
};

export const coverageLabel = (t: TFunction, coverage: Coverage): string => {
    const labels: Record<Coverage, string> = {
        full: t('backups.coverage.full', 'Full (files and packages)'),
        files_only: t('backups.coverage.filesOnly', 'Files only'),
        unsupported: t('backups.coverage.unsupported', 'Not supported'),
    };
    return labels[coverage] ?? coverage;
};

export const actionLabel = (t: TFunction, action: string): string => {
    const labels: Record<string, string> = {
        configure: t('backups.action.configure', 'Configure'),
        capture: t('backups.action.capture', 'Backup'),
        seal: t('backups.action.seal', 'Seal'),
        prune: t('backups.action.prune', 'Prune'),
        check: t('backups.action.check', 'Check'),
        estimate: t('backups.action.estimate', 'Estimate'),
        snapshots: t('backups.action.snapshots', 'List snapshots'),
        restore: t('backups.action.restore', 'Restore'),
        du: t('backups.action.du', 'Storage use'),
        repack: t('backups.action.repack', 'Repack'),
        prepare: t('backups.action.prepare', 'Prepare storage'),
        protect: t('backups.action.protect', 'Protect'),
        verify: t('backups.action.verify', 'Full-read verification'),
    };
    return labels[action] ?? action;
};

export const runStatusLabel = (t: TFunction, run: BackupRun): string => {
    switch (run.check_label) {
        case 'verified':
            return t('backups.run.verified', 'Verified');
        case 'changed':
            return t('backups.run.changed', 'Changed');
        case 'metadata_check_passed':
            return t('backups.run.metadataCheckPassed', 'Metadata check passed');
        case 'metadata_changed':
            return t('backups.run.metadataChanged', 'Metadata changed');
        default:
            break;
    }
    const labels: Record<string, string> = {
        queued: t('backups.run.queued', 'Queued'),
        running: t('backups.run.running', 'Running'),
        ok: t('backups.run.ok', 'Succeeded'),
        different: t('backups.run.different', 'Differences found'),
        incomplete: t('backups.run.incomplete', 'Incomplete'),
        failed: t('backups.run.failed', 'Failed'),
        untrusted: t('backups.run.untrusted', 'Untrusted'),
        busy: t('backups.run.busy', 'Busy, will retry'),
    };
    return labels[run.status] ?? run.status;
};

export const runStatusColor = (status: string): ChipColor => {
    if (status === 'ok') return 'success';
    if (status === 'failed' || status === 'untrusted') return 'error';
    if (status === 'incomplete' || status === 'different' || status === 'busy') return 'warning';
    return 'info';
};

export const formatBytes = (bytes: number | null | undefined): string => {
    if (bytes == null) return '--';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
    if (bytes < 1024 ** 4) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
    return `${(bytes / 1024 ** 4).toFixed(2)} TB`;
};

export const formatTime = (iso: string | null | undefined): string => {
    if (!iso) return '--';
    // A naive timestamp from the server is UTC.
    const zoned = iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`;
    return new Date(zoned).toLocaleString(appLocale());
};

/** The server's own (translated) message, or ``fallback``. */
export const apiDetail = (error: unknown, fallback: string): string => {
    const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

/** What the newest capture that made a snapshot could not read (restate's
 *  result: a count and the first paths, each with why), or null. */
type UnreadablePath = string | { path?: string; reason?: string };
export const unreadableOf = (run: BackupRun | null): { count: number; first: string[] } | null => {
    const unreadable = (run?.result as { unreadable?: { count?: number; first?: UnreadablePath[] } } | null)?.unreadable;
    const count = unreadable?.count ?? 0;
    if (count <= 0) return null;
    const first = (unreadable?.first ?? []).map(entry =>
        typeof entry === 'string' ? entry : [entry.path, entry.reason].filter(Boolean).join(': '));
    return { count, first };
};

/** Each service restate paused for a capture: kind and name, how long it was
 *  paused, and how it ended (restate's result ``quiesce`` list). */
export interface PausedService {
    service: string;
    seconds: number | null;
    ok: boolean;
    message: string;
}

export const pausedServicesOf = (run: BackupRun): PausedService[] => {
    const entries = (run.result as { quiesce?: Array<Record<string, string>> } | null)?.quiesce;
    if (!Array.isArray(entries)) return [];
    return entries.map(entry => {
        const paused = Date.parse(entry.paused_at ?? '');
        const resumed = Date.parse(entry.resumed_at ?? '');
        return {
            service: [entry.kind, entry.name].filter(Boolean).join(' '),
            seconds: Number.isFinite(paused) && Number.isFinite(resumed) ? Math.round((resumed - paused) / 1000) : null,
            ok: entry.status === 'ok',
            message: entry.message ?? '',
        };
    });
};

/** The dashboard Backups card's level: an error when a backup failed or the
 *  backup storage is broken (or critically full), a warning when one is
 *  only overdue or incomplete. */
export const backupSummaryLevel = (
    summary: Pick<BackupSummary, 'counts' | 'target_problem'>,
): 'error' | 'warning' | 'ok' => {
    if (summary.counts.failed || summary.target_problem) return 'error';
    return summary.counts.overdue || summary.counts.incomplete ? 'warning' : 'ok';
};
