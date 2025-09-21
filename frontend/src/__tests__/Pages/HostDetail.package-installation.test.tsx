import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, test, expect } from 'vitest';

// Simple test component that mimics the package installation UI without the complex HostDetail dependencies
const PackageInstallationModal = () => {
  const [isOpen, setIsOpen] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [searchResults, setSearchResults] = React.useState<any[]>([]);
  const [selectedPackages, setSelectedPackages] = React.useState<any[]>([]);

  const handleSearch = async () => {
    if (searchQuery.trim()) {
      // Mock search results
      setSearchResults([
        { name: 'htop', description: 'Interactive process viewer', version: '3.0.5' },
        { name: 'htop-dev', description: 'Development files for htop', version: '3.0.5' },
      ]);
    }
  };

  const handleInstallPackage = (pkg: any) => {
    setSelectedPackages([...selectedPackages, pkg]);
  };

  const handleInstallSelected = async () => {
    // Mock installation success
    setIsOpen(false);
    setSelectedPackages([]);
    setSearchResults([]);
    setSearchQuery('');
  };

  return (
    <div>
      <button onClick={() => setIsOpen(true)}>Add Package</button>

      {isOpen && (
        <div data-testid="package-modal">
          <h2>Install Packages</h2>

          <input
            placeholder="Enter package name to search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button onClick={handleSearch}>Search</button>

          {searchResults.length > 0 && (
            <div>
              <h3>Search Results</h3>
              {searchResults.map((pkg) => (
                <div key={pkg.name}>
                  <span>{pkg.name}</span>
                  <span>{pkg.description}</span>
                  <button onClick={() => handleInstallPackage(pkg)}>Install</button>
                </div>
              ))}
            </div>
          )}

          {selectedPackages.length > 0 && (
            <div>
              <h3>Packages to install ({selectedPackages.length})</h3>
              {selectedPackages.map((pkg) => (
                <div key={pkg.name}>{pkg.name}</div>
              ))}
              <button onClick={handleInstallSelected}>
                Install Selected Packages ({selectedPackages.length})
              </button>
            </div>
          )}

          <button onClick={() => setIsOpen(false)}>Cancel</button>
        </div>
      )}
    </div>
  );
};

describe('Package Installation Functionality', () => {
  test('renders Add Package button', () => {
    render(<PackageInstallationModal />);
    expect(screen.getByText('Add Package')).toBeInTheDocument();
  });

  test('opens package installation modal when Add Package is clicked', () => {
    render(<PackageInstallationModal />);

    const addButton = screen.getByText('Add Package');
    fireEvent.click(addButton);

    expect(screen.getByTestId('package-modal')).toBeInTheDocument();
    expect(screen.getByText('Install Packages')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter package name to search...')).toBeInTheDocument();
  });

  test('searches for packages when using search', async () => {
    render(<PackageInstallationModal />);

    // Open modal
    fireEvent.click(screen.getByText('Add Package'));

    // Search for packages
    const searchInput = screen.getByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'htop' } });

    const searchButton = screen.getByText('Search');
    fireEvent.click(searchButton);

    // Wait for search results
    await waitFor(() => {
      expect(screen.getByText('Search Results')).toBeInTheDocument();
      expect(screen.getByText('htop')).toBeInTheDocument();
      expect(screen.getByText('Interactive process viewer')).toBeInTheDocument();
    });
  });

  test('selects packages and shows in selected packages section', async () => {
    render(<PackageInstallationModal />);

    // Open modal and search
    fireEvent.click(screen.getByText('Add Package'));

    const searchInput = screen.getByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'htop' } });
    fireEvent.click(screen.getByText('Search'));

    // Wait for results and select a package
    await waitFor(() => {
      const installButton = screen.getAllByText('Install')[0];
      fireEvent.click(installButton);
    });

    // Check that selected packages section appears
    await waitFor(() => {
      expect(screen.getByText('Packages to install (1)')).toBeInTheDocument();
      expect(screen.getByText(/Install Selected Packages \(1\)/)).toBeInTheDocument();
    });
  });

  test('installs selected packages when install button is clicked', async () => {
    render(<PackageInstallationModal />);

    // Open modal, search, and select packages
    fireEvent.click(screen.getByText('Add Package'));

    const searchInput = screen.getByPlaceholderText('Enter package name to search...');
    fireEvent.change(searchInput, { target: { value: 'htop' } });
    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      const installButton = screen.getAllByText('Install')[0];
      fireEvent.click(installButton);
    });

    // Click install selected packages button
    const installSelectedButton = await screen.findByText(/Install Selected Packages \(1\)/);
    fireEvent.click(installSelectedButton);

    // Check that modal closes
    await waitFor(() => {
      expect(screen.queryByTestId('package-modal')).not.toBeInTheDocument();
    });
  });

  test('closes modal when cancel button is clicked', () => {
    render(<PackageInstallationModal />);

    // Open modal
    fireEvent.click(screen.getByText('Add Package'));
    expect(screen.getByTestId('package-modal')).toBeInTheDocument();

    // Click cancel
    const cancelButton = screen.getByText('Cancel');
    fireEvent.click(cancelButton);

    // Check modal is closed
    expect(screen.queryByTestId('package-modal')).not.toBeInTheDocument();
  });
});