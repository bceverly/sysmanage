// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The advisor UI (Phase 21.2 S7).  The property under test is the phase's:
// what the advisor could NOT assess is rendered -- counted, with its reasons
// -- and an unassessed grade is never shown as clean.  21.1 S6 computed an
// honest `comparable: false` and never rendered it; these tests exist so the
// advisor cannot repeat that.

import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('react-i18next', () => {
    const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
        let s = typeof fallback === 'string' ? fallback : key;
        for (const [k, v] of Object.entries(opts ?? {})) {
            s = s.replace(new RegExp(`{{${k}}}`, 'g'), String(v));
        }
        return s;
    };
    return { useTranslation: () => ({ t, i18n: { language: 'en' } }) };
});

vi.mock('../../../Services/advisorService', () => ({
    advisorService: {
        getFeed: vi.fn(),
        getHost: vi.fn(),
        getRuleHosts: vi.fn(),
        listProposals: vi.fn(),
        approveProposal: vi.fn(),
        rejectProposal: vi.fn(),
        listPacks: vi.fn(),
        choosePack: vi.fn(),
        evaluate: vi.fn(),
    },
}));

import { advisorService } from '../../../Services/advisorService';
import type { AdvisorFeed, AdvisorHostView, AdvisorProposal } from '../../../Services/advisorService';
import AdvisorScoreSummary from '../AdvisorScoreSummary';
import AdvisorRuleTable from '../AdvisorRuleTable';
import AdvisorProposalList from '../AdvisorProposalList';
import HostAdvisorTab from '../../HostDetail/HostAdvisorTab';
import Advisor from '../../../Pages/Advisor';

const svc = advisorService as unknown as Record<string, ReturnType<typeof vi.fn>>;

const FEED: AdvisorFeed = {
    fleet: {
        total_hosts: 6, assessed_hosts: 1, unknown_hosts: 5, incomplete_hosts: 1,
        average_score: 48, max_score: 48, level: 'MEDIUM',
        hosts_by_level: { CRITICAL: 0, HIGH: 0, MEDIUM: 1, LOW: 0, NONE: 0, UNKNOWN: 5 },
    },
    totals: { findings: 2, not_assessable: 47, not_applicable: 1, clean: 16 },
    rules: [
        {
            source: 'shared', key: 'SM-SEC-003', risk: null,
            rule: { source: 'shared', key: 'SM-SEC-003', title: 'Account other than root with user ID 0',
                lens: 'security', scope: 'host', impact: 5, likelihood: 3, errors: [] },
            hosts_firing: 0, hosts_not_assessable: 5, hosts_not_applicable: 0, hosts_clean: 1,
            gap_reasons: { columns_not_advertised: 5 },
        },
    ],
};

const PROPOSAL: AdvisorProposal = {
    id: 'p1', host_id: 'h1', fqdn: 'gdr-t14', source: 'shared', key: 'SM-AVAIL-001',
    kind: 'generate', profile_name: null, engine: 'ansible-core', content: '- hosts: all\n',
    packages: ['libvirt-clients', 'openssl'], skipped: 6, status: 'proposed', reason: null,
    created_at: null, decided_by: null, decided_at: null, command_id: null, run: null,
};

beforeEach(() => {
    vi.clearAllMocks();
});

describe('AdvisorScoreSummary', () => {
    test('an unassessed host has no grade and says so -- never a clean one', () => {
        render(<AdvisorScoreSummary host={{ score: null, level: 'UNKNOWN', complete: false,
            counts: { fires: 0, does_not_fire: 3, not_assessable: 2, not_applicable: 0 }, worst_risk: null }} />);
        expect(screen.getByText('Not assessed')).toBeInTheDocument();
        expect(screen.getByText('--')).toBeInTheDocument();
        expect(screen.getByText(/could not be fully assessed/)).toBeInTheDocument();
        expect(screen.queryByText('No findings')).not.toBeInTheDocument();
    });

    test('the fleet shows its unassessed hosts beside the average', () => {
        render(<AdvisorScoreSummary fleet={FEED.fleet} />);
        expect(screen.getByText('1 of 6 hosts assessed')).toBeInTheDocument();
        expect(screen.getByText(/5 hosts could not be assessed/)).toBeInTheDocument();
        expect(screen.getByText(/1 hosts were only partly assessed/)).toBeInTheDocument();
    });

    test('a partly assessed host is marked as a minimum', () => {
        render(<AdvisorScoreSummary host={{ score: 48, level: 'MEDIUM', complete: false,
            counts: { fires: 2, does_not_fire: 0, not_assessable: 1, not_applicable: 0 }, worst_risk: 12 }} />);
        expect(screen.getByText(/this score is a minimum/)).toBeInTheDocument();
    });
});

describe('AdvisorRuleTable', () => {
    test('not assessable is a column with its reasons', () => {
        render(<MemoryRouter><AdvisorRuleTable rules={FEED.rules} /></MemoryRouter>);
        const row = screen.getByText('Account other than root with user ID 0').closest('tr')!;
        expect(within(row).getByText('5')).toBeInTheDocument();
        expect(within(row).getByText('agent too old to report the needed columns (5)')).toBeInTheDocument();
    });

    test('expanding a rule lists its hosts with what is missing', async () => {
        svc.getRuleHosts.mockResolvedValue({ rule: null, hosts: [
            { source: 'shared', key: 'SM-SEC-003', title: null, lens: null, outcome: 'not_assessable',
                impact: 5, likelihood: 3, risk: null, evaluated_at: null, host_id: 'h2', fqdn: 't480',
                gaps: [{ evidence: 'facts.users', reason: 'columns_not_advertised' }] },
            { source: 'shared', key: 'SM-SEC-003', title: null, lens: null, outcome: 'does_not_fire',
                impact: 5, likelihood: 3, risk: null, evaluated_at: null, host_id: 'h1', fqdn: 'gdr-t14' },
        ] });
        render(<MemoryRouter><AdvisorRuleTable rules={FEED.rules} /></MemoryRouter>);
        fireEvent.click(screen.getByLabelText('Show hosts'));
        expect(await screen.findByText('t480')).toBeInTheDocument();
        expect(screen.getByText('Facts: users: agent too old to report the needed columns')).toBeInTheDocument();
        expect(screen.queryByText('gdr-t14')).not.toBeInTheDocument();
    });

    test('an empty feed says nothing was evaluated, not that all is well', () => {
        render(<MemoryRouter><AdvisorRuleTable rules={[]} /></MemoryRouter>);
        expect(screen.getByText(/No rules have been evaluated yet/)).toBeInTheDocument();
    });
});

describe('AdvisorProposalList', () => {
    test('review shows exactly what would run, including what was left out', () => {
        render(<AdvisorProposalList proposals={[PROPOSAL]} onChanged={vi.fn()} />);
        fireEvent.click(screen.getByText('Review'));
        expect(screen.getByText('libvirt-clients, openssl')).toBeInTheDocument();
        expect(screen.getByText(/6 matched items were left out/)).toBeInTheDocument();
        expect(screen.getByText(/administrative rights/)).toBeInTheDocument();
    });

    test('approve goes to the server and refreshes', async () => {
        const onChanged = vi.fn();
        svc.approveProposal.mockResolvedValue({ ...PROPOSAL, status: 'approved' });
        render(<AdvisorProposalList proposals={[PROPOSAL]} onChanged={onChanged} />);
        fireEvent.click(screen.getByText('Review'));
        fireEvent.click(screen.getByText('Approve'));
        await waitFor(() => expect(onChanged).toHaveBeenCalled());
        expect(svc.approveProposal).toHaveBeenCalledWith('p1');
    });

    test('a refused approval explains why', async () => {
        svc.approveProposal.mockRejectedValue({ response: { data: { detail: { reason: 'not_queued' } } } });
        render(<AdvisorProposalList proposals={[PROPOSAL]} onChanged={vi.fn()} />);
        fireEvent.click(screen.getByText('Review'));
        fireEvent.click(screen.getByText('Approve'));
        expect(await screen.findByText('the host could not take the command')).toBeInTheDocument();
    });

    test('an approved fix is queued, not applied, until its run returns', () => {
        render(<AdvisorProposalList proposals={[{ ...PROPOSAL, status: 'approved', command_id: 'c' }]}
            onChanged={vi.fn()} />);
        expect(screen.getByText(/Queued -- waiting for the host/)).toBeInTheDocument();
    });
});

describe('HostAdvisorTab', () => {
    const VIEW: AdvisorHostView = {
        host_id: 'h1', fqdn: 'gdr-t14',
        score: { score: 48, level: 'MEDIUM', complete: false,
            counts: { fires: 1, does_not_fire: 0, not_assessable: 1, not_applicable: 0 }, worst_risk: 12 },
        findings: [{ source: 'shared', key: 'SM-SEC-002', title: 'High-severity vulnerability with a fix available',
            lens: 'security', outcome: 'fires', impact: 4, likelihood: 3, risk: 12, evaluated_at: null,
            match_count: 1, remediation: ['Upgrade mailcap from 3.70 to 3.75'], proposal: null }],
        not_assessable: [{ source: 'shared', key: 'SM-STAB-001', title: 'Configuration drift unresolved for more than 7 days',
            lens: 'stability', outcome: 'not_assessable', impact: 3, likelihood: 3, risk: null, evaluated_at: null,
            gaps: [{ evidence: 'drift', reason: 'stale', age_days: 12, max_age_days: 7 }] }],
        not_applicable: [],
        clean: [],
    };

    test('findings and what could not be assessed are both shown, with reasons', async () => {
        svc.getHost.mockResolvedValue(VIEW);
        svc.listProposals.mockResolvedValue([]);
        render(<HostAdvisorTab hostId="h1" />);
        expect(await screen.findByText('Upgrade mailcap from 3.70 to 3.75')).toBeInTheDocument();
        expect(screen.getByText('Not assessable (1)')).toBeInTheDocument();
        expect(screen.getByText('Configuration drift check: too old to trust')).toBeInTheDocument();
    });

    test('a host never evaluated says so', async () => {
        svc.getHost.mockResolvedValue({ ...VIEW, findings: [], not_assessable: [],
            score: { ...VIEW.score, score: null, level: 'UNKNOWN' } });
        svc.listProposals.mockResolvedValue([]);
        render(<HostAdvisorTab hostId="h1" />);
        expect(await screen.findByText('The advisor has not evaluated this host yet.')).toBeInTheDocument();
    });
});

describe('Advisor page', () => {
    test('loads the fleet and evaluates on request', async () => {
        svc.getFeed.mockResolvedValue(FEED);
        svc.listProposals.mockResolvedValue([PROPOSAL]);
        svc.listPacks.mockResolvedValue([]);
        svc.evaluate.mockResolvedValue({});
        render(<MemoryRouter><Advisor /></MemoryRouter>);
        expect(await screen.findByText('2 findings')).toBeInTheDocument();
        expect(screen.getByText('47 not assessable')).toBeInTheDocument();
        expect(screen.getByText('Proposed fixes (1)')).toBeInTheDocument();
        fireEvent.click(screen.getByText('Evaluate now'));
        await waitFor(() => expect(svc.evaluate).toHaveBeenCalled());
    });
});
