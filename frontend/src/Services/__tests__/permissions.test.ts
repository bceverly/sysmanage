// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import axiosInstance from '../api';
import * as perms from '../permissions';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));

const mockData = {
  is_admin: false,
  permissions: { 'Manage Custom Metrics': true, 'Add User': false },
};

describe('permissions service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    perms.clearPermissionsCache();
  });

  it('fetchUserPermissions fetches from the API and caches the result', async () => {
    (axiosInstance.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockData });
    const result = await perms.fetchUserPermissions();
    expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/user/permissions');
    expect(result).toEqual(mockData);
    // now cached — sync check reflects it
    expect(perms.hasPermissionSync('Manage Custom Metrics')).toBe(true);
    expect(perms.hasPermissionSync('Add User')).toBe(false);
    expect(perms.hasPermissionSync('Not A Real Role')).toBe(false);
  });

  it('getUserPermissions uses the cache on subsequent calls', async () => {
    (axiosInstance.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockData });
    await perms.getUserPermissions();
    await perms.getUserPermissions();
    expect(axiosInstance.get).toHaveBeenCalledTimes(1);
  });

  it('hasPermission (async) fetches when uncached and evaluates the role', async () => {
    (axiosInstance.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockData });
    expect(await perms.hasPermission('Manage Custom Metrics')).toBe(true);
    expect(await perms.hasPermission('Add User')).toBe(false);
    expect(await perms.hasPermission('Missing')).toBe(false);
  });

  it('hasPermissionSync returns false when nothing is cached', () => {
    expect(perms.hasPermissionSync('anything')).toBe(false);
  });

  it('clearPermissionsCache drops the cache', async () => {
    (axiosInstance.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockData });
    await perms.fetchUserPermissions();
    expect(perms.hasPermissionSync('Manage Custom Metrics')).toBe(true);
    perms.clearPermissionsCache();
    expect(perms.hasPermissionSync('Manage Custom Metrics')).toBe(false);
  });

  it('refreshPermissions re-fetches even when already cached', async () => {
    (axiosInstance.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockData });
    await perms.getUserPermissions();
    await perms.refreshPermissions();
    expect(axiosInstance.get).toHaveBeenCalledTimes(2);
  });

  it('exposes the SecurityRoles name constants', () => {
    expect(perms.SecurityRoles.ADD_USER).toBe('Add User');
    expect(perms.SecurityRoles.VIEW_HOST_DETAILS).toBe('View Host Details');
  });
});
