// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for serverSettings API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { serverSettingsService } from '../serverSettings';
import axiosInstance from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        put: vi.fn(),
    },
}));

describe('Server Settings Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('get', () => {
        it('fetches settings and unwraps the settings array', async () => {
            const settings = [
                { key: 'a', group: 'g', type: 'str', value: 'x' },
            ];
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({
                data: { settings },
            } as never);

            const result = await serverSettingsService.get();

            expect(result).toEqual(settings);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/settings');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
            await expect(serverSettingsService.get()).rejects.toThrow('boom');
        });
    });

    describe('update', () => {
        it('updates settings and unwraps the settings array', async () => {
            const settings = [
                { key: 'a', group: 'g', type: 'int', value: 5 },
            ];
            vi.mocked(axiosInstance.put).mockResolvedValueOnce({
                data: { settings },
            } as never);

            const result = await serverSettingsService.update({ a: 5 });

            expect(result).toEqual(settings);
            expect(axiosInstance.put).toHaveBeenCalledWith('/api/v1/settings', {
                settings: { a: 5 },
            });
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('fail'));
            await expect(serverSettingsService.update({})).rejects.toThrow('fail');
        });
    });
});
