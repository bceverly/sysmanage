import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import HostDetail from '../../Pages/HostDetail';

// Mock useParams to return a valid host ID
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: '1' }),
    useNavigate: () => vi.fn(),
  };
});

// Mock localStorage
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn(() => 'mock-token'),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  },
});

// Mock axios instance
vi.mock('../../Services/api', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    axiosInstance: {
      get: vi.fn(),
      post: vi.fn(),
    },
  };
});

// Mock hosts service functions
vi.mock('../../Services/hosts', () => ({
  doGetHostByID: vi.fn(),
  doGetHostStorage: vi.fn(),
  doGetHostNetwork: vi.fn(),
  doGetHostUsers: vi.fn(),
  doGetHostGroups: vi.fn(),
  doGetHostSoftware: vi.fn(),
  doGetHostDiagnostics: vi.fn(),
  doRequestHostDiagnostics: vi.fn(),
  doGetDiagnosticDetail: vi.fn(),
  doDeleteDiagnostic: vi.fn(),
  doRebootHost: vi.fn(),
  doShutdownHost: vi.fn(),
  doGetHostUbuntuPro: vi.fn(),
  doAttachUbuntuPro: vi.fn(),
  doDetachUbuntuPro: vi.fn(),
  doEnableUbuntuProService: vi.fn(),
  doDisableUbuntuProService: vi.fn(),
}));

// Mock host data
const mockHostData = {
  id: 1,
  fqdn: 'test-host.example.com',
  ipv4: '192.168.1.100',
  ipv6: '::1',
  active: true,
  status: 'up',
  approval_status: 'approved',
  platform: 'Linux',
  last_access: '2023-01-01T12:00:00Z',
  created_at: '2023-01-01T10:00:00Z',
  updated_at: '2023-01-01T12:00:00Z',
};

// Mock software packages data
const mockSoftwarePackages = [
  {
    name: 'vim',
    version: '8.2',
    package_manager: 'apt',
    description: 'Vi IMproved - enhanced vi editor',
    status: 'installed'
  },
  {
    name: 'curl',
    version: '7.68.0',
    package_manager: 'apt',
    description: 'Command line tool for transferring data',
    status: 'installed'
  }
];

const HostDetailWithRouter = () => (
  <BrowserRouter future={{
    v7_startTransition: true,
    v7_relativeSplatPath: true
  }}>
    <HostDetail />
  </BrowserRouter>
);

describe.skip('HostDetail Package Installation', () => {
  beforeEach(async () => {
    vi.clearAllMocks();

    // Get the mocked modules
    const { axiosInstance } = await import('../../Services/api');
    const hosts = await import('../../Services/hosts');

    // Setup hosts service mocks
    vi.mocked(hosts.doGetHostByID).mockResolvedValue({
      success: true,
      data: mockHostData
    });

    vi.mocked(hosts.doGetHostSoftware).mockResolvedValue({
      success: true,
      data: mockSoftwarePackages
    });

    vi.mocked(hosts.doGetHostStorage).mockResolvedValue({
      success: true,
      data: []
    });

    vi.mocked(hosts.doGetHostNetwork).mockResolvedValue({
      success: true,
      data: []
    });

    vi.mocked(hosts.doGetHostUsers).mockResolvedValue({
      success: true,
      data: []
    });

    vi.mocked(hosts.doGetHostGroups).mockResolvedValue({
      success: true,
      data: []
    });

    vi.mocked(hosts.doGetHostDiagnostics).mockResolvedValue({
      success: true,
      data: []
    });

    vi.mocked(hosts.doGetHostUbuntuPro).mockResolvedValue({
      success: true,
      data: null
    });

    // Setup default mock responses for axios (for package search and installation)
    vi.mocked(axiosInstance.get).mockImplementation((url) => {
      if (url === '/api/hosts/1/tags') {
        return Promise.resolve({ data: [] });
      }
      if (url === '/api/tags') {
        return Promise.resolve({ data: [] });
      }
      if (url.includes('/api/packages/search')) {
        return Promise.resolve({
          data: [
            { name: 'htop', description: 'Interactive process viewer', version: '3.0.5' },
            { name: 'htop-dev', description: 'Development files for htop', version: '3.0.5' }
          ]
        });
      }
      if (url.includes('/api/hosts/1/software/installation-history')) {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({ data: {} });
    });

    vi.mocked(axiosInstance.post).mockResolvedValue({
      data: {
        success: true,
        message: 'Package installation has been queued',
        installation_ids: ['uuid-1', 'uuid-2']
      }
    });
  });

  test('renders Add Package button on Software tab', async () => {
    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    // Wait for the component to load
    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Click on Software tab
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    // Check for Add Package button
    await waitFor(() => {
      expect(screen.getByText('Add Package')).toBeInTheDocument();
    });
  });

  test('opens package installation modal when Add Package is clicked', async () => {
    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Click on Software tab
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    // Click Add Package button
    const addPackageButton = await screen.findByText('Add Package');
    fireEvent.click(addPackageButton);

    // Check that the modal opens
    await waitFor(() => {
      expect(screen.getByText('Install Packages')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Enter package name to search...')).toBeInTheDocument();
    });
  });

  test('searches for packages when typing in search field', async () => {
    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Navigate to Software tab and open modal
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    const addPackageButton = await screen.findByText('Add Package');
    fireEvent.click(addPackageButton);

    // Type in search field
    const searchInput = await screen.findByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'htop' } });

    // Wait for search results
    await waitFor(() => {
      expect(screen.getByText('Search Results')).toBeInTheDocument();
      expect(screen.getByText('htop')).toBeInTheDocument();
      expect(screen.getByText('Interactive process viewer')).toBeInTheDocument();
    });

    // Verify API call was made
    const { axiosInstance } = await import('../../Services/api');
    await waitFor(() => {
      expect(vi.mocked(axiosInstance.get)).toHaveBeenCalledWith(
        expect.stringContaining('/api/packages/search?query=htop')
      );
    });
  });

  test('selects packages and shows in selected packages section', async () => {
    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Navigate to Software tab and open modal
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    const addPackageButton = await screen.findByText('Add Package');
    fireEvent.click(addPackageButton);

    // Search for packages
    const searchInput = await screen.findByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'htop' } });

    // Wait for results and select a package
    await waitFor(() => {
      const packageCheckbox = screen.getAllByRole('checkbox')[0];
      fireEvent.click(packageCheckbox);
    });

    // Check that selected packages section appears
    await waitFor(() => {
      expect(screen.getByText('Selected Packages (1)')).toBeInTheDocument();
      expect(screen.getByText('htop')).toBeInTheDocument();
    });
  });

  test('installs selected packages when install button is clicked', async () => {
    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Navigate to Software tab and open modal
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    const addPackageButton = await screen.findByText('Add Package');
    fireEvent.click(addPackageButton);

    // Search and select packages
    const searchInput = await screen.findByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'htop' } });

    await waitFor(() => {
      const packageCheckbox = screen.getAllByRole('checkbox')[0];
      fireEvent.click(packageCheckbox);
    });

    // Click install button
    const installButton = await screen.findByText(/Install Selected Packages \(1\)/);
    fireEvent.click(installButton);

    // Verify API call was made
    const { axiosInstance } = await import('../../Services/api');
    await waitFor(() => {
      expect(vi.mocked(axiosInstance.post)).toHaveBeenCalledWith(
        '/api/packages/install/1',
        {
          package_names: ['htop'],
          requested_by: 'current_user'
        }
      );
    });

    // Check that success message is shown and modal closes
    await waitFor(() => {
      expect(screen.queryByText('Install Packages')).not.toBeInTheDocument();
    });
  });

  test('displays error message when package installation fails', async () => {
    // Mock failed installation
    const { axiosInstance } = await import('../../Services/api');
    vi.mocked(axiosInstance.post).mockRejectedValueOnce({
      response: {
        data: {
          detail: 'Host not found or not active'
        }
      }
    });

    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Navigate to Software tab and open modal
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    const addPackageButton = await screen.findByText('Add Package');
    fireEvent.click(addPackageButton);

    // Search and select packages
    const searchInput = await screen.findByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'htop' } });

    await waitFor(() => {
      const packageCheckbox = screen.getAllByRole('checkbox')[0];
      fireEvent.click(packageCheckbox);
    });

    // Click install button
    const installButton = await screen.findByText(/Install Selected Packages \(1\)/);
    fireEvent.click(installButton);

    // Check that error handling works
    await waitFor(() => {
      // The modal should still be open due to error
      expect(screen.getByText('Install Packages')).toBeInTheDocument();
    });
  });

  test('shows minimum character requirement message', async () => {
    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Navigate to Software tab and open modal
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    const addPackageButton = await screen.findByText('Add Package');
    fireEvent.click(addPackageButton);

    // Type only one character
    const searchInput = await screen.findByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'h' } });

    // Check for minimum character message
    await waitFor(() => {
      expect(screen.getByText('Enter at least 2 characters to search')).toBeInTheDocument();
    });
  });

  test('shows no packages found message for empty search results', async () => {
    // Mock empty search results
    const { axiosInstance } = await import('../../Services/api');
    vi.mocked(axiosInstance.get).mockImplementation((url) => {
      if (url === '/api/hosts/1') {
        return Promise.resolve({ data: mockHostData });
      }
      if (url === '/api/hosts/1/software') {
        return Promise.resolve({ data: mockSoftwarePackages });
      }
      if (url.includes('/api/packages/search')) {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({ data: {} });
    });

    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Navigate to Software tab and open modal
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    const addPackageButton = await screen.findByText('Add Package');
    fireEvent.click(addPackageButton);

    // Search for packages that don't exist
    const searchInput = await screen.findByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'nonexistent' } });

    // Check for no packages found message
    await waitFor(() => {
      expect(screen.getByText('No packages found matching your search')).toBeInTheDocument();
    });
  });

  test('closes modal when cancel button is clicked', async () => {
    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Navigate to Software tab and open modal
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    const addPackageButton = await screen.findByText('Add Package');
    fireEvent.click(addPackageButton);

    // Check modal is open
    await waitFor(() => {
      expect(screen.getByText('Install Packages')).toBeInTheDocument();
    });

    // Click cancel button
    const cancelButton = screen.getByText('Cancel');
    fireEvent.click(cancelButton);

    // Check modal is closed
    await waitFor(() => {
      expect(screen.queryByText('Install Packages')).not.toBeInTheDocument();
    });
  });

  test('displays Software Changes tab', async () => {
    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Check that Software Changes tab exists
    expect(screen.getByText('Software Changes')).toBeInTheDocument();

    // Click on Software Changes tab
    const softwareInstallsTab = screen.getByText('Software Changes');
    fireEvent.click(softwareInstallsTab);

    // Check that the tab content is displayed
    await waitFor(() => {
      expect(screen.getByText('Software Installation History')).toBeInTheDocument();
      expect(screen.getByText(/Software installation tracking coming soon/)).toBeInTheDocument();
    });
  });

  test('removes package from selected list when chip is deleted', async () => {
    await act(async () => {
      render(<HostDetailWithRouter />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-host.example.com')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Navigate to Software tab and open modal
    const softwareTab = screen.getByText('Software');
    fireEvent.click(softwareTab);

    const addPackageButton = await screen.findByText('Add Package');
    fireEvent.click(addPackageButton);

    // Search and select packages
    const searchInput = await screen.findByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'htop' } });

    await waitFor(() => {
      const packageCheckbox = screen.getAllByRole('checkbox')[0];
      fireEvent.click(packageCheckbox);
    });

    // Verify package is selected
    await waitFor(() => {
      expect(screen.getByText('Selected Packages (1)')).toBeInTheDocument();
    });

    // Find and click the delete button on the chip
    const deleteButton = screen.getByTestId('CancelIcon');
    fireEvent.click(deleteButton);

    // Verify package is removed from selection
    await waitFor(() => {
      expect(screen.queryByText('Selected Packages (1)')).not.toBeInTheDocument();
    });
  });
});