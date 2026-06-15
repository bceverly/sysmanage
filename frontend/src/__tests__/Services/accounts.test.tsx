import { vi, describe, beforeEach, test, expect } from 'vitest';

vi.mock('../../Services/api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import axiosInstance from '../../Services/api';
import { accountsService, getActiveTenantId } from '../../Services/accounts';

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;

function makeJwt(payload: object): string {
  const b64 = (o: object) =>
    globalThis
      .btoa(JSON.stringify(o))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
  return `${b64({ alg: 'HS256' })}.${b64(payload)}.sig`;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('accountsService', () => {
  test('list unwraps the accounts envelope', async () => {
    mockGet.mockResolvedValue({
      data: {
        accounts: [
          { tenant_id: 't1', name: 'Acme', slug: 'acme', role: 'admin', is_default: true },
        ],
        total: 1,
      },
    });
    const res = await accountsService.list();
    expect(mockGet).toHaveBeenCalledWith('/api/auth/accounts');
    expect(res[0].name).toBe('Acme');
  });

  test('switch posts tenant_id and stores the re-minted token', async () => {
    mockPost.mockResolvedValue({ data: { Authorization: 'new.token.value' } });
    await accountsService.switch('t9');
    expect(mockPost).toHaveBeenCalledWith('/api/auth/switch-account', {
      tenant_id: 't9',
    });
    expect(localStorage.getItem('bearer_token')).toBe('new.token.value');
  });
});

describe('getActiveTenantId', () => {
  test('returns null when no token', () => {
    expect(getActiveTenantId()).toBeNull();
  });

  test('decodes tenant_id from the JWT payload', () => {
    localStorage.setItem('bearer_token', makeJwt({ user_id: 'u', tenant_id: 't-42' }));
    expect(getActiveTenantId()).toBe('t-42');
  });

  test('returns null when the token has no tenant_id', () => {
    localStorage.setItem('bearer_token', makeJwt({ user_id: 'u' }));
    expect(getActiveTenantId()).toBeNull();
  });

  test('returns null for a malformed token', () => {
    localStorage.setItem('bearer_token', 'not-a-jwt');
    expect(getActiveTenantId()).toBeNull();
  });
});
