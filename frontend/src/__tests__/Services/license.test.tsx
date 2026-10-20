// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, test, expect } from 'vitest';

// Mock the axios instance the license service imports.
vi.mock('../../Services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import axiosInstance from '../../Services/api';
import {
  refreshLicenseCache,
  getCachedLicense,
  isFeatureLicensed,
  isModuleLicensed,
  clearLicenseCache,
  onLicenseChange,
  watchLicense,
  LICENSE_RETRY_DELAYS_S,
} from '../../Services/license';

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;

const PRO_PLUS_LICENSE = {
  active: true,
  tier: 'professional',
  features: ['health_analysis', 'audit_log_export'],
  modules: ['secrets_engine', 'reporting_engine', 'observability_engine'],
};

describe('license cache helpers', () => {
  beforeEach(() => {
    clearLicenseCache();
    mockGet.mockReset();
  });

  test('isFeatureLicensed/isModuleLicensed return false when cache is empty', () => {
    expect(isFeatureLicensed('health_analysis')).toBe(false);
    expect(isModuleLicensed('secrets_engine')).toBe(false);
    expect(getCachedLicense()).toBeNull();
  });

  test('refreshLicenseCache populates cache from /api/v1/license', async () => {
    mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
    const info = await refreshLicenseCache();
    expect(info).toEqual(PRO_PLUS_LICENSE);
    expect(getCachedLicense()).toEqual(PRO_PLUS_LICENSE);
    expect(mockGet).toHaveBeenCalledWith('/api/v1/license');
  });

  test('isFeatureLicensed reflects cached features after refresh', async () => {
    mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
    await refreshLicenseCache();
    expect(isFeatureLicensed('health_analysis')).toBe(true);
    expect(isFeatureLicensed('not_in_license')).toBe(false);
  });

  test('isModuleLicensed reflects cached modules after refresh', async () => {
    mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
    await refreshLicenseCache();
    expect(isModuleLicensed('secrets_engine')).toBe(true);
    expect(isModuleLicensed('reporting_engine')).toBe(true);
    expect(isModuleLicensed('compliance_engine')).toBe(false);
  });

  test('a failed fetch keeps the last known license (server restarting)', async () => {
    // A 502 / connection error during an upgrade is not "no license": it
    // used to empty the menus until the user logged in again (2026-10-19).
    mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
    await refreshLicenseCache();
    mockGet.mockRejectedValueOnce({ response: { status: 502 } });
    const info = await refreshLicenseCache();
    expect(info).toEqual(PRO_PLUS_LICENSE);
    expect(isModuleLicensed('secrets_engine')).toBe(true);
  });

  test('a failed fetch is retried until one succeeds', async () => {
    vi.useFakeTimers();
    try {
      mockGet.mockRejectedValueOnce(new Error('connect ECONNREFUSED'));
      mockGet.mockRejectedValueOnce({ response: { status: 503 } });
      mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
      await refreshLicenseCache();
      expect(getCachedLicense()).toBeNull();
      await vi.advanceTimersByTimeAsync(LICENSE_RETRY_DELAYS_S[0] * 1000);
      expect(getCachedLicense()).toBeNull();
      await vi.advanceTimersByTimeAsync(LICENSE_RETRY_DELAYS_S[1] * 1000);
      expect(isModuleLicensed('secrets_engine')).toBe(true);
      expect(mockGet).toHaveBeenCalledTimes(3);
      // ...and it stops retrying once it has an answer
      await vi.advanceTimersByTimeAsync(60_000);
      expect(mockGet).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  test('a genuine "no license" answer still replaces a licensed snapshot', async () => {
    mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
    await refreshLicenseCache();
    mockGet.mockResolvedValueOnce({ data: { active: false } }); // OSS
    await refreshLicenseCache();
    expect(isModuleLicensed('secrets_engine')).toBe(false);
    mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
    await refreshLicenseCache();
    mockGet.mockRejectedValueOnce({ response: { status: 402 } });
    await refreshLicenseCache();
    expect(getCachedLicense()).toEqual({ active: false });
  });

  test('regaining focus refetches the license', async () => {
    localStorage.setItem('bearer_token', 'tok');
    try {
      watchLicense();
      mockGet.mockResolvedValue({ data: PRO_PLUS_LICENSE });
      globalThis.dispatchEvent(new Event('focus'));
      await vi.waitFor(() => expect(isModuleLicensed('secrets_engine')).toBe(true));
    } finally {
      localStorage.removeItem('bearer_token');
    }
  });

  test('license without modules array returns false for any module check', async () => {
    mockGet.mockResolvedValueOnce({
      data: { active: true, tier: 'community' },
    });
    await refreshLicenseCache();
    expect(isModuleLicensed('secrets_engine')).toBe(false);
    expect(isFeatureLicensed('health_analysis')).toBe(false);
  });

  test('onLicenseChange subscribers fire on refresh and clear', async () => {
    const subscriber = vi.fn();
    const unsubscribe = onLicenseChange(subscriber);
    mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
    await refreshLicenseCache();
    expect(subscriber).toHaveBeenCalledTimes(1);
    clearLicenseCache();
    expect(subscriber).toHaveBeenCalledTimes(2);
    unsubscribe();
    clearLicenseCache();
    // After unsubscribe, no more firings.
    expect(subscriber).toHaveBeenCalledTimes(2);
  });

  test('clearLicenseCache resets every helper to the empty state', async () => {
    mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
    await refreshLicenseCache();
    expect(isModuleLicensed('secrets_engine')).toBe(true);
    clearLicenseCache();
    expect(getCachedLicense()).toBeNull();
    expect(isModuleLicensed('secrets_engine')).toBe(false);
    expect(isFeatureLicensed('health_analysis')).toBe(false);
  });
});
