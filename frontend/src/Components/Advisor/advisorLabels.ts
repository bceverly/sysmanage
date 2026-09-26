// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Wording for the advisor's CODES. The server and engine return codes --
// outcomes, levels, gap reasons, proposal states -- never sentences, so every
// language gets its own wording from here. Literal keys (no template strings)
// so the i18n tooling can see every one.

import type { TFunction } from 'i18next';
import type { AdvisorGap, AdvisorLevel, AdvisorOutcome, AdvisorProposalStatus } from '../../Services/advisorService';

type ChipColor = 'default' | 'error' | 'warning' | 'info' | 'success';

export const outcomeLabel = (t: TFunction, outcome: AdvisorOutcome): string => {
    const labels: Record<AdvisorOutcome, string> = {
        fires: t('advisor.outcome.fires', 'Finding'),
        does_not_fire: t('advisor.outcome.doesNotFire', 'Clean'),
        not_assessable: t('advisor.outcome.notAssessable', 'Not assessable'),
        not_applicable: t('advisor.outcome.notApplicable', 'Not applicable'),
    };
    return labels[outcome] ?? outcome;
};

export const levelLabel = (t: TFunction, level: AdvisorLevel): string => {
    const labels: Record<AdvisorLevel, string> = {
        CRITICAL: t('advisor.level.critical', 'Critical'),
        HIGH: t('advisor.level.high', 'High'),
        MEDIUM: t('advisor.level.medium', 'Medium'),
        LOW: t('advisor.level.low', 'Low'),
        NONE: t('advisor.level.none', 'No findings'),
        UNKNOWN: t('advisor.level.unknown', 'Not assessed'),
    };
    return labels[level] ?? level;
};

export const levelColor = (level: AdvisorLevel): ChipColor => {
    const colors: Record<AdvisorLevel, ChipColor> = {
        CRITICAL: 'error',
        HIGH: 'error',
        MEDIUM: 'warning',
        LOW: 'info',
        NONE: 'success',
        // Never green: an unassessed host is not a healthy one.
        UNKNOWN: 'default',
    };
    return colors[level] ?? 'default';
};

export const lensLabel = (t: TFunction, lens: string | null | undefined): string => {
    const labels: Record<string, string> = {
        security: t('advisor.lens.security', 'Security'),
        performance: t('advisor.lens.performance', 'Performance'),
        availability: t('advisor.lens.availability', 'Availability'),
        stability: t('advisor.lens.stability', 'Stability'),
    };
    return (lens && labels[lens]) || lens || '';
};

export const gapReasonLabel = (t: TFunction, reason: string): string => {
    const labels: Record<string, string> = {
        missing: t('advisor.gap.missing', 'never reported'),
        stale: t('advisor.gap.stale', 'too old to trust'),
        not_collected: t('advisor.gap.notCollected', 'not collected yet'),
        columns_not_advertised: t('advisor.gap.columnsNotAdvertised', 'agent too old to report the needed columns'),
        columns_not_populated: t('advisor.gap.columnsNotPopulated', 'agent does not fill the needed columns'),
        domain_unavailable: t('advisor.gap.domainUnavailable', 'not measured by this version'),
        rule_error: t('advisor.gap.ruleError', 'the rule could not be evaluated'),
        insufficient_peers: t('advisor.gap.insufficientPeers', 'no comparable hosts'),
        not_applicable: t('advisor.gap.notApplicable', 'does not apply to this platform'),
        unsupported: t('advisor.gap.unsupported', 'not supported by this agent'),
        unknown: t('advisor.gap.unknown', 'agent never reported coverage'),
    };
    return labels[reason] ?? reason;
};

export const evidenceLabel = (t: TFunction, evidence: string): string => {
    if (evidence.startsWith('facts.')) {
        return t('advisor.evidence.facts', 'Facts: {{table}}', { table: evidence.slice(6) });
    }
    if (evidence.startsWith('peer_group.')) {
        return t('advisor.evidence.peerGroup', 'Peer group');
    }
    const labels: Record<string, string> = {
        vuln: t('advisor.evidence.vuln', 'Vulnerability scan'),
        compliance: t('advisor.evidence.compliance', 'Compliance scan'),
        drift: t('advisor.evidence.drift', 'Configuration drift check'),
        updates: t('advisor.evidence.updates', 'Update detection'),
        reboot: t('advisor.evidence.reboot', 'Reboot status'),
        packages: t('advisor.evidence.packages', 'Software inventory'),
        firewall: t('advisor.evidence.firewall', 'Firewall status'),
        metric_history: t('advisor.evidence.metricHistory', 'Metric history'),
        when: t('advisor.evidence.when', 'Rule query'),
        rule: t('advisor.evidence.rule', 'Rule definition'),
    };
    return labels[evidence] ?? evidence;
};

/** One gap as a sentence fragment: what is missing and why. */
export const gapText = (t: TFunction, gap: AdvisorGap): string =>
    `${evidenceLabel(t, gap.evidence)}: ${gapReasonLabel(t, gap.reason)}`;

export const proposalStatusLabel = (t: TFunction, status: AdvisorProposalStatus): string => {
    const labels: Record<AdvisorProposalStatus, string> = {
        proposed: t('advisor.proposal.status.proposed', 'Awaiting approval'),
        approved: t('advisor.proposal.status.approved', 'Approved'),
        rejected: t('advisor.proposal.status.rejected', 'Rejected'),
        withdrawn: t('advisor.proposal.status.withdrawn', 'Withdrawn'),
        failed: t('advisor.proposal.status.failed', 'Failed'),
    };
    return labels[status] ?? status;
};

export const proposalReasonLabel = (t: TFunction, reason: string | null): string => {
    if (!reason) return '';
    const labels: Record<string, string> = {
        no_longer_fires: t('advisor.proposal.reason.noLongerFires', 'the finding is gone'),
        rule_removed: t('advisor.proposal.reason.ruleRemoved', 'the rule was removed or switched off'),
        profile_missing: t('advisor.proposal.reason.profileMissing', 'the configuration profile it names is missing or inactive'),
        not_queued: t('advisor.proposal.reason.notQueued', 'the host could not take the command'),
        not_proposed: t('advisor.proposal.reason.notProposed', 'it was already decided'),
    };
    return labels[reason] ?? reason;
};
