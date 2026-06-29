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

  test('refreshLicenseCache clears cache to null on API failure', async () => {
    mockGet.mockResolvedValueOnce({ data: PRO_PLUS_LICENSE });
    await refreshLicenseCache();
    expect(getCachedLicense()).not.toBeNull();
    mockGet.mockRejectedValueOnce(new Error('boom'));
    const info = await refreshLicenseCache();
    expect(info).toBeNull();
    expect(getCachedLicense()).toBeNull();
    expect(isModuleLicensed('secrets_engine')).toBe(false);
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
