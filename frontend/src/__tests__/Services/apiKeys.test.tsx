// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, test, expect } from 'vitest';

// Mock the axios instance the apiKeys service imports.
vi.mock('../../Services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import axiosInstance from '../../Services/api';
import {
  listApiKeys,
  createApiKey,
  getApiKey,
  revokeApiKey,
} from '../../Services/apiKeys';

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;
const mockDelete = axiosInstance.delete as unknown as ReturnType<typeof vi.fn>;

const KEY = {
  id: 'k1',
  user_id: 'u1',
  name: 'ci',
  key_prefix: 'smk_abcd1234',
  is_active: true,
};

describe('apiKeys service', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockDelete.mockReset();
  });

  test('listApiKeys GETs /api/v1/api-keys', async () => {
    mockGet.mockResolvedValueOnce({ data: [KEY] });
    const keys = await listApiKeys();
    expect(keys).toEqual([KEY]);
    expect(mockGet).toHaveBeenCalledWith('/api/v1/api-keys');
  });

  test('createApiKey POSTs payload and returns the one-time key', async () => {
    mockPost.mockResolvedValueOnce({
      data: { ...KEY, key: 'smk_thePlaintextValue' },
    });
    const created = await createApiKey({ name: 'ci' });
    expect(created.key).toBe('smk_thePlaintextValue');
    expect(mockPost).toHaveBeenCalledWith('/api/v1/api-keys', { name: 'ci' });
  });

  test('getApiKey GETs the key by id', async () => {
    mockGet.mockResolvedValueOnce({ data: KEY });
    const key = await getApiKey('k1');
    expect(key).toEqual(KEY);
    expect(mockGet).toHaveBeenCalledWith('/api/v1/api-keys/k1');
  });

  test('revokeApiKey DELETEs the key by id', async () => {
    mockDelete.mockResolvedValueOnce({});
    await revokeApiKey('k1');
    expect(mockDelete).toHaveBeenCalledWith('/api/v1/api-keys/k1');
  });
});
