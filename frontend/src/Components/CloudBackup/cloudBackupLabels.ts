// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Words for the iCloud Photos codes the server and the storage host's agent
// send (ROADMAP 24.12).

import type { TFunction } from 'i18next';
import type { CloudAccountStatus, CloudRun, CloudSummary } from '../../Services/cloudBackup';

type ChipColor = 'default' | 'success' | 'warning' | 'error' | 'info';

export const accountStatusLabel = (t: TFunction, status: CloudAccountStatus): string => {
    const labels: Record<CloudAccountStatus, string> = {
        new: t('cloudBackup.status.new', 'Not signed in yet'),
        ok: t('cloudBackup.status.ok', 'Up to date'),
        running: t('cloudBackup.status.running', 'Running'),
        waiting_code: t('cloudBackup.status.waitingCode', 'Waiting for the two-factor code'),
        needs_sign_in: t('cloudBackup.status.needsSignIn', 'Needs sign-in'),
        failed: t('cloudBackup.status.failed', 'Failed'),
    };
    return labels[status] ?? status;
};

export const accountStatusColor = (status: CloudAccountStatus): ChipColor => {
    switch (status) {
        case 'ok':
            return 'success';
        case 'failed':
            return 'error';
        case 'needs_sign_in':
        case 'waiting_code':
            return 'warning';
        case 'running':
            return 'info';
        default:
            return 'default';
    }
};

export const actionLabel = (t: TFunction, action: CloudRun['action']): string => {
    const labels: Record<CloudRun['action'], string> = {
        enable: t('cloudBackup.action.enable', 'Enable'),
        connect: t('cloudBackup.action.connect', 'Sign-in'),
        download: t('cloudBackup.action.download', 'Download'),
        reconcile: t('cloudBackup.action.reconcile', 'Full pass'),
        libraries: t('cloudBackup.action.libraries', 'List libraries'),
        remove: t('cloudBackup.action.remove', 'Removal'),
    };
    return labels[action] ?? action;
};

/** Why a job or Enable failed, as something an operator can act on.  The
 *  codes come from the storage host's agent (cloud_backup/runner.py, tool.py
 *  and operations.py); an unknown one falls back to the agent's message. */
export const reasonText = (t: TFunction, reason: string | null, fallback: string | null): string => {
    switch (reason) {
        case 'auth_failed':
            return t('cloudBackup.reason.authFailed',
                'Apple did not accept the sign-in for this account. Check the password, then press Connect and enter the two-factor code.');
        case 'session_expired':
            return t('cloudBackup.reason.sessionExpired',
                'Apple wants a new sign-in for this account. Press Connect and enter the two-factor code.');
        case 'code_rejected':
            return t('cloudBackup.reason.codeRejected', 'Apple did not accept the two-factor code. Press Connect to try again.');
        case 'no_code':
            return t('cloudBackup.reason.noCode', 'No two-factor code was entered in time. Press Connect to try again.');
        case 'two_step':
            return t('cloudBackup.reason.twoStep',
                "This Apple ID uses Apple's older two-step verification, which is not supported. Turn on two-factor authentication for it, then press Connect.");
        case 'web_access_off':
            return t('cloudBackup.reason.webAccessOff',
                'iCloud data cannot be reached from the web for this account. With Advanced Data Protection on, turn on "Access iCloud Data on the Web" on the iPhone (Settings, your name, iCloud), then try again.');
        case 'password_unavailable':
            return t('cloudBackup.reason.passwordUnavailable', 'The storage host could not get the password from the server for this job.');
        case 'checksum_mismatch':
            return t('cloudBackup.reason.checksumMismatch',
                'The downloaded icloudpd did not match its pinned checksum, so nothing was installed.');
        case 'no_python':
            return t('cloudBackup.reason.noPython',
                'icloudpd needs Python 3.10 to 3.13 on the storage host. Install one (for example: pkg install python311), then press Enable iCloud backup again.');
        case 'wrong_platform':
            return t('cloudBackup.reason.wrongPlatform', 'icloudpd is not offered on the storage host\'s operating system.');
        case 'missing_tool':
            return t('cloudBackup.reason.missingTool', 'icloudpd is not installed on the storage host. Press Enable iCloud backup.');
        case 'agent_outdated':
            return t('cloudBackup.reason.agentOutdated', 'The storage host\'s agent is too old for iCloud backup. Update the agent.');
        case 'prepare_failed':
            return t('cloudBackup.reason.prepareFailed', 'The place for the photos could not be prepared on the storage.');
        default:
            return fallback || t('cloudBackup.reason.unknown', 'The job did not finish. The details below say why.');
    }
};

/** The one line the dashboard's backup card shows for iCloud, or null. */
export const dashboardNote = (t: TFunction, summary: CloudSummary | null): string | null => {
    if (!summary?.enabled) return null;
    if (summary.needs_sign_in > 0) {
        return t('cloudBackup.dashboard.needsSignIn', 'iCloud accounts that need sign-in: {{n}}', { n: summary.needs_sign_in });
    }
    if (summary.failed > 0) {
        return t('cloudBackup.dashboard.failed', 'iCloud accounts that failed: {{n}}', { n: summary.failed });
    }
    if (summary.expiring > 0) {
        return t('cloudBackup.dashboard.expiring', 'iCloud sign-ins that end soon: {{n}}', { n: summary.expiring });
    }
    return null;
};

/** How many iCloud accounts need someone to act (the dashboard counts them). */
export const attentionCount = (summary: CloudSummary | null): number =>
    summary?.enabled ? summary.needs_sign_in + summary.failed : 0;
