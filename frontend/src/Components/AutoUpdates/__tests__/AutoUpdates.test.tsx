// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Automatic updates UI (ROADMAP 26.1): the host card says which policy a
// host follows and why, an opt-out needs a reason, a hold needs a reason,
// and without the Enterprise engine nothing is shown.  26.2/26.3: a run
// waiting for its window says when it starts, and each pending update says
// when it becomes eligible and why.

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
    host: vi.fn(),
    optOut: vi.fn(),
    settings: vi.fn(),
    runs: vi.fn(),
    holdAll: vi.fn(),
    acknowledge: vi.fn(),
    updateSettings: vi.fn(),
  },
}));

import { autoUpdatesService } from '../../../Services/autoUpdates';
import HostAutoUpdatesCard from '../HostAutoUpdatesCard';
import AutoUpdatesPanel from '../AutoUpdatesPanel';
import AutomaticFields from '../AutomaticFields';

const svc = autoUpdatesService as unknown as Record<string, ReturnType<typeof vi.fn>>;

const run = (over = {}) => ({
  id: 'r1', profile_id: 'p1', profile_name: 'Nightly security', host_id: 'h1',
  hostname: 'web1', status: 'partial', reason: null, triggered_by: null,
  packages: [{ package_name: 'openssl', package_manager: 'apt' }, { package_name: 'curl', package_manager: 'apt' }],
  skipped: [{ package_name: 'postgresql-16', package_manager: 'apt', reason: 'held' }],
  applied_count: 1, failed_count: 1,
  failures: [{ package_name: 'curl', package_manager: 'apt', error: 'E: broken' }],
  reboot_needed: true, reboot_status: 'not_back', queued_at: '2026-11-16T03:00:00',
  release_at: null, completed_at: null, acknowledged_by: null, acknowledged_at: null,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('HostAutoUpdatesCard', () => {
  test('says which policy the host follows and why, and shows its runs', async () => {
    svc.host.mockResolvedValue({
      host_id: 'h1', opt_out: false, opt_out_reason: null, hold_all: false,
      policy: { id: 'p1', name: 'Nightly security', rule: 'more_specific', candidates: ['p0', 'p1'] },
      runs: [run()],
    });
    render(<HostAutoUpdatesCard hostId="h1" canManage />);
    expect(await screen.findByText(/Follows "Nightly security": the most specific policy/)).toBeTruthy();
    expect(screen.getByText('Partly failed')).toBeTruthy();
    expect(screen.getByText('Did not come back from its reboot')).toBeTruthy();
    expect(screen.getByText('postgresql-16: held on the host')).toBeTruthy();
    expect(screen.getByText('curl: E: broken')).toBeTruthy();
  });

  test('opting out asks why, and sends the reason', async () => {
    svc.host.mockResolvedValue({ host_id: 'h1', opt_out: false, opt_out_reason: null, hold_all: false, policy: null, runs: [] });
    svc.optOut.mockResolvedValue({});
    vi.spyOn(globalThis, 'prompt').mockReturnValue('production database');
    render(<HostAutoUpdatesCard hostId="h1" canManage />);
    fireEvent.click(await screen.findByRole('switch'));
    await waitFor(() => expect(svc.optOut).toHaveBeenCalledWith('h1', true, 'production database'));
  });

  test('no reason, no opt-out', async () => {
    svc.host.mockResolvedValue({ host_id: 'h1', opt_out: false, opt_out_reason: null, hold_all: false, policy: null, runs: [] });
    vi.spyOn(globalThis, 'prompt').mockReturnValue('  ');
    render(<HostAutoUpdatesCard hostId="h1" canManage />);
    fireEvent.click(await screen.findByRole('switch'));
    expect(svc.optOut).not.toHaveBeenCalled();
  });

  test('without the Enterprise engine there is nothing to show', async () => {
    svc.host.mockRejectedValue({ response: { status: 402 } });
    const { container } = render(<HostAutoUpdatesCard hostId="h1" canManage />);
    await waitFor(() => expect(svc.host).toHaveBeenCalled());
    expect(container.innerHTML).toBe('');
  });
});

describe('AutoUpdatesPanel', () => {
  test('lists the runs that need attention, and acknowledges one', async () => {
    svc.settings.mockResolvedValue({ hold_all: false, hold_reason: null, hold_by: null, hold_at: null, retry_after_hours: 24, reboot_timeout_minutes: 30 });
    svc.runs.mockResolvedValue([run(), run({ id: 'r2', status: 'succeeded', reboot_status: 'none' })]);
    svc.acknowledge.mockResolvedValue({});
    render(<AutoUpdatesPanel />);
    expect(await screen.findByText(/web1 -- Nightly security/)).toBeTruthy();
    expect(screen.getAllByText('Acknowledge')).toHaveLength(1);
    fireEvent.click(screen.getByText('Acknowledge'));
    await waitFor(() => expect(svc.acknowledge).toHaveBeenCalledWith('r1'));
  });

  test('holding every policy asks why', async () => {
    svc.settings.mockResolvedValue({ hold_all: false, hold_reason: null, hold_by: null, hold_at: null, retry_after_hours: 24, reboot_timeout_minutes: 30 });
    svc.runs.mockResolvedValue([]);
    svc.holdAll.mockResolvedValue({});
    vi.spyOn(globalThis, 'prompt').mockReturnValue('change freeze');
    render(<AutoUpdatesPanel />);
    fireEvent.click(await screen.findByRole('switch'));
    await waitFor(() => expect(svc.holdAll).toHaveBeenCalledWith(true, 'change freeze'));
  });
});

const FORM = {
  auto_apply: false, reboot_mode: 'never' as const, excluded_packages: '',
  require_backup_hours: '' as const, host_ids: [], wait_days_regular: 0,
  wait_days_critical: 0, critical_source: 'either' as const,
};

describe('26.2 and 26.3 on the host card', () => {
  const view = (over = {}) => ({
    host_id: 'h1', opt_out: false, opt_out_reason: null, hold_all: false,
    policy: { id: 'p1', name: 'Nightly', rule: 'only', candidates: ['p1'],
              wait_days_regular: 7, wait_days_critical: 0 },
    runs: [], ...over,
  });

  test('a run waiting for its window says when it starts', async () => {
    svc.host.mockResolvedValue(view({
      runs: [run({ status: 'waiting', reboot_status: 'none', release_at: '2026-11-22T02:00:00',
                   skipped: [], failures: [], applied_count: 0, failed_count: 0 })],
      window: { state: 'blocked', active_blackout: null,
                next_window: { id: 'w1', name: 'Sunday 2am', starts_at: '2026-11-22T02:00:00' } },
    }));
    render(<HostAutoUpdatesCard hostId="h1" canManage />);
    expect(await screen.findByText('Waiting for its window')).toBeTruthy();
    expect(screen.getByText(/Starts when its window opens/)).toBeTruthy();
    expect(screen.getByText(/Next: "Sunday 2am"/)).toBeTruthy();
  });

  test('a blackout says nothing is applied', async () => {
    svc.host.mockResolvedValue(view({
      window: { state: 'blocked', active_blackout: 'Quarter end', next_window: null },
    }));
    render(<HostAutoUpdatesCard hostId="h1" canManage />);
    expect(await screen.findByText(/In the blackout "Quarter end"/)).toBeTruthy();
  });

  test('each pending update says when it becomes eligible and why', async () => {
    svc.host.mockResolvedValue(view({
      pending: {
        sources: { vulnerability: true, advisory: false }, critical_threshold: 'critical',
        updates: [
          { package_name: 'openssl', package_manager: 'apt', reason: null, kind: 'critical',
            fix_id: 'CVE-2026-1234', eligible_at: null },
          { package_name: 'vim', package_manager: 'apt', reason: 'waiting_period', kind: 'regular',
            fix_id: null, eligible_at: '2026-11-23T03:00:00' },
          { package_name: 'postgresql-16', package_manager: 'apt', reason: 'held' },
        ],
      },
    }));
    render(<HostAutoUpdatesCard hostId="h1" canManage />);
    expect(await screen.findByText('critical CVE-2026-1234: eligible now')).toBeTruthy();
    expect(screen.getByText(/^regular: eligible on /)).toBeTruthy();
    expect(screen.getByText('held on the host')).toBeTruthy();
    expect(screen.queryByText(/no vulnerability scan or vendor advisories/)).toBeNull();
  });

  test('without CVE data the host says every patch waits the regular count', async () => {
    svc.host.mockResolvedValue(view({
      pending: { sources: { vulnerability: false, advisory: false }, critical_threshold: 'critical',
                 updates: [] },
    }));
    render(<HostAutoUpdatesCard hostId="h1" canManage />);
    expect(await screen.findByText(/every patch on it waits the regular count/)).toBeTruthy();
  });
});

describe('the critical threshold', () => {
  test('is a tenant setting on the panel', async () => {
    svc.settings.mockResolvedValue({ hold_all: false, hold_reason: null, hold_by: null, hold_at: null,
                                     retry_after_hours: 24, reboot_timeout_minutes: 30,
                                     critical_threshold: 'critical' });
    svc.runs.mockResolvedValue([]);
    svc.updateSettings.mockResolvedValue({});
    render(<AutoUpdatesPanel />);
    fireEvent.mouseDown(await screen.findByLabelText('A patch is critical when it fixes a CVE rated'));
    fireEvent.click(await screen.findByText('High or critical'));
    await waitFor(() => expect(svc.updateSettings).toHaveBeenCalledWith({ critical_threshold: 'high' }));
  });
});

describe('AutomaticFields', () => {
  test('the waiting periods and the in-window reboot are part of the policy', () => {
    const setForm = vi.fn();
    render(<AutomaticFields form={{ ...FORM, auto_apply: true }} setForm={setForm} hosts={[]} />);
    fireEvent.change(screen.getByLabelText('Wait before applying a regular patch (days)'), {
      target: { value: '7' },
    });
    expect(setForm).toHaveBeenCalledWith(expect.objectContaining({ wait_days_regular: 7 }));
    fireEvent.change(
      screen.getByLabelText('Wait before applying a patch that fixes a critical CVE (days)'),
      { target: { value: '-3' } },
    );
    expect(setForm).toHaveBeenCalledWith(expect.objectContaining({ wait_days_critical: 0 }));
    fireEvent.mouseDown(screen.getByLabelText('Reboots'));
    fireEvent.click(screen.getByText('Reboot when needed, only inside a maintenance window'));
    expect(setForm).toHaveBeenCalledWith(expect.objectContaining({ reboot_mode: 'in_window' }));
  });

  test('the automatic settings appear only with "apply automatically" on', () => {
    const form = { ...FORM };
    const setForm = vi.fn();
    const { rerender } = render(<AutomaticFields form={form} setForm={setForm} hosts={[]} />);
    expect(screen.queryByLabelText('Never apply these packages')).toBeNull();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(setForm).toHaveBeenCalledWith(expect.objectContaining({ auto_apply: true }));
    rerender(<AutomaticFields form={{ ...form, auto_apply: true }} setForm={setForm} hosts={[]} />);
    expect(screen.getByLabelText('Never apply these packages')).toBeTruthy();
  });
});
