import { vi, describe, beforeEach, test, expect } from 'vitest';

// Mock the axios instance the control-plane service imports.
vi.mock('../../Services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

import axiosInstance from '../../Services/api';
import { controlPlaneService } from '../../Services/controlPlane';

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;
const mockDelete = axiosInstance.delete as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('controlPlaneService', () => {
  test('getStatus returns the payload', async () => {
    mockGet.mockResolvedValue({
      data: { multitenancy_enabled: true, tenant_count: 3 },
    });
    const res = await controlPlaneService.getStatus();
    expect(mockGet).toHaveBeenCalledWith('/api/control-plane/status');
    expect(res).toEqual({ multitenancy_enabled: true, tenant_count: 3 });
  });

  test('listTenants unwraps the envelope', async () => {
    mockGet.mockResolvedValue({
      data: { tenants: [{ id: 't1', name: 'Acme', slug: 'acme', status: 'active' }], total: 1 },
    });
    const res = await controlPlaneService.listTenants();
    expect(res).toHaveLength(1);
    expect(res[0].slug).toBe('acme');
  });

  test('listTenants passes a status filter', async () => {
    mockGet.mockResolvedValue({ data: { tenants: [], total: 0 } });
    await controlPlaneService.listTenants('suspended');
    expect(mockGet).toHaveBeenCalledWith('/api/control-plane/tenants', {
      params: { status: 'suspended' },
    });
  });

  test('addEmailDomain posts to the tenant-scoped path', async () => {
    mockPost.mockResolvedValue({
      data: { id: 'd1', tenant_id: 't1', domain: 'acme.com' },
    });
    const res = await controlPlaneService.addEmailDomain('t1', 'acme.com');
    expect(mockPost).toHaveBeenCalledWith(
      '/api/control-plane/tenants/t1/email-domains',
      { domain: 'acme.com' },
    );
    expect(res.domain).toBe('acme.com');
  });

  test('ensureUser reuses an existing user instead of creating one', async () => {
    mockGet.mockResolvedValue({
      data: [{ id: 'u1', email: 'a@acme.com', is_active: true }],
    });
    const res = await controlPlaneService.ensureUser('a@acme.com');
    expect(res.id).toBe('u1');
    expect(mockPost).not.toHaveBeenCalled();
  });

  test('ensureUser creates a user when none exists', async () => {
    mockGet.mockResolvedValue({ data: [] });
    mockPost.mockResolvedValue({
      data: { id: 'u2', email: 'b@acme.com', is_active: true },
    });
    const res = await controlPlaneService.ensureUser('b@acme.com');
    expect(mockPost).toHaveBeenCalledWith('/api/control-plane/users', {
      email: 'b@acme.com',
    });
    expect(res.id).toBe('u2');
  });

  test('getPlacement returns null on a 404', async () => {
    mockGet.mockRejectedValue({ response: { status: 404 } });
    const res = await controlPlaneService.getPlacement('t1');
    expect(res).toBeNull();
  });

  test('getPlacement rethrows non-404 errors', async () => {
    mockGet.mockRejectedValue({ response: { status: 500 } });
    await expect(controlPlaneService.getPlacement('t1')).rejects.toBeTruthy();
  });

  test('autoProvision posts options to the auto-provision path', async () => {
    mockPost.mockResolvedValue({
      data: {
        tenant_id: 't1',
        dbname: 'tenant_acme',
        openbao_role: 'acme-role',
        revision: 'rev1',
        status: 'provisioned',
      },
    });
    const res = await controlPlaneService.autoProvision('t1', {
      host: 'db',
      tier: 'silo',
    });
    expect(mockPost).toHaveBeenCalledWith(
      '/api/control-plane/tenants/t1/auto-provision',
      { host: 'db', tier: 'silo' },
    );
    expect(res.dbname).toBe('tenant_acme');
  });

  test('autoProvision sends an empty body when no options given', async () => {
    mockPost.mockResolvedValue({ data: { status: 'provisioned' } });
    await controlPlaneService.autoProvision('t1');
    expect(mockPost).toHaveBeenCalledWith(
      '/api/control-plane/tenants/t1/auto-provision',
      {},
    );
  });

  test('createEnrollmentToken posts options and returns the plaintext once', async () => {
    mockPost.mockResolvedValue({
      data: { token: 'sme_abc', summary: { id: 'k1', label: 'laptops' } },
    });
    const res = await controlPlaneService.createEnrollmentToken('t1', {
      label: 'laptops',
      expiresInDays: 30,
      maxUses: 5,
    });
    expect(mockPost).toHaveBeenCalledWith(
      '/api/control-plane/tenants/t1/enrollment-tokens',
      { label: 'laptops', expires_in_days: 30, max_uses: 5 },
    );
    expect(res.token).toBe('sme_abc');
  });

  test('revokeEnrollmentToken deletes the token path', async () => {
    mockDelete.mockResolvedValue({ data: undefined });
    await controlPlaneService.revokeEnrollmentToken('t1', 'k9');
    expect(mockDelete).toHaveBeenCalledWith(
      '/api/control-plane/tenants/t1/enrollment-tokens/k9',
    );
  });

  test('deleteTenant sends confirm + drop_database in the request body', async () => {
    mockDelete.mockResolvedValue({ data: { registry_removed: true } });
    await controlPlaneService.deleteTenant('t1', {
      confirm: 'acme',
      dropDatabase: true,
    });
    expect(mockDelete).toHaveBeenCalledWith('/api/control-plane/tenants/t1', {
      data: { confirm: 'acme', drop_database: true },
    });
  });
});
