// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for firewallService API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getFirewallStatus } from '../firewallService';
import axiosInstance from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
    },
}));

describe('Firewall Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('fetches firewall status for a host', async () => {
        const data = { id: 'f1', host_id: 'h1', firewall_name: 'ufw', enabled: true };
        vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

        const result = await getFirewallStatus('h1');

        expect(result).toEqual(data);
        expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/hosts/h1/firewall-status');
    });

    it('returns null when none present', async () => {
        vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: null } as never);
        const result = await getFirewallStatus('h1');
        expect(result).toBeNull();
    });

    it('rethrows on error', async () => {
        vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
        await expect(getFirewallStatus('h1')).rejects.toThrow('boom');
    });
});
