// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for secrets API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  secretsService,
  SecretResponse,
  SecretWithContent,
  SecretTypesResponse,
  CreateSecretRequest,
  UpdateSecretRequest,
} from '../secrets';
import axiosInstance from '../api.js';

vi.mock('../api.js', () => ({
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

const sampleSecret: SecretResponse = {
  id: 's1',
  name: 'db-pw',
  secret_type: 'password',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  created_by: 'admin',
  updated_by: 'admin',
};

describe('Secrets API Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getSecrets', () => {
    it('fetches all secrets', async () => {
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve([sampleSecret]));

      const result = await secretsService.getSecrets();

      expect(result).toEqual([sampleSecret]);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/stored-secrets');
    });

    it('returns unlicensed payload as-is', async () => {
      const unlicensed = { licensed: false, secrets: [] };
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve(unlicensed));

      const result = await secretsService.getSecrets();

      expect(result).toEqual(unlicensed);
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
      await expect(secretsService.getSecrets()).rejects.toThrow('boom');
    });
  });

  describe('getSecretTypes', () => {
    it('fetches secret types', async () => {
      const types: SecretTypesResponse = {
        types: [{ value: 'password', label: 'Password', supports_visibility: false }],
      };
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve(types));

      const result = await secretsService.getSecretTypes();

      expect(result).toEqual(types);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/stored-secrets/types');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('e'));
      await expect(secretsService.getSecretTypes()).rejects.toThrow('e');
    });
  });

  describe('getSecret', () => {
    it('fetches a secret by id', async () => {
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve(sampleSecret));

      const result = await secretsService.getSecret('s1');

      expect(result).toEqual(sampleSecret);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/stored-secrets/s1');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('nf'));
      await expect(secretsService.getSecret('s1')).rejects.toThrow('nf');
    });
  });

  describe('getSecretContent', () => {
    it('fetches secret content', async () => {
      const withContent: SecretWithContent = { ...sampleSecret, content: 'hunter2' };
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve(withContent));

      const result = await secretsService.getSecretContent('s1');

      expect(result).toEqual(withContent);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/stored-secrets/s1/content');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('c'));
      await expect(secretsService.getSecretContent('s1')).rejects.toThrow('c');
    });
  });

  describe('createSecret', () => {
    it('posts a new secret', async () => {
      const payload: CreateSecretRequest = {
        name: 'db-pw',
        secret_type: 'password',
        content: 'hunter2',
        secret_subtype: 'generic',
      };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(resolve(sampleSecret));

      const result = await secretsService.createSecret(payload);

      expect(result).toEqual(sampleSecret);
      expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/stored-secrets', payload);
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('cr'));
      await expect(
        secretsService.createSecret({
          name: 'x',
          secret_type: 'password',
          content: 'y',
          secret_subtype: 'generic',
        }),
      ).rejects.toThrow('cr');
    });
  });

  describe('updateSecret', () => {
    it('puts an updated secret', async () => {
      const payload: UpdateSecretRequest = {
        name: 'db-pw',
        secret_type: 'password',
        content: 'new',
        secret_subtype: 'generic',
      };
      vi.mocked(axiosInstance.put).mockResolvedValueOnce(resolve(sampleSecret));

      const result = await secretsService.updateSecret('s1', payload);

      expect(result).toEqual(sampleSecret);
      expect(axiosInstance.put).toHaveBeenCalledWith('/api/v1/stored-secrets/s1', payload);
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('up'));
      await expect(
        secretsService.updateSecret('s1', {
          name: 'x',
          secret_type: 'password',
          content: 'y',
          secret_subtype: 'generic',
        }),
      ).rejects.toThrow('up');
    });
  });

  describe('deleteSecret', () => {
    it('deletes a single secret', async () => {
      vi.mocked(axiosInstance.delete).mockResolvedValueOnce(resolve(undefined));

      await expect(secretsService.deleteSecret('s1')).resolves.toBeUndefined();
      expect(axiosInstance.delete).toHaveBeenCalledWith('/api/v1/stored-secrets/s1');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error('del'));
      await expect(secretsService.deleteSecret('s1')).rejects.toThrow('del');
    });
  });

  describe('deleteSecrets', () => {
    it('deletes multiple secrets with ids in the request body', async () => {
      vi.mocked(axiosInstance.delete).mockResolvedValueOnce(resolve(undefined));

      await expect(secretsService.deleteSecrets(['a', 'b'])).resolves.toBeUndefined();
      expect(axiosInstance.delete).toHaveBeenCalledWith('/api/v1/stored-secrets', {
        data: ['a', 'b'],
      });
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error('dels'));
      await expect(secretsService.deleteSecrets(['a'])).rejects.toThrow('dels');
    });
  });
});
