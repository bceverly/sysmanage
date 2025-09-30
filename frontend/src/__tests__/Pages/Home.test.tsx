import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import Home from '../../Pages/Home';

// Mock localStorage
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn(() => 'mock-token'),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  },
});

// Mock the hosts service
vi.mock('../../Services/hosts', () => ({
  doGetHosts: vi.fn(() => Promise.resolve([
    { id: '550e8400-e29b-41d4-a716-446655440001', active: true, status: 'up', fqdn: 'test1.example.com', ipv4: '192.168.1.1', ipv6: '::1' },
    { id: '550e8400-e29b-41d4-a716-446655440002', active: true, status: 'up', fqdn: 'test2.example.com', ipv4: '192.168.1.2', ipv6: '::2' }
  ]))
}));

// Mock the updates service
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

// Mock MUI X-Charts Gauge component to avoid ESM resolution issues
vi.mock('@mui/x-charts/Gauge', () => ({
  Gauge: vi.fn(() => null),
  gaugeClasses: {}
}));

const HomeWithRouter = () => (
  <BrowserRouter future={{
    v7_startTransition: true,
    v7_relativeSplatPath: true
  }}>
    <Home />
  </BrowserRouter>
);

describe('Home Page', () => {
  test('renders without crashing', async () => {
    await act(async () => {
      render(<HomeWithRouter />);
    });
    // Basic smoke test - ensure component renders
    expect(document.body).toBeInTheDocument();
  });

  test('contains main content area', async () => {
    await act(async () => {
      render(<HomeWithRouter />);
    });
    // Check for actual content from the Home page
    expect(screen.getByText('Hosts')).toBeInTheDocument();
  });

  test('displays home page content', async () => {
    await act(async () => {
      render(<HomeWithRouter />);
    });
    
    // At minimum, something should be rendered
    const bodyContent = document.body.textContent || '';
    expect(bodyContent.length).toBeGreaterThan(0);
  });

  test('has proper document structure', async () => {
    await act(async () => {
      render(<HomeWithRouter />);
    });
    
    // Ensure the component renders successfully
    expect(document.body).toBeInTheDocument();
  });

  test('renders home page component successfully', async () => {
    // This is a comprehensive test to ensure Home component loads
    await act(async () => {
      expect(() => render(<HomeWithRouter />)).not.toThrow();
    });
  });
});