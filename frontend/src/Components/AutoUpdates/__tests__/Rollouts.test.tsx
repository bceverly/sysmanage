// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Fleet-by-fleet rollout UI (ROADMAP 26.4): the policy form lists the
// fleets in order with their tags and soak times, and the rollouts card
// shows the fleet in progress, why a rollout halted and which hosts caused
// it, and resumes or cancels only with a reason.

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('../../../Services/autoUpdates', () => ({
  autoUpdatesService: {
    rollouts: vi.fn(),
    resumeRollout: vi.fn(),
    cancelRollout: vi.fn(),
  },
}));

import { autoUpdatesService } from '../../../Services/autoUpdates';
import RolloutFields, { stagesToSend } from '../RolloutFields';
import RolloutsCard from '../RolloutsCard';

const svc = autoUpdatesService as unknown as Record<string, ReturnType<typeof vi.fn>>;
const TAGS = [{ id: 't1', name: 'canary' }, { id: 't2', name: 'web' }];
const FORM = { rollout_enabled: false, rollout_max_failure_pct: 0, rollout_stages: [] };

const host = (id: string, status: string | null, over = {}) => ({
  host_id: id, hostname: `${id}.lab`, run_id: status ? `r-${id}` : null, status,
  reason: null, reboot_status: 'none', release_at: null, ...over,
});

const rollout = (over = {}) => ({
  id: 'ro1', profile_id: 'p1', profile_name: 'Nightly security', status: 'halted',
  stage_index: 0, triggered_by: null, started_at: '2026-11-17T03:00:00',
  completed_at: null, halt_reason: 'run_failures',
  halt_detail: { stage: 0, culprits: ['a'] }, halted_at: '2026-11-17T03:20:00',
  ended_by: null, end_reason: null,
  stages: [
    { name: 'Canary', tag_id: 't1', soak_minutes: 60, host_ids: ['a'], status: 'halted',
      started_at: '2026-11-17T03:00:00', finished_at: null,
      counts: { hosts: 1, applied: 0, failed: 1, in_flight: 0, other: 0 },
      hosts: [host('a', 'failed')] },
    { name: 'Web', tag_id: 't2', soak_minutes: 0, host_ids: ['b', 'c'], status: 'pending',
      started_at: null, finished_at: null, hosts: [host('b', null), host('c', null)] },
  ],
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RolloutFields', () => {
  test('turning the rollout on starts with a canary fleet', () => {
    const setForm = vi.fn();
    render(<RolloutFields form={FORM} setForm={setForm} tags={TAGS} />);
    fireEvent.click(screen.getByLabelText('Roll out fleet by fleet'));
    const last = setForm.mock.calls.at(-1)?.[0];
    expect(last.rollout_stages).toMatchObject([{ name: 'Canary fleet', tag_id: '', soak_hours: 24 }]);
    // A stable client-side key, since fleets can be reordered (stripped on save).
    expect(last.rollout_stages[0].uid).toMatch(/^fleet-/);
  });

  test('fleets can be reordered and removed', () => {
    const setForm = vi.fn();
    const form = {
      ...FORM,
      rollout_enabled: true,
      rollout_stages: [
        { name: 'Canary', tag_id: 't1', soak_hours: 24 },
        { name: 'Web', tag_id: 't2', soak_hours: 0 },
      ],
    };
    render(<RolloutFields form={form} setForm={setForm} tags={TAGS} />);
    fireEvent.click(screen.getAllByRole('button', { name: 'Move later' })[0]);
    expect(setForm.mock.calls.at(-1)?.[0].rollout_stages.map((s: { name: string }) => s.name))
      .toEqual(['Web', 'Canary']);
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove this fleet' })[1]);
    expect(setForm.mock.calls.at(-1)?.[0].rollout_stages).toHaveLength(1);
  });

  test('the failure share is clamped to 0-100', () => {
    const setForm = vi.fn();
    render(<RolloutFields form={{ ...FORM, rollout_enabled: true }} setForm={setForm} tags={TAGS} />);
    fireEvent.change(
      screen.getByLabelText('Halt when more than this share of a fleet fails (%)'),
      { target: { value: '250' } },
    );
    expect(setForm).toHaveBeenCalledWith(expect.objectContaining({ rollout_max_failure_pct: 100 }));
  });
});

describe('RolloutsCard', () => {
  test('a halted rollout says why and names the hosts that caused it', async () => {
    svc.rollouts.mockResolvedValue([rollout()]);
    render(<RolloutsCard />);
    expect(await screen.findByText(/Halted at Canary: too many runs in this fleet failed \(a\.lab\)/))
      .toBeTruthy();
    expect(screen.getByText('Halted here')).toBeTruthy();
    expect(screen.getByText('Not started')).toBeTruthy();
  });

  test('resuming needs a reason', async () => {
    svc.rollouts.mockResolvedValue([rollout()]);
    svc.resumeRollout.mockResolvedValue(rollout({ status: 'running' }));
    const prompt = vi.spyOn(globalThis, 'prompt').mockReturnValueOnce('').mockReturnValueOnce('mirror was down');
    render(<RolloutsCard />);
    fireEvent.click(await screen.findByText('Resume'));
    expect(svc.resumeRollout).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Resume'));
    await waitFor(() => expect(svc.resumeRollout).toHaveBeenCalledWith('ro1', 'mirror was down'));
    prompt.mockRestore();
  });

  test('a fleet in progress shows each host and why it has not applied', async () => {
    const running = rollout({
      status: 'running', stage_index: 1, halt_reason: null, halt_detail: {},
      stages: [
        { ...rollout().stages[0], status: 'done', hosts: [host('a', 'succeeded')] },
        { ...rollout().stages[1], status: 'running',
          counts: { hosts: 2, applied: 0, failed: 0, in_flight: 1, other: 1 },
          hosts: [host('b', 'waiting', { release_at: '2026-11-18T02:00:00' }),
                  host('c', 'skipped', { reason: 'opted_out' })] },
      ],
    });
    svc.rollouts.mockResolvedValue([running]);
    render(<RolloutsCard />);
    expect(await screen.findByText('the host never updates automatically')).toBeTruthy();
    expect(screen.getByText(/0 applied, 0 failed, 1 in progress, 1 not applied/)).toBeTruthy();
    expect(screen.queryByText('Resume')).toBeNull();
  });

  test('without the Enterprise engine nothing is shown', async () => {
    svc.rollouts.mockRejectedValue(new Error('402'));
    const { container } = render(<RolloutsCard />);
    await waitFor(() => expect(svc.rollouts).toHaveBeenCalled());
    expect(container.textContent).toBe('');
  });
});

describe('what a save sends (production, 2026-11-24)', () => {
  test('rollout off: the untagged fleet the checkbox added is not sent', () => {
    const canary = { uid: 'fleet-1', name: 'Canary fleet', tag_id: '', soak_hours: 24 };
    const done = { uid: 'fleet-2', name: ' Desktops ', tag_id: 't1', soak_hours: 0 };
    expect(stagesToSend(false, [canary, done])).toEqual([
      { name: 'Desktops', tag_id: 't1', soak_hours: 0 },
    ]);
    // On, everything goes, so an unfinished fleet is caught and said.
    expect(stagesToSend(true, [canary])).toEqual([
      { name: 'Canary fleet', tag_id: '', soak_hours: 24 },
    ]);
  });
});
