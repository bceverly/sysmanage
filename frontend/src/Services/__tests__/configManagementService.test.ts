// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Config-management prerequisite service (Phase 20.1).
 *
 * The URLs are asserted literally.  Both routes are mounted natively under
 * /api/v1 with no unversioned alias, so a path typo here is a 404 the card
 * reports as "failed to load" -- indistinguishable from a real server problem.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  getConfigMgmtPrereq,
  installConfigMgmtPrereq,
} from '../configManagementService';
import axiosInstance from '../api';

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('Config Management Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the prerequisite status for a host', async () => {
    const data = {
      host_id: 'h1',
      executor: 'ansible-core',
      status: 'satisfied',
      installed_version: '2.20.1',
      minimum_version: '2.20',
      can_install: false,
      detail: null,
      package_name: 'ansible-core',
    };
    vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

    const result = await getConfigMgmtPrereq('h1');

    expect(result).toEqual(data);
    expect(axiosInstance.get).toHaveBeenCalledWith(
      '/api/v1/hosts/h1/config-management/prerequisite',
    );
  });

  it('requests the install for a host', async () => {
    const data = { host_id: 'h1', queued: true, message: 'ok' };
    vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data } as never);

    const result = await installConfigMgmtPrereq('h1');

    expect(result).toEqual(data);
    expect(axiosInstance.post).toHaveBeenCalledWith(
      '/api/v1/hosts/h1/config-management/prerequisite/install',
    );
  });

  it('rethrows on a failed status fetch', async () => {
    vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
    await expect(getConfigMgmtPrereq('h1')).rejects.toThrow('boom');
  });

  it('rethrows on a failed install so the card can re-enable its button', async () => {
    vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('nope'));
    await expect(installConfigMgmtPrereq('h1')).rejects.toThrow('nope');
  });
});
