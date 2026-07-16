// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for geolocations API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { doGetHostGeolocations } from '../geolocations';
import axiosInstance from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
    },
}));

describe('Geolocations Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('fetches host geolocations', async () => {
        const data = [
            {
                host_id: 'h1',
                fqdn: 'host.example.com',
                status: 'up',
                platform: 'linux',
                country_code: 'US',
                subdivision_code: null,
                city: null,
                latitude: 1.23,
                longitude: 4.56,
            },
        ];
        vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

        const result = await doGetHostGeolocations();

        expect(result).toEqual(data);
        expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/hosts/geolocations');
    });

    it('rethrows on error', async () => {
        vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
        await expect(doGetHostGeolocations()).rejects.toThrow('boom');
    });
});
