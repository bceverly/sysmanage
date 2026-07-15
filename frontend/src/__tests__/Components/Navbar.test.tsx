import { render, screen, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi, beforeEach, afterEach } from 'vitest';
import Navbar from '../../Components/Navbar';

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

// Mock the license service for Pro+ feature check.
// Include the modules that gate /secrets (secrets_engine) and /reports
// (reporting_engine) AND the ``reports`` feature — /reports now requires BOTH
// the reporting_engine module and the (Enterprise) ``reports`` feature, so a
// full-access license grants both. Navbar uses ``refreshLicenseCache`` (not
// ``getLicenseInfo``) to populate its local state, so that's what the test mocks.
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

describe('Navbar Component', () => {
  // Set up authentication before each test - navbar shows user menu only when logged in
  beforeEach(() => {
    localStorage.setItem('bearer_token', 'test-token-for-navbar-tests');
  });

  afterEach(() => {
    localStorage.removeItem('bearer_token');
  });

  test('renders navigation links', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    expect(screen.getByAltText('SysManage')).toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Hosts')).toBeInTheDocument();
    expect(screen.getByText('nav.updates')).toBeInTheDocument();
    // User profile dropdown should be present instead of direct logout link
    expect(screen.getByLabelText('User menu')).toBeInTheDocument();
  });

  test('has proper navigation structure', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    const nav = screen.getByRole('banner');
    expect(nav).toBeInTheDocument();
    expect(nav.tagName).toBe('HEADER');
  });

  test('contains navigation menu', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    // Check that navigation links are present in the DOM
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Hosts')).toBeInTheDocument();
    expect(screen.getByText('nav.updates')).toBeInTheDocument();
    // User profile dropdown replaces direct logout link
    expect(screen.getByLabelText('User menu')).toBeInTheDocument();
  });

  test('menu toggle functionality', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    // Check if menu toggle elements exist (mobile menu)
    expect(screen.getByAltText('SysManage')).toBeInTheDocument();
  });

  test('navigation links are clickable', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    // Navigation links exist in DOM but are hidden by CSS visibility
    // Use getAllByRole to get all links including hidden ones
    const allLinks = screen.getAllByRole('link', { hidden: true });
    
    // Verify we have the expected links (no more logout link in main nav).
    // Phase 12.7: added /map (host geolocation world view).
    // Phase 12.3: added /sites (federation sites page), gated on the
    // federation controller engine being loaded.  In this test the
    // MSW federation handler isn't installed, so the probe falls
    // through to ``licensed: false`` and the Sites entry is hidden —
    // exactly the OSS behaviour we want.  11 links: logo + Dashboard,
    // Users, Hosts, Map, Updates, OS Upgrades, Maintenance Windows (Phase
    // 14.2, OSS), Secrets, Scripts, Reports.
    expect(allLinks).toHaveLength(11);

    // Find links by their href attributes since they don't have accessible names when hidden
    const dashboardLink = allLinks.find(link => link.getAttribute('href') === '/');
    const usersLink = allLinks.find(link => link.getAttribute('href') === '/users');
    const hostsLink = allLinks.find(link => link.getAttribute('href') === '/hosts');
    const mapLink = allLinks.find(link => link.getAttribute('href') === '/map');
    const sitesLink = allLinks.find(link => link.getAttribute('href') === '/sites');
    const updatesLink = allLinks.find(link => link.getAttribute('href') === '/updates');
    const osUpgradesLink = allLinks.find(link => link.getAttribute('href') === '/os-upgrades');
    const maintenanceWindowsLink = allLinks.find(link => link.getAttribute('href') === '/maintenance-windows');
    const secretsLink = allLinks.find(link => link.getAttribute('href') === '/secrets');
    const scriptsLink = allLinks.find(link => link.getAttribute('href') === '/scripts');
    const reportsLink = allLinks.find(link => link.getAttribute('href') === '/reports');

    expect(dashboardLink).toHaveAttribute('href', '/');
    expect(usersLink).toHaveAttribute('href', '/users');
    expect(hostsLink).toHaveAttribute('href', '/hosts');
    expect(mapLink).toHaveAttribute('href', '/map');
    // Sites is OFF in tests — see the comment above.  Asserting
    // ``undefined`` here pins the gated-out state so a future
    // refactor that accidentally always-renders it gets caught.
    expect(sitesLink).toBeUndefined();
    expect(updatesLink).toHaveAttribute('href', '/updates');
    expect(osUpgradesLink).toHaveAttribute('href', '/os-upgrades');
    expect(maintenanceWindowsLink).toHaveAttribute('href', '/maintenance-windows');
    expect(secretsLink).toHaveAttribute('href', '/secrets');
    expect(scriptsLink).toHaveAttribute('href', '/scripts');
    expect(reportsLink).toHaveAttribute('href', '/reports');
  });
});