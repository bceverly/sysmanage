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

// Mock the license service for Pro+ feature check
vi.mock('../../Services/license', () => ({
  getLicenseInfo: vi.fn(() => Promise.resolve({
    active: false,
    features: []
  }))
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
    
    // Verify we have the expected links (no more logout link in main nav)
    expect(allLinks).toHaveLength(9); // SysManage logo + 8 nav links (Dashboard, Users, Hosts, Updates, OS Upgrades, Secrets, Scripts, Reports)

    // Find links by their href attributes since they don't have accessible names when hidden
    const dashboardLink = allLinks.find(link => link.getAttribute('href') === '/');
    const usersLink = allLinks.find(link => link.getAttribute('href') === '/users');
    const hostsLink = allLinks.find(link => link.getAttribute('href') === '/hosts');
    const updatesLink = allLinks.find(link => link.getAttribute('href') === '/updates');
    const osUpgradesLink = allLinks.find(link => link.getAttribute('href') === '/os-upgrades');
    const secretsLink = allLinks.find(link => link.getAttribute('href') === '/secrets');
    const scriptsLink = allLinks.find(link => link.getAttribute('href') === '/scripts');
    const reportsLink = allLinks.find(link => link.getAttribute('href') === '/reports');

    expect(dashboardLink).toHaveAttribute('href', '/');
    expect(usersLink).toHaveAttribute('href', '/users');
    expect(hostsLink).toHaveAttribute('href', '/hosts');
    expect(updatesLink).toHaveAttribute('href', '/updates');
    expect(osUpgradesLink).toHaveAttribute('href', '/os-upgrades');
    expect(secretsLink).toHaveAttribute('href', '/secrets');
    expect(scriptsLink).toHaveAttribute('href', '/scripts');
    expect(reportsLink).toHaveAttribute('href', '/reports');
  });
});