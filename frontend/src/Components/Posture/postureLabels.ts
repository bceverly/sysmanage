// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Wording for the posture punch list's CODES (21.4), and for the curated
// packs' names and rule titles -- content the engine ships in English only,
// which the 21.2 UI showed untranslated. Literal keys so the i18n tooling can
// see every one; anything unknown falls back to what the server sent.

import type { TFunction } from 'i18next';
import type { PostureState } from '../../Services/postureService';

type ChipColor = 'default' | 'error' | 'warning' | 'info' | 'success';

export const stateLabel = (t: TFunction, state: PostureState): string => {
    const labels: Record<PostureState, string> = {
        satisfied: t('posture.state.satisfied', 'Satisfied'),
        open: t('posture.state.open', 'Open'),
        waived: t('posture.state.waived', 'Waived'),
        not_assessable: t('posture.state.notAssessable', 'Not assessable'),
    };
    return labels[state] ?? state;
};

export const stateColor = (state: PostureState): ChipColor => {
    const colors: Record<PostureState, ChipColor> = {
        satisfied: 'success',
        open: 'error',
        // An accepted risk is NEUTRAL, never green: it was not eliminated.
        waived: 'default',
        // Never green either: nothing was measured.
        not_assessable: 'warning',
    };
    return colors[state] ?? 'default';
};

export const eventKindLabel = (t: TFunction, kind: string): string => {
    const labels: Record<string, string> = {
        regression: t('posture.event.regression', 'Regressed'),
        resolved: t('posture.event.resolved', 'Resolved'),
        blind_spot: t('posture.event.blindSpot', 'Could no longer be assessed'),
        measured_again: t('posture.event.measuredAgain', 'Assessed again'),
        added: t('posture.event.added', 'Added'),
        removed: t('posture.event.removed', 'Removed'),
        added_by_model: t('posture.event.addedByModel', 'Added by the threat model'),
        removed_by_model: t('posture.event.removedByModel', 'Removed by the threat model'),
        changed_by_model: t('posture.event.changedByModel', 'Changed by the threat model'),
        withdrawn: t('posture.event.withdrawn', 'Check withdrawn'),
        remediation_requested: t('posture.event.remediationRequested', 'Remedy applied'),
        changed: t('posture.event.changed', 'Changed'),
    };
    return labels[kind] ?? kind;
};

export const gapLabel = (t: TFunction, reason: string): string => {
    const labels: Record<string, string> = {
        missing: t('posture.gap.missing', 'The evidence could not be read'),
        unavailable: t('posture.gap.unavailable', 'SysManage has no view of this on this installation'),
        coverage_unknown: t('posture.gap.coverageUnknown', 'Some hosts have not reported this'),
        threat_model_incomplete: t('posture.gap.threatModelIncomplete', 'The threat model is incomplete'),
        rule_error: t('posture.gap.ruleError', 'The check could not be evaluated'),
    };
    return labels[reason] ?? reason;
};

export const staleLabel = (t: TFunction, reason: string): string => {
    const labels: Record<string, string> = {
        risk_rose: t('posture.stale.riskRose', 'The risk has risen since it was waived'),
        rule_version_changed: t('posture.stale.ruleChanged', 'The check has changed since it was waived'),
        threat_model_changed: t('posture.stale.modelChanged', 'The threat model has changed since it was waived'),
    };
    return labels[reason] ?? reason;
};

export const refusalLabel = (t: TFunction, code: string): string => {
    const labels: Record<string, string> = {
        not_open: t('posture.refusal.notOpen', 'Only an open item can be waived or fixed.'),
        already_waived: t('posture.refusal.alreadyWaived', 'This item is already waived.'),
        reason_required: t('posture.refusal.reasonRequired', 'A reason is required.'),
        not_stale: t('posture.refusal.notStale', 'This waiver does not need re-affirming.'),
        not_waived: t('posture.refusal.notWaived', 'This item is not waived.'),
        managed_by_server: t('posture.refusal.managedByServer', 'Only the server operator can change this setting.'),
        nothing_to_do: t('posture.refusal.nothingToDo', 'There is nothing left to change.'),
        not_automated: t('posture.refusal.notAutomated', 'This has no automated fix.'),
        unknown_remedy: t('posture.refusal.unknownRemedy', 'This check does not name a fix.'),
    };
    return labels[code] ?? code;
};

/** How each remedy fixes its item -- shown beside the control. */
export const remedyText = (t: TFunction, remedy: string | null): string => {
    const texts: Record<string, string> = {
        require_admin_mfa: t('posture.remedy.require_admin_mfa', 'Require MFA for administrators.'),
        enforce_lockout: t('posture.remedy.enforce_lockout', 'Lock accounts after 5 failed logins.'),
        shorten_session: t('posture.remedy.shorten_session', 'Expire sessions after an hour.'),
        enable_fips: t('posture.remedy.enable_fips', 'Enable FIPS mode on the hosts that support it, in their maintenance windows.'),
        enable_firewall: t('posture.remedy.enable_firewall', 'Turn on the firewall on the hosts where it is off, in their maintenance windows.'),
        enable_antivirus: t('posture.remedy.enable_antivirus', 'Turn on the installed antivirus where it is off. Hosts with none need a product chosen on the antivirus page.'),
        enroll_admin_mfa: t('posture.remedy.enroll_admin_mfa', 'Each administrator enrolls MFA from their own profile.'),
        configure_log_forwarding: t('posture.remedy.configure_log_forwarding', 'Choose where logs are forwarded in the logging settings.'),
        set_audit_retention: t('posture.remedy.set_audit_retention', 'Create an audit retention policy of at least 365 days through the audit API. There is no screen for this yet.'),
        configure_alerting: t('posture.remedy.configure_alerting', 'Add a notification channel and an alert rule on the alerts page.'),
        schedule_security_updates: t('posture.remedy.schedule_security_updates', 'Schedule security updates with an update profile.'),
        define_maintenance_windows: t('posture.remedy.define_maintenance_windows', 'Define when changes may be made.'),
        configure_backups: t('posture.remedy.configure_backups', 'Configure a backup command and a recovery point objective.'),
        set_air_gap_role: t('posture.remedy.set_air_gap_role', 'Set the server role to match your air-gapped deployment.'),
        expire_api_keys: t('posture.remedy.expire_api_keys', 'Replace API keys that never expire with ones that do.'),
        run_compliance_scans: t('posture.remedy.run_compliance_scans', 'Run compliance scans on every host.'),
        patch_critical_vulnerabilities: t('posture.remedy.patch_critical_vulnerabilities', 'Review and approve the proposed fixes.'),
        enable_openbao: t('posture.remedy.enable_openbao', 'Store secrets in OpenBAO.'),
        set_password_policy: t('posture.remedy.set_password_policy', 'The password policy is set in sysmanage.yaml; SysManage cannot change it for you.'),
    };
    return (remedy && texts[remedy]) || '';
};

/** Where a guided remedy's link goes. A target with no screen has no link. */
export const GUIDED_ROUTES: Record<string, string> = {
    user_security: '/profile',
    logging_settings: '/settings#logging',
    alerting: '/alerts',
    upgrade_profiles: '/settings#update-profiles',
    maintenance_windows: '/maintenance-windows',
    tenant_backups: '/tenants',
    server_role: '/settings#server-role',
    api_keys: '/api-keys',
    compliance: '/compliance',
    advisor_proposals: '/advisor',
    secrets: '/secrets',
};

export const ruleTitle = (t: TFunction, key: string, fallback?: string | null): string => {
    const titles: Record<string, string> = {
        // Posture checks (21.4)
        'PM-MFA-ENFORCED': t('advisor.curated.pmMfaEnforced', 'MFA is required for administrators'),
        'PM-MFA-ENROLLED': t('advisor.curated.pmMfaEnrolled', 'Every administrator has enrolled MFA'),
        'PM-LOCKOUT': t('advisor.curated.pmLockout', 'Repeated failed logins lock the account'),
        'PM-SESSION-TIMEOUT': t('advisor.curated.pmSessionTimeout', 'Sessions expire within an hour'),
        'PM-PASSWORD-LENGTH': t('advisor.curated.pmPasswordLength', 'Passwords are at least 12 characters'),
        'PM-LOG-FORWARD': t('advisor.curated.pmLogForward', 'Logs are forwarded off the hosts'),
        'PM-AUDIT-RETENTION': t('advisor.curated.pmAuditRetention', 'Audit history is kept for at least a year'),
        'PM-SECRETS': t('advisor.curated.pmSecrets', 'Secrets are kept in OpenBAO'),
        'PM-AIRGAP-ROLE': t('advisor.curated.pmAirgapRole', 'The server is set up as the air-gapped deployment you described'),
        'PM-BACKUPS': t('advisor.curated.pmBackups', 'Backups meet your recovery point objective'),
        'PM-ALERTING': t('advisor.curated.pmAlerting', 'Someone is notified when something breaks'),
        'PM-PATCH-CADENCE': t('advisor.curated.pmPatchCadence', 'Security updates are applied on a schedule'),
        'PM-MAINT-WINDOWS': t('advisor.curated.pmMaintWindows', 'Changes land in planned maintenance windows'),
        'PM-API-KEY-EXPIRY': t('advisor.curated.pmApiKeyExpiry', 'No API key is left without an expiry'),
        'PM-FIPS': t('advisor.curated.pmFips', 'FIPS mode is on wherever it is available'),
        'PM-ANTIVIRUS': t('advisor.curated.pmAntivirus', 'Every host runs antivirus'),
        'PM-FIREWALL': t('advisor.curated.pmFirewall', "Every host's firewall is on"),
        'PM-COMPLIANCE-SCANS': t('advisor.curated.pmComplianceScans', 'Every host has a compliance scan from the last 30 days'),
        'PM-CRITICAL-VULNS': t('advisor.curated.pmCriticalVulns', 'No host has an unpatched critical vulnerability'),
        // Baseline pack (21.2)
        'SM-SEC-001': t('advisor.curated.smSec001', 'Critical vulnerability with a fix available'),
        'SM-SEC-002': t('advisor.curated.smSec002', 'High-severity vulnerability with a fix available'),
        'SM-SEC-003': t('advisor.curated.smSec003', 'Account other than root with user ID 0'),
        'SM-SEC-004': t('advisor.curated.smSec004', 'Services listening on all interfaces while the host firewall is off'),
        'SM-SEC-005': t('advisor.curated.smSec005', 'Certificate expiring within 30 days'),
        'SM-PERF-001': t('advisor.curated.smPerf001', 'Filesystem more than 90% full'),
        'SM-AVAIL-001': t('advisor.curated.smAvail001', 'Security updates pending'),
        'SM-AVAIL-002': t('advisor.curated.smAvail002', 'Reboot required'),
        'SM-STAB-001': t('advisor.curated.smStab001', 'Configuration drift unresolved for more than 7 days'),
        'SM-COMP-001': t('advisor.curated.smComp001', 'Failed high or critical compliance checks'),
        'SM-STAB-F01': t('advisor.curated.smStabF01', 'OpenSSL version differs from the version its peers run'),
    };
    return titles[key] ?? fallback ?? key;
};

export const packName = (t: TFunction, slug: string, fallback?: string | null): string => {
    const names: Record<string, string> = {
        'sysmanage-baseline': t('advisor.curatedPack.baseline.name', 'SysManage baseline'),
        'sysmanage-posture': t('advisor.curatedPack.posture.name', 'SysManage posture'),
    };
    return names[slug] ?? fallback ?? slug;
};

export const packDescription = (t: TFunction, slug: string, fallback?: string | null): string => {
    const texts: Record<string, string> = {
        'sysmanage-baseline': t('advisor.curatedPack.baseline.description',
            'Security, performance, availability and stability checks over the evidence every SysManage host reports.'),
        'sysmanage-posture': t('advisor.curatedPack.posture.description',
            'Installation-wide security and resilience checks, applied according to your threat model.'),
    };
    return texts[slug] ?? fallback ?? '';
};
