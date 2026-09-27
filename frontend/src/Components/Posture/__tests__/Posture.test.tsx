// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The posture UI (Phase 21.4 S7). What is under test is the phase's promise:
// the wizard asks exactly what the engine derives from (branches cascade, a
// closed branch's answer is never saved), and the punch list never shows an
// accepted or unmeasured risk as a pass.

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

vi.mock('../../../Services/postureService', async () => {
    const actual = await vi.importActual<typeof import('../../../Services/postureService')>('../../../Services/postureService');
    return {
        ...actual,
        postureService: {
            getQuestionnaire: vi.fn(),
            getThreatModel: vi.fn(),
            saveThreatModel: vi.fn(),
            getDiff: vi.fn(),
            getPosture: vi.fn(),
            getHistory: vi.fn(),
            waive: vi.fn(),
            revokeWaiver: vi.fn(),
            reaffirmWaiver: vi.fn(),
            previewRemedy: vi.fn(),
            applyRemedy: vi.fn(),
        },
    };
});

import { postureService } from '../../../Services/postureService';
import type { PostureItem, Questionnaire, ThreatModel } from '../../../Services/postureService';
import { visibleAnswers, visibleQuestions } from '../threatModelLogic';
import { stateColor } from '../postureLabels';
import ThreatModelWizard from '../ThreatModelWizard';
import PostureTab from '../PostureTab';
import RemedyDialog from '../RemedyDialog';
import WaiverDialog from '../WaiverDialog';

const svc = postureService as unknown as Record<string, ReturnType<typeof vi.fn>>;

// A cut of the curated questionnaire with the same branching.
const Q: Questionnaire = {
    id: 'sysmanage-threat-model',
    version: 1,
    attributes: {},
    questions: [
        { id: 'org', kind: 'one', options: [{ id: 'homelab' }, { id: 'public_sector' }] },
        { id: 'data', kind: 'many', options: [{ id: 'none_sensitive' }, { id: 'personal' }] },
        {
            id: 'regs', kind: 'many',
            show_if: { any_of: { data: ['personal'] } },
            options: [{ id: 'gdpr' }, { id: 'cmmc_800_171' }],
        },
        {
            id: 'fips', kind: 'one',
            show_if: { any_of: { org: ['public_sector'], regs: ['cmmc_800_171'] } },
            options: [{ id: 'yes' }, { id: 'no' }],
        },
    ],
};

const MODEL: ThreatModel = {
    id: 'm1', model_version: 1, questionnaire: Q.id, questionnaire_version: 1,
    attributes: { regulated: false, internet_exposed: true }, answers: { org: 'homelab' },
    digest: 'd', complete: true, missing: [], ignored: [], created_by: 'admin@example.com',
    created_at: '2026-09-26T10:00:00Z',
};

const item = (over: Partial<PostureItem>): PostureItem => ({
    rule_key: 'PM-FIREWALL', rule_source: 'shared', rule_version: 1,
    state: 'open', evaluated_state: 'open', waiver: null,
    remedy: 'enable_firewall', remedy_kind: 'fleet', remedy_target: null, outcome: 'finding',
    managed_by: 'tenant', impact: 3, likelihood: 3, risk: 9, gaps: [], coverage: null,
    evaluated_at: null, state_changed_at: null, evaluated_under_current_model: true, regressed: false,
    ...over,
});

beforeEach(() => {
    vi.clearAllMocks();
    svc.getHistory.mockResolvedValue([]);
});

describe('threat model branching', () => {
    test('a branch opens only when an earlier answer calls for it', () => {
        expect(visibleQuestions(Q, { data: ['none_sensitive'] }).map(q => q.id)).toEqual(['org', 'data']);
        expect(visibleQuestions(Q, { data: ['personal'] }).map(q => q.id)).toEqual(['org', 'data', 'regs']);
    });

    test('visibility cascades: a hidden question cannot open a later one', () => {
        // regs answered cmmc but hidden (no personal data): fips must stay hidden.
        const answers = { org: 'homelab', data: ['none_sensitive'], regs: ['cmmc_800_171'] };
        expect(visibleQuestions(Q, answers).map(q => q.id)).not.toContain('fips');
    });

    test('a closed branch never carries its old answer into the save', () => {
        const answers = { org: 'homelab', data: ['none_sensitive'], regs: ['gdpr'] };
        expect(visibleAnswers(Q, answers)).toEqual({ org: 'homelab', data: ['none_sensitive'] });
    });
});

describe('ThreatModelWizard', () => {
    test('asks one question per step and saves only the visible answers', async () => {
        svc.saveThreatModel.mockResolvedValue({ threat_model: MODEL, changes: { attributes_on: [], attributes_off: [], answers_changed: [] } });
        const onSaved = vi.fn();
        render(<ThreatModelWizard open questionnaire={Q} initial={{ regs: ['gdpr'] }} onClose={vi.fn()} onSaved={onSaved} />);

        expect(screen.getByText('Question 1 of 2')).toBeTruthy();
        const next = screen.getByRole('button', { name: 'Next' }) as HTMLButtonElement;
        expect(next.disabled).toBe(true);
        fireEvent.click(screen.getByLabelText('A home lab or personal systems'));
        fireEvent.click(screen.getByRole('button', { name: 'Next' }));
        fireEvent.click(screen.getByLabelText('Nothing sensitive'));
        fireEvent.click(screen.getByRole('button', { name: 'Save threat model' }));

        await waitFor(() => expect(onSaved).toHaveBeenCalled());
        expect(svc.saveThreatModel).toHaveBeenCalledWith({ org: 'homelab', data: ['none_sensitive'] });
    });
});

describe('posture states', () => {
    test('neither a waived nor an unmeasured item is ever green', () => {
        expect(stateColor('satisfied')).toBe('success');
        expect(stateColor('waived')).not.toBe('success');
        expect(stateColor('not_assessable')).not.toBe('success');
    });
});

describe('PostureTab', () => {
    const renderTab = () => render(<MemoryRouter><PostureTab /></MemoryRouter>);

    test('without a threat model it asks for one', async () => {
        svc.getQuestionnaire.mockResolvedValue(Q);
        svc.getThreatModel.mockResolvedValue({ current: null, versions: [] });
        svc.getPosture.mockResolvedValue({ threat_model: null, totals: {}, items: [] });
        renderTab();
        expect(await screen.findByText('Describe your installation first')).toBeTruthy();
    });

    test('renders every state, the regression and server-managed markers, and only sensible actions', async () => {
        svc.getQuestionnaire.mockResolvedValue(Q);
        svc.getThreatModel.mockResolvedValue({ current: MODEL, versions: [] });
        svc.getPosture.mockResolvedValue({
            threat_model: MODEL,
            totals: { open: 1, waived: 1, not_assessable: 1, satisfied: 1 },
            items: [
                item({ regressed: true }),
                item({
                    rule_key: 'PM-FIPS', state: 'waived', evaluated_state: 'open',
                    waiver: {
                        id: 'w', reason: 'lab', granted_by: 'admin@example.com', granted_at: null,
                        reaffirmed_by: null, reaffirmed_at: null, stale_reason: null, stale_since: null,
                        risk: 9, rule_version: 1, basis_attributes: {},
                    },
                }),
                item({
                    rule_key: 'PM-LOCKOUT', state: 'not_assessable', evaluated_state: 'not_assessable',
                    remedy: 'enforce_lockout', remedy_kind: 'setting', managed_by: 'server',
                    gaps: [{ evidence: 'identity', reason: 'unavailable' }],
                }),
                item({ rule_key: 'PM-SECRETS', state: 'satisfied', evaluated_state: 'satisfied', remedy: 'enable_openbao', remedy_kind: 'guided' }),
            ],
        });
        renderTab();
        const firewall = (await screen.findByText("Every host's firewall is on")).closest('tr')!;
        expect(within(firewall).getByText('Regressed')).toBeTruthy();
        expect(within(firewall).getByRole('button', { name: 'Fix' })).toBeTruthy();
        expect(within(firewall).getByRole('button', { name: 'Waive' })).toBeTruthy();

        const fips = screen.getByText('FIPS mode is on wherever it is available').closest('tr')!;
        expect(within(fips).getByText('Waived')).toBeTruthy();
        expect(within(fips).queryByRole('button', { name: 'Waive' })).toBeNull();

        const lockout = screen.getByText('Repeated failed logins lock the account').closest('tr')!;
        expect(within(lockout).getByText('Not assessable')).toBeTruthy();
        expect(within(lockout).getByText('Managed by the server operator')).toBeTruthy();
        expect(within(lockout).queryByRole('button', { name: 'Fix' })).toBeNull();

        const secrets = screen.getByText('Secrets are kept in OpenBAO').closest('tr')!;
        expect(within(secrets).queryByRole('button')).not.toBeNull(); // only the expander
        expect(within(secrets).queryByRole('button', { name: 'Fix' })).toBeNull();
    });
});

describe('RemedyDialog', () => {
    const renderDialog = (over: Partial<PostureItem> = {}) =>
        render(<MemoryRouter><RemedyDialog item={item(over)} onClose={vi.fn()} onApplied={vi.fn()} /></MemoryRouter>);

    test('previews the hosts before applying a fleet fix', async () => {
        svc.previewRemedy.mockResolvedValue({
            remedy: 'enable_firewall', kind: 'fleet', available: true, unavailable_reason: null,
            target: null, changes: [], hosts: [{ id: 'h1', fqdn: 'netbsd.lan' }],
        });
        svc.applyRemedy.mockResolvedValue({ applied: true, changes: [], hosts: [], failed: [] });
        renderDialog();
        expect(await screen.findByText('netbsd.lan')).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Apply fix' }));
        await waitFor(() => expect(svc.applyRemedy).toHaveBeenCalledWith('PM-FIREWALL'));
    });

    test('a guided fix links to its screen and cannot be applied', async () => {
        svc.previewRemedy.mockResolvedValue({
            remedy: 'enable_openbao', kind: 'guided', available: false, unavailable_reason: 'not_automated',
            target: 'secrets', changes: [], hosts: [],
        });
        renderDialog({ rule_key: 'PM-SECRETS', remedy: 'enable_openbao', remedy_kind: 'guided' });
        expect(await screen.findByRole('button', { name: 'Go there' })).toBeTruthy();
        expect(screen.queryByRole('button', { name: 'Apply fix' })).toBeNull();
    });

    test('a withheld fix says why', async () => {
        svc.previewRemedy.mockResolvedValue({
            remedy: 'enforce_lockout', kind: 'setting', available: false, unavailable_reason: 'managed_by_server',
            target: null, changes: [], hosts: [],
        });
        renderDialog({ rule_key: 'PM-LOCKOUT', remedy: 'enforce_lockout', remedy_kind: 'setting' });
        expect(await screen.findByText('Only the server operator can change this setting.')).toBeTruthy();
        expect((screen.getByRole('button', { name: 'Apply fix' }) as HTMLButtonElement).disabled).toBe(true);
    });
});

describe('WaiverDialog', () => {
    test('a waiver needs a reason', async () => {
        svc.waive.mockResolvedValue({});
        const onDone = vi.fn();
        render(<WaiverDialog item={item({})} mode="waive" onClose={vi.fn()} onDone={onDone} />);
        const submit = screen.getByRole('button', { name: 'Waive' }) as HTMLButtonElement;
        expect(submit.disabled).toBe(true);
        fireEvent.change(screen.getByRole('textbox'), { target: { value: '  lab only  ' } });
        fireEvent.click(screen.getByRole('button', { name: 'Waive' }));
        await waitFor(() => expect(onDone).toHaveBeenCalled());
        expect(svc.waive).toHaveBeenCalledWith('PM-FIREWALL', 'lab only');
    });
});
