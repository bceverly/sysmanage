// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import Home from '../../Pages/Home';
import { Gauge } from '@mui/x-charts/Gauge';
import { doGetHosts, doGetHostsSummary } from '../../Services/hosts';
import { server } from '../../mocks/node';

// Mock localStorage
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn(() => 'mock-token'),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  },
});

// Mock the hosts service: the dashboard reads counts, not the host list
// (Phase 22.7).
vi.mock('../../Services/hosts', () => ({
  doGetHosts: vi.fn(() => Promise.reject(new Error('the dashboard must not fetch every host'))),
  doGetHostsSummary: vi.fn(() => Promise.resolve({
    total: 7,
    approved: 6,
    approved_up: 5,
    approved_down: 1,
    reboot_required: 3,
  })),
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
  <BrowserRouter>
    <Home />
  </BrowserRouter>
);

describe('Home Page', () => {
  // The Dashboard fires three direct axiosInstance.get() calls that the shared
  // handlers don't cover (dashboard-card prefs + antivirus/OpenTelemetry
  // coverage). Mock them here so nothing escapes to MSW as an unhandled request;
  // benign empty/zero payloads keep every assertion below unchanged.
  beforeEach(() => {
    server.use(
      http.get('/api/v1/user-preferences/dashboard-cards', () =>
        HttpResponse.json({ preferences: [] }),
      ),
      http.get('/api/v1/antivirus-coverage', () =>
        HttpResponse.json({ coverage_percentage: 0 }),
      ),
      http.get('/api/v1/opentelemetry/opentelemetry-coverage', () =>
        HttpResponse.json({ coverage_percentage: 0 }),
      ),
    );
  });

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

  test('shows the host counts from the summary, without the host list', async () => {
    await act(async () => {
      render(<HomeWithRouter />);
    });
    expect(doGetHostsSummary).toHaveBeenCalled();
    expect(doGetHosts).not.toHaveBeenCalled();
    const values = vi.mocked(Gauge).mock.calls.map(([props]) => (props as { value?: number }).value);
    expect(values).toContain(7); // hosts
    expect(values).toContain(3); // reboot required
  });
});
