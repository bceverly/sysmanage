// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Words for the backup codes the server sends (Phase 24).

import type { TFunction } from 'i18next';
import { appLocale } from '../../utils/locale';
import type { BackupRun, BackupStatus, Coverage } from '../../Services/backups';

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
            return 'info';
        default:
            return 'default';
    }
};

export const statusLabel = (t: TFunction, status: BackupStatus): string => {
    const labels: Record<BackupStatus, string> = {
        ok: t('backups.status.ok', 'Backed up'),
        incomplete: t('backups.status.incomplete', 'Incomplete'),
        overdue: t('backups.status.overdue', 'Overdue'),
        failed: t('backups.status.failed', 'Failed'),
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

export const formatTime = (iso: string | null | undefined): string =>
    iso ? new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`).toLocaleString(appLocale()) : '--';

/** The server's own (translated) message, or ``fallback``. */
export const apiDetail = (error: unknown, fallback: string): string => {
    const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};
