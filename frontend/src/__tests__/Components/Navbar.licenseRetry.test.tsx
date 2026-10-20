// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The Navbar against the REAL license cache: a license fetch that failed
// while the server was restarting used to leave an open session showing the
// OSS menus (no Pro+ items) until the user logged out and back in
// (Bryan, 2026-10-19).

import { render, screen, act, cleanup } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { vi, beforeEach, afterEach, describe, test, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import Navbar from '../../Components/Navbar';
import { clearLicenseCache, LICENSE_RETRY_DELAYS_S } from '../../Services/license';
import { server } from '../../mocks/node';

vi.mock('../../Services/updates', () => ({
  updatesService: {
    getUpdatesSummary: vi.fn(() => Promise.resolve({
      total_hosts: 0, hosts_with_updates: 0, total_updates: 0,
      security_updates: 0, system_updates: 0, application_updates: 0,
    })),
  },
}));

const LICENSED = {
  active: true,
  tier: 'enterprise',
  features: ['reports'],
  modules: ['secrets_engine', 'reporting_engine'],
};

const secretsLink = () =>
  screen.queryAllByRole('link', { hidden: true }).find(l => l.getAttribute('href') === '/secrets');

describe('Navbar license after a failed fetch', () => {
  beforeEach(() => {
    clearLicenseCache();
    localStorage.setItem('bearer_token', 'test-token');
    server.use(
      http.get('/api/v1/server-info', () => HttpResponse.json({ role: 'standard', federation_role: 'none' })),
      http.get('/api/v1/federation/sites', () => HttpResponse.json({ licensed: false })),
      http.get('/api/v1/user/permissions', () => HttpResponse.json({ is_admin: true, permissions: {} })),
    );
  });

  afterEach(() => {
    cleanup(); // unmount first: clearing the cache notifies a mounted Navbar
    vi.useRealTimers();
    clearLicenseCache();
    localStorage.removeItem('bearer_token');
  });

  test('a 502 while the server restarts, then success, ends with the licensed menu', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    server.use(
      http.get('/api/v1/license', () => {
        calls += 1;
        return calls === 1
          ? new HttpResponse(null, { status: 502 })
          : HttpResponse.json(LICENSED);
      }),
    );
    await act(async () => {
      render(<BrowserRouter><Navbar /></BrowserRouter>);
      await new Promise(resolve => setTimeout(resolve, 200));
    });
    expect(secretsLink()).toBeUndefined(); // the 502 left no license yet
    await act(async () => {
      await vi.advanceTimersByTimeAsync(LICENSE_RETRY_DELAYS_S[0] * 1000 + 100);
      await new Promise(resolve => setTimeout(resolve, 300)); // the retry's fetch
    });
    await act(async () => {
      await vi.waitFor(() => expect(secretsLink()).toBeDefined());
    });
    expect(calls).toBeGreaterThanOrEqual(2);
  });

  test('a genuine OSS answer still hides the Pro+ items', async () => {
    server.use(http.get('/api/v1/license', () => HttpResponse.json({ active: false })));
    await act(async () => {
      render(<BrowserRouter><Navbar /></BrowserRouter>);
    });
    // let every mount-time fetch (license, server-info, permissions) settle
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 200)); });
    expect(secretsLink()).toBeUndefined();
  });
});
