// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for upgradeProfiles API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    upgradeProfilesService,
    UpgradeProfile,
    UpgradeProfileCreate,
    UpgradeProfileUpdate,
    TriggerResult,
} from '../upgradeProfiles';
import axiosInstance from '../api.js';

vi.mock('../api.js', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

const mockProfile: UpgradeProfile = {
    id: 'p-1',
    name: 'Nightly',
    description: null,
    cron: '0 3 * * *',
    enabled: true,
    security_only: false,
    package_managers: ['apt'],
    staggered_window_min: 10,
    tag_id: null,
    last_run: null,
    last_status: null,
    next_run: null,
    created_at: null,
    updated_at: null,
};

describe('upgradeProfilesService', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('list', () => {
        it('lists profiles', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: [mockProfile] });

            const result = await upgradeProfilesService.list();

            expect(result).toEqual([mockProfile]);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/upgrade-profiles');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('List failed'));
            await expect(upgradeProfilesService.list()).rejects.toThrow('List failed');
        });
    });

    describe('create', () => {
        it('creates a profile', async () => {
            const payload: UpgradeProfileCreate = { name: 'Nightly' };
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data: mockProfile });

            const result = await upgradeProfilesService.create(payload);

            expect(result).toEqual(mockProfile);
            expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/upgrade-profiles', payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('Create failed'));
            await expect(upgradeProfilesService.create({ name: 'x' })).rejects.toThrow('Create failed');
        });
    });

    describe('update', () => {
        it('updates a profile', async () => {
            const payload: UpgradeProfileUpdate = { enabled: false };
            vi.mocked(axiosInstance.put).mockResolvedValueOnce({ data: mockProfile });

            const result = await upgradeProfilesService.update('p-1', payload);

            expect(result).toEqual(mockProfile);
            expect(axiosInstance.put).toHaveBeenCalledWith('/api/v1/upgrade-profiles/p-1', payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('Update failed'));
            await expect(upgradeProfilesService.update('p-1', {})).rejects.toThrow('Update failed');
        });
    });

    describe('remove', () => {
        it('removes a profile', async () => {
            vi.mocked(axiosInstance.delete).mockResolvedValueOnce({ data: undefined });

            const result = await upgradeProfilesService.remove('p-1');

            expect(result).toBeUndefined();
            expect(axiosInstance.delete).toHaveBeenCalledWith('/api/v1/upgrade-profiles/p-1');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error('Remove failed'));
            await expect(upgradeProfilesService.remove('p-1')).rejects.toThrow('Remove failed');
        });
    });

    describe('trigger', () => {
        it('triggers a profile', async () => {
            const mockTrigger: TriggerResult = {
                profile_id: 'p-1',
                name: 'Nightly',
                host_count: 2,
                enqueued_count: 2,
                host_ids: ['h1', 'h2'],
                next_run: null,
            };
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data: mockTrigger });

            const result = await upgradeProfilesService.trigger('p-1');

            expect(result).toEqual(mockTrigger);
            expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/upgrade-profiles/p-1/trigger');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('Trigger failed'));
            await expect(upgradeProfilesService.trigger('p-1')).rejects.toThrow('Trigger failed');
        });
    });
});
