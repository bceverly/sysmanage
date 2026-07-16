// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

// Mock the license service the guard depends on.
vi.mock('../../Services/license', () => ({
  refreshLicenseCache: vi.fn(() => Promise.resolve()),
  isModuleLicensed: vi.fn(),
  isFeatureLicensed: vi.fn(),
}));

// Mock react-router-dom's Navigate so a redirect is observable.
vi.mock('react-router-dom', () => ({
  Navigate: ({ to }: { to: string }) => <div data-testid="redirect">{to}</div>,
}));

import LicensedRoute from '../../Components/LicensedRoute';
import { isModuleLicensed, isFeatureLicensed } from '../../Services/license';

const mockModule = isModuleLicensed as unknown as ReturnType<typeof vi.fn>;
const mockFeature = isFeatureLicensed as unknown as ReturnType<typeof vi.fn>;

const child = <div data-testid="page">SECRET PAGE</div>;

describe('LicensedRoute feature + module gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('renders children when both the module and feature are licensed', async () => {
    mockModule.mockReturnValue(true);
    mockFeature.mockReturnValue(true);
    render(
      <LicensedRoute module="compliance_engine" feature="fips_mode">
        {child}
      </LicensedRoute>,
    );
    expect(await screen.findByTestId('page')).toBeInTheDocument();
    expect(screen.queryByTestId('redirect')).toBeNull();
  });

  test('redirects when the module is licensed but the feature is not', async () => {
    // The exact FIPS/compliance leak: Professional has the engine module but
    // not the Enterprise feature — the page must NOT be reachable.
    mockModule.mockReturnValue(true);
    mockFeature.mockReturnValue(false);
    render(
      <LicensedRoute module="compliance_engine" feature="fips_mode">
        {child}
      </LicensedRoute>,
    );
    expect(await screen.findByTestId('redirect')).toHaveTextContent('/');
    expect(screen.queryByTestId('page')).toBeNull();
  });

  test('redirects when the feature is licensed but the module is not', async () => {
    mockModule.mockReturnValue(false);
    mockFeature.mockReturnValue(true);
    render(
      <LicensedRoute module="compliance_engine" feature="fips_mode">
        {child}
      </LicensedRoute>,
    );
    expect(await screen.findByTestId('redirect')).toBeInTheDocument();
  });

  test('a feature-only gate is honoured', async () => {
    mockFeature.mockReturnValue(false);
    render(<LicensedRoute feature="fips_mode">{child}</LicensedRoute>);
    expect(await screen.findByTestId('redirect')).toBeInTheDocument();
    // Module check is irrelevant when no module gate is set.
    expect(mockModule).not.toHaveBeenCalled();
  });

  test('renders when no gate is set at all', async () => {
    render(<LicensedRoute>{child}</LicensedRoute>);
    expect(await screen.findByTestId('page')).toBeInTheDocument();
  });
});
