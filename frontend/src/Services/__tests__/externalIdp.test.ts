// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for external IdP API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  listProviders,
  createProvider,
  updateProvider,
  deleteProvider,
  listRoleMappings,
  createRoleMapping,
  deleteRoleMapping,
  getIdpSettings,
  updateIdpSettings,
  IdpProvider,
  IdpProviderCreate,
  IdpRoleMapping,
  IdpSettings,
} from '../externalIdp';
import axiosInstance from '../api';

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const resolve = (data: unknown) => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  config: {} as any,
});

describe('External IdP API Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listProviders', () => {
    it('fetches providers', async () => {
      const providers: IdpProvider[] = [
        { id: '1', name: 'ldap', type: 'ldap', enabled: true },
      ];
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve(providers));

      const result = await listProviders();

      expect(result).toEqual(providers);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/idp-providers');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
      await expect(listProviders()).rejects.toThrow('boom');
    });
  });

  describe('createProvider', () => {
    it('posts a new provider', async () => {
      const payload: IdpProviderCreate = { name: 'oidc', type: 'oidc' };
      const created: IdpProvider = { id: '2', name: 'oidc', type: 'oidc', enabled: false };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(resolve(created));

      const result = await createProvider(payload);

      expect(result).toEqual(created);
      expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/idp-providers', payload);
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('bad'));
      await expect(createProvider({ name: 'x', type: 'saml' })).rejects.toThrow('bad');
    });
  });

  describe('updateProvider', () => {
    it('puts a patch to a provider', async () => {
      const patch: Partial<IdpProviderCreate> = { enabled: true };
      const updated: IdpProvider = { id: '3', name: 'ldap', type: 'ldap', enabled: true };
      vi.mocked(axiosInstance.put).mockResolvedValueOnce(resolve(updated));

      const result = await updateProvider('3', patch);

      expect(result).toEqual(updated);
      expect(axiosInstance.put).toHaveBeenCalledWith('/api/v1/idp-providers/3', patch);
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('nope'));
      await expect(updateProvider('3', {})).rejects.toThrow('nope');
    });
  });

  describe('deleteProvider', () => {
    it('deletes a provider', async () => {
      vi.mocked(axiosInstance.delete).mockResolvedValueOnce(resolve(undefined));

      await expect(deleteProvider('9')).resolves.toBeUndefined();
      expect(axiosInstance.delete).toHaveBeenCalledWith('/api/v1/idp-providers/9');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error('fail'));
      await expect(deleteProvider('9')).rejects.toThrow('fail');
    });
  });

  describe('listRoleMappings', () => {
    it('fetches role mappings for a provider', async () => {
      const mappings: IdpRoleMapping[] = [
        { id: 'm1', provider_id: 'p1', external_group: 'g', role_name: 'r', default_for_unmapped: false },
      ];
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve(mappings));

      const result = await listRoleMappings('p1');

      expect(result).toEqual(mappings);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/idp-providers/p1/role-mappings');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('err'));
      await expect(listRoleMappings('p1')).rejects.toThrow('err');
    });
  });

  describe('createRoleMapping', () => {
    it('posts a new role mapping', async () => {
      const payload = { external_group: 'admins', role_name: 'admin', default_for_unmapped: true };
      const created: IdpRoleMapping = {
        id: 'm2', provider_id: 'p1', external_group: 'admins', role_name: 'admin', default_for_unmapped: true,
      };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(resolve(created));

      const result = await createRoleMapping('p1', payload);

      expect(result).toEqual(created);
      expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/idp-providers/p1/role-mappings', payload);
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('x'));
      await expect(
        createRoleMapping('p1', { external_group: 'g', role_name: 'r' }),
      ).rejects.toThrow('x');
    });
  });

  describe('deleteRoleMapping', () => {
    it('deletes a role mapping', async () => {
      vi.mocked(axiosInstance.delete).mockResolvedValueOnce(resolve(undefined));

      await expect(deleteRoleMapping('p1', 'm1')).resolves.toBeUndefined();
      expect(axiosInstance.delete).toHaveBeenCalledWith('/api/v1/idp-providers/p1/role-mappings/m1');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error('d'));
      await expect(deleteRoleMapping('p1', 'm1')).rejects.toThrow('d');
    });
  });

  describe('getIdpSettings', () => {
    it('fetches idp settings', async () => {
      const settings: IdpSettings = { local_account_fallback: true, max_failed_attempts: 5 };
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve(settings));

      const result = await getIdpSettings();

      expect(result).toEqual(settings);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/settings/idp');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('e'));
      await expect(getIdpSettings()).rejects.toThrow('e');
    });
  });

  describe('updateIdpSettings', () => {
    it('puts settings patch', async () => {
      const patch: Partial<IdpSettings> = { max_failed_attempts: 10 };
      const updated: IdpSettings = { local_account_fallback: false, max_failed_attempts: 10 };
      vi.mocked(axiosInstance.put).mockResolvedValueOnce(resolve(updated));

      const result = await updateIdpSettings(patch);

      expect(result).toEqual(updated);
      expect(axiosInstance.put).toHaveBeenCalledWith('/api/v1/settings/idp', patch);
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('u'));
      await expect(updateIdpSettings({})).rejects.toThrow('u');
    });
  });
});
