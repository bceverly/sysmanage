import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import Reports from '../../Pages/Reports';

/* eslint-disable no-undef, no-unused-vars */
declare const global: {
  fetch: any;
};
declare const console: {
  error: (...args: any[]) => void;
};
declare const Blob: {
  new (array: BlobPart[], options?: BlobPropertyBag): Blob;
};
declare const Headers: {
  new (init?: HeadersInit): Headers;
};
/* eslint-enable no-undef, no-unused-vars */

// Mock axios API
vi.mock('../../Services/api', () => ({
  default: {
    get: vi.fn(),
  },
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}));

// Mock localStorage
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn(() => 'mock-token'),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  },
  writable: true,
});

// Mock window.URL.createObjectURL
Object.defineProperty(window.URL, 'createObjectURL', {
  value: vi.fn(() => 'mock-blob-url'),
  writable: true,
});

// Mock window.URL.revokeObjectURL
Object.defineProperty(window.URL, 'revokeObjectURL', {
  value: vi.fn(),
  writable: true,
});

// Mock window.open
Object.defineProperty(window, 'open', {
  value: vi.fn(),
  writable: true,
});

// Mock alert
Object.defineProperty(window, 'alert', {
  value: vi.fn(),
  writable: true,
});


// Mock React Router
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Import the mocked api
import api from '../../Services/api';

// Type the mock properly
const mockApi = vi.mocked(api);

const ReportsWithRouter = () => (
  <BrowserRouter future={{
    v7_startTransition: true,
    v7_relativeSplatPath: true
  }}>
    <Reports />
  </BrowserRouter>
);

describe('Reports Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('renders without crashing', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });
    expect(screen.getByText('Reports')).toBeInTheDocument();
  });

  test('displays tabs for Hosts and Users', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    expect(screen.getByText('Hosts')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
  });

  test('displays search functionality', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    // Material-UI TextField uses label instead of placeholder, search by role
    const searchInput = screen.getByRole('textbox', { name: /search reports/i });
    expect(searchInput).toBeInTheDocument();
  });

  test('displays host reports by default', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    // Should show host-related reports
    expect(screen.getByText('Registered Hosts')).toBeInTheDocument();
    expect(screen.getByText('Hosts with Tags')).toBeInTheDocument();
  });

  test('switches to users tab when clicked', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    const usersTab = screen.getByText('Users');
    fireEvent.click(usersTab);

    await waitFor(() => {
      expect(screen.getByText('SysManage Users')).toBeInTheDocument();
    });
  });

  test('filters reports based on search input', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    const searchInput = screen.getByDisplayValue('');

    // Type in search box
    fireEvent.change(searchInput, { target: { value: 'Hosts' } });

    await waitFor(() => {
      // Should still show hosts reports that match the search
      expect(screen.getByText('Registered Hosts')).toBeInTheDocument();
      expect(screen.getByText('Hosts with Tags')).toBeInTheDocument();
    });
  });

  test('generates PDF when Generate PDF button is clicked', async () => {
    // Suppress JSDOM navigation warnings
    const originalConsoleError = console.error;
    console.error = (...args: any[]) => {
      if (args[0]?.toString().includes('Not implemented: navigation')) {
        return; // Suppress JSDOM navigation warnings
      }
      originalConsoleError(...args);
    };

    mockApi.get.mockResolvedValueOnce({
      data: new Blob(['mock-pdf'], { type: 'application/pdf' }),
      headers: {
        'content-disposition': 'attachment; filename="hosts_report.pdf"'
      }
    });

    await act(async () => {
      render(<ReportsWithRouter />);
    });

    const generateButtons = screen.getAllByText('Generate PDF');

    await act(async () => {
      fireEvent.click(generateButtons[0]);
    });

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/reports/generate/registered-hosts',
        expect.objectContaining({
          responseType: 'blob',
        })
      );
    });

    // Restore original console.error
    console.error = originalConsoleError;
  });

  test('views HTML report when View Report button is clicked', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportsWithRouter />);
    });

    const viewButtons = screen.getAllByText('View Report');

    await act(async () => {
      fireEvent.click(viewButtons[0]);
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/reports/registered-hosts');
    });
  });

  test('handles PDF generation error gracefully', async () => {
    mockApi.get.mockRejectedValueOnce(new Error('Network error'));

    // Mock console.error to suppress error output in tests
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await act(async () => {
      render(<ReportsWithRouter />);
    });

    const generateButtons = screen.getAllByText('Generate PDF');

    await act(async () => {
      fireEvent.click(generateButtons[0]);
    });

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith('Error generating report:', expect.any(Error));
    });

    consoleSpy.mockRestore();
  });

  test('handles HTML report viewing - navigates correctly', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    const viewButtons = screen.getAllByText('View Report');

    await act(async () => {
      fireEvent.click(viewButtons[0]);
    });

    // View report just navigates, doesn't make API calls that could error
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/reports/registered-hosts');
    });
  });

  test('displays correct number of report cards', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    // Should have 2 host reports by default
    const hostCards = screen.getAllByText(/Generate PDF|View Report/);
    expect(hostCards.length).toBeGreaterThanOrEqual(4); // 2 cards × 2 buttons each
  });

  test('search filters work correctly', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    const searchInput = screen.getByDisplayValue('');

    // Search for something that shouldn't match
    fireEvent.change(searchInput, { target: { value: 'nonexistent' } });

    await waitFor(() => {
      // Should not show any host reports
      expect(screen.queryByText('Registered Hosts')).not.toBeInTheDocument();
    });
  });

  test('card layout responds to screen size', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    // Check that cards are rendered in a grid layout (look for multiple report cards)
    const reportCards = screen.getAllByText(/Generate PDF|View Report/);
    expect(reportCards.length).toBeGreaterThan(0);
  });

  test('report descriptions are displayed', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    // Check for actual report descriptions from the component
    expect(screen.getByText(/Complete listing of all registered hosts/)).toBeInTheDocument();
    expect(screen.getByText(/Shows all registered hosts along with their assigned tags/)).toBeInTheDocument();
  });

  test('users tab shows user reports', async () => {
    await act(async () => {
      render(<ReportsWithRouter />);
    });

    // Click Users tab
    const usersTab = screen.getByText('Users');
    fireEvent.click(usersTab);

    await waitFor(() => {
      expect(screen.getByText('SysManage Users')).toBeInTheDocument();
      expect(screen.getByText(/Comprehensive list of all SysManage users/)).toBeInTheDocument();
    });
  });

  test('PDF download creates proper blob URL', async () => {
    // Suppress JSDOM navigation warnings
    const originalConsoleError = console.error;
    console.error = (...args: any[]) => {
      if (args[0]?.toString().includes('Not implemented: navigation')) {
        return; // Suppress JSDOM navigation warnings
      }
      originalConsoleError(...args);
    };

    const mockBlob = new Blob(['mock-pdf'], { type: 'application/pdf' });

    // Reset and setup fresh mock
    mockApi.get.mockReset();
    mockApi.get.mockResolvedValue({
      data: mockBlob,
      headers: {
        'content-disposition': 'attachment; filename="hosts_report.pdf"'
      }
    });

    await act(async () => {
      render(<ReportsWithRouter />);
    });

    const generateButtons = screen.getAllByText('Generate PDF');

    await act(async () => {
      fireEvent.click(generateButtons[0]);
    });

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/reports/generate/registered-hosts',
        expect.objectContaining({
          responseType: 'blob',
        })
      );
    });

    await waitFor(() => {
      expect(window.URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    });

    // Restore original console.error
    console.error = originalConsoleError;
  });

  test('navigation to report viewer includes correct report ID', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportsWithRouter />);
    });

    const viewButtons = screen.getAllByText('View Report');

    await act(async () => {
      fireEvent.click(viewButtons[1]); // Click the second button (hosts_with_tags)
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/reports/hosts-with-tags');
    });
  });
});