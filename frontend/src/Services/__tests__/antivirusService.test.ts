// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for antivirusService API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getAntivirusStatus } from '../antivirusService';
import axiosInstance from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
    },
}));

describe('Antivirus Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('fetches antivirus status for a host', async () => {
        const data = { id: 'a1', host_id: 'h1', software_name: 'clamav', enabled: true };
        vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

        const result = await getAntivirusStatus('h1');

        expect(result).toEqual(data);
        expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/hosts/h1/antivirus-status');
    });

    it('returns null when none present', async () => {
        vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: null } as never);
        const result = await getAntivirusStatus('h1');
        expect(result).toBeNull();
    });

    it('rethrows on error', async () => {
        vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
        await expect(getAntivirusStatus('h1')).rejects.toThrow('boom');
    });
});
