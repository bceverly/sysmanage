// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi, beforeEach, afterEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import Navbar from '../../Components/Navbar';
import { server } from '../../mocks/node';

// Mock the updates service for NotificationBell component
vi.mock('../../Services/updates', () => ({
  updatesService: {
    getUpdatesSummary: vi.fn(() => Promise.resolve({
      total_hosts: 2,
      hosts_with_updates: 1,
      total_updates: 5,
      security_updates: 2,
      system_updates: 2,
      application_updates: 1
    }))
  }
}));

// Mock the license service for Pro+ feature check. Includes secrets_engine (gates
// /secrets), reporting_engine + the ``reports`` feature (gates /reports). Navbar
// uses ``refreshLicenseCache`` to populate its local state.
const mockLicenseInfo = {
  active: true,
  features: ['reports'],
  modules: ['secrets_engine', 'reporting_engine']
};
vi.mock('../../Services/license', () => ({
  getLicenseInfo: vi.fn(() => Promise.resolve(mockLicenseInfo)),
  refreshLicenseCache: vi.fn(() => Promise.resolve(mockLicenseInfo)),
  getCachedLicense: vi.fn(() => mockLicenseInfo),
  isFeatureLicensed: vi.fn((f: string) => mockLicenseInfo.features.includes(f)),
  isModuleLicensed: vi.fn((m: string) => mockLicenseInfo.modules.includes(m)),
  onLicenseChange: vi.fn(() => () => {}),
  clearLicenseCache: vi.fn()
}));

const NavbarWithRouter = () => (
  <BrowserRouter>
    <Navbar />
  </BrowserRouter>
);

describe('Navbar Component (grouped menubar)', () => {
  beforeEach(() => {
    localStorage.setItem('bearer_token', 'test-token-for-navbar-tests');
    // Navbar fires three authenticated fetches on mount that the shared
    // handlers don't cover: the server-info role chip (raw fetch), the
    // federation-licensed probe, and the user's security-role permissions.
    // Mock them so nothing escapes to MSW. federation returns licensed:false
    // to keep the "/sites" link gated OFF (asserted below), and permissions is
    // an empty set so no role-gated destinations are surfaced.
    server.use(
      http.get('/api/v1/server-info', () =>
        HttpResponse.json({ role: 'standard', federation_role: 'none' }),
      ),
      http.get('/api/v1/federation/sites', () =>
        HttpResponse.json({ licensed: false }),
      ),
      http.get('/api/v1/user/permissions', () =>
        HttpResponse.json({ is_admin: false, permissions: {} }),
      ),
    );
  });

  afterEach(() => {
    localStorage.removeItem('bearer_token');
  });

  test('renders logo, grouped category menus, and the user menu', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });

    expect(screen.getByAltText('SysManage')).toBeInTheDocument();

    // Categories are the new non-navigating top-level menus. Each label appears
    // in both the desktop menubar trigger and the mobile drawer group title
    // (jsdom renders both — no CSS media queries), hence getAllByText.
    for (const cat of ['Fleet', 'Patching', 'Security', 'Automation', 'Insights', 'Administration']) {
      expect(screen.getAllByText(cat).length).toBeGreaterThan(0);
    }

    // Dashboard is now reached via the logo, not a separate text nav link.
    expect(screen.queryByText('Dashboard')).toBeNull();

    // Account menu still present.
    expect(screen.getByLabelText('User menu')).toBeInTheDocument();
  });

  test('is a header/banner element', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    const nav = screen.getByRole('banner');
    expect(nav).toBeInTheDocument();
    expect(nav.tagName).toBe('HEADER');
  });

  test('navigation destinations are present with correct hrefs', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });

    // Destinations render as links in the (always-mounted) mobile drawer; the
    // desktop menubar exposes them as menu items only once opened, so we assert
    // via the drawer links, which is viewport-independent.
    const links = screen.getAllByRole('link', { hidden: true });
    const byHref = (h: string) => links.find(l => l.getAttribute('href') === h);

    expect(byHref('/')).toBeDefined(); // logo → dashboard
    expect(byHref('/hosts')).toBeDefined();
    expect(byHref('/map')).toBeDefined();
    expect(byHref('/users')).toBeDefined();
    expect(byHref('/updates')).toBeDefined();
    expect(byHref('/os-upgrades')).toBeDefined();
    expect(byHref('/maintenance-windows')).toBeDefined();
    expect(byHref('/secrets')).toBeDefined(); // secrets_engine module in the mock
    expect(byHref('/scripts')).toBeDefined();
    expect(byHref('/reports')).toBeDefined(); // reporting_engine + reports feature
    expect(byHref('/settings')).toBeDefined(); // Settings now lives under Administration

    // Sites is gated OFF in tests (federation controller not licensed). Pinning
    // this catches a refactor that accidentally always-renders it.
    expect(byHref('/sites')).toBeUndefined();
  });

  test('renders nothing at all when not authenticated', async () => {
    localStorage.removeItem('bearer_token');
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    // Pre-login the whole navbar is hidden — no logo, no categories, no user menu.
    expect(screen.queryByAltText('SysManage')).toBeNull();
    expect(screen.queryByText('Fleet')).toBeNull();
    expect(screen.queryByLabelText('User menu')).toBeNull();
  });
});
