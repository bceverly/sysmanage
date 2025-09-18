import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import ReportViewer from '../../Pages/ReportViewer';

/* eslint-disable no-undef, no-unused-vars */
declare const global: {
  fetch: any;
};
declare const console: {
  error: (...args: any[]) => void;
};
declare const require: (module: string) => any;
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
    useParams: vi.fn(() => ({ reportId: 'hosts' })),
  };
});

const ReportViewerWithRouter = ({ reportId = 'hosts' }) => (
  <MemoryRouter
    initialEntries={[`/reports/${reportId}`]}
    future={{
      v7_startTransition: true,
      v7_relativeSplatPath: true
    }}
  >
    <ReportViewer />
  </MemoryRouter>
);

// Import the mocked api
import api from '../../Services/api';
import { useParams } from 'react-router-dom';

// Type the mock properly
const mockApi = vi.mocked(api);
const mockUseParams = vi.mocked(useParams);

describe('ReportViewer Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('renders without crashing', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('Back')).toBeInTheDocument();
    });
  });

  test('displays loading state initially', async () => {
    mockApi.get.mockImplementationOnce(
      () => new Promise(resolve => setTimeout(() => resolve({
        data: '<html><body>Mock HTML Report</body></html>',
      }), 100))
    );

    render(<ReportViewerWithRouter />);

    // Should show loading spinner while request is pending
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  test('fetches and displays HTML report content', async () => {
    const mockHtmlContent = '<html><body><h1>Test Report</h1><p>Report content here</p></body></html>';

    mockApi.get.mockResolvedValueOnce({
      data: mockHtmlContent,
    });

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/reports/view/hosts',
        expect.objectContaining({
          responseType: 'text',
        })
      );
    });

    // Check that iframe is rendered
    await waitFor(() => {
      const iframe = screen.getByTitle('Report Content');
      expect(iframe).toBeInTheDocument();
    });
  });

  test('displays Back button', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      const backButton = screen.getByText('Back');
      expect(backButton).toBeInTheDocument();
    });
  });

  test('navigates back to reports when Back button is clicked', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      const backButton = screen.getByText('Back');
      expect(backButton).toBeInTheDocument();
    });

    const backButton = screen.getByText('Back');

    await act(async () => {
      fireEvent.click(backButton);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/reports');
  });

  test('displays Generate PDF button', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      const pdfButton = screen.getByText('Generate PDF');
      expect(pdfButton).toBeInTheDocument();
    });
  });

  test('generates PDF when Generate PDF button is clicked', async () => {
    // Mock HTML fetch
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('Generate PDF')).toBeInTheDocument();
    });

    // Mock PDF fetch
    mockApi.get.mockResolvedValueOnce({
      data: new Blob(['mock-pdf'], { type: 'application/pdf' }),
    });

    const pdfButton = screen.getByText('Generate PDF');

    await act(async () => {
      fireEvent.click(pdfButton);
    });

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/reports/generate/hosts',
        expect.objectContaining({
          responseType: 'blob',
        })
      );
    });
  });

  test('handles error when fetching HTML report', async () => {
    mockApi.get.mockRejectedValueOnce(new Error('Network error'));

    // Mock console.error to suppress error output in tests
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('Failed to load report')).toBeInTheDocument();
    });

    consoleSpy.mockRestore();
  });

  test('handles error when generating PDF', async () => {
    // Mock HTML fetch to succeed
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('Generate PDF')).toBeInTheDocument();
    });

    // Mock PDF fetch to fail
    mockApi.get.mockRejectedValueOnce(new Error('PDF generation error'));

    // Mock console.error to suppress error output in tests
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const pdfButton = screen.getByText('Generate PDF');

    await act(async () => {
      fireEvent.click(pdfButton);
    });

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith('Error generating PDF:', expect.any(Error));
    });

    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith('Error generating PDF: Unknown error');
    });

    consoleSpy.mockRestore();
  });

  test('renders with different report types', async () => {
    // Mock console.error to suppress error output
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Users Report</body></html>',
    });

    // Override useParams mock for this test
    mockUseParams.mockReturnValueOnce({ reportId: 'users' });

    await act(async () => {
      render(<ReportViewerWithRouter reportId="users" />);
    });

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/reports/view/users',
        expect.objectContaining({
          responseType: 'text',
        })
      );
    });

    consoleSpy.mockRestore();
  });

  test('iframe has correct styling and attributes', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      const iframe = screen.getByTitle('Report Content');
      expect(iframe).toHaveAttribute('title', 'Report Content');
      expect(iframe).toHaveStyle('width: 100%');
    });
  });

  test('proper cleanup on unmount', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    const { unmount } = render(<ReportViewerWithRouter />);

    await waitFor(() => {
      expect(screen.getByText('Back')).toBeInTheDocument();
    });

    // Unmount component
    unmount();

    // Component should be unmounted without errors
    expect(screen.queryByText('Back')).not.toBeInTheDocument();
  });

  test('handles missing report ID parameter', async () => {
    // Override useParams mock to return undefined reportId
    mockUseParams.mockReturnValueOnce({ reportId: undefined });

    render(<ReportViewerWithRouter />);

    // Should show loading initially since no API call will be made
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  test('PDF download creates proper blob URL and triggers download', async () => {
    const mockBlob = new Blob(['mock-pdf'], { type: 'application/pdf' });

    // Mock HTML fetch
    mockApi.get.mockResolvedValueOnce({
      data: '<html><body>Mock HTML Report</body></html>',
    });

    await act(async () => {
      render(<ReportViewerWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('Generate PDF')).toBeInTheDocument();
    });

    // Mock PDF fetch
    mockApi.get.mockResolvedValueOnce({
      data: mockBlob,
    });

    const pdfButton = screen.getByText('Generate PDF');

    await act(async () => {
      fireEvent.click(pdfButton);
    });

    await waitFor(() => {
      expect(window.URL.createObjectURL).toHaveBeenCalledWith(mockBlob);
      expect(window.open).toHaveBeenCalledWith('mock-blob-url', '_blank');
    });
  });
});