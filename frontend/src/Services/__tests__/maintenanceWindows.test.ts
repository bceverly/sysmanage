// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for maintenanceWindows API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    maintenanceWindowsService,
    MaintenanceWindow,
    MaintenanceWindowInput,
    HostWindowStatus,
} from '../maintenanceWindows';
import axiosInstance from '../api.js';

vi.mock('../api.js', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

const okResponse = (data: unknown) => ({
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {} as any,
});

const sampleWindow: MaintenanceWindow = {
    id: 'w1',
    name: 'nightly',
    description: null,
    enabled: true,
    kind: 'allow',
    recurrence: 'daily',
    timezone: 'UTC',
    start_time: '02:00',
    duration_minutes: 60,
    days_of_week: [],
    starts_at: null,
    ends_at: null,
    scopes: [{ scope_type: 'all' }],
};

const sampleInput: MaintenanceWindowInput = {
    name: 'nightly',
    enabled: true,
    kind: 'allow',
    recurrence: 'daily',
    timezone: 'UTC',
    scopes: [{ scope_type: 'all' }],
};

describe('maintenanceWindowsService', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('list', () => {
        it('unwraps and returns res.data.windows', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce(
                okResponse({ windows: [sampleWindow] }),
            );

            const result = await maintenanceWindowsService.list();

            expect(result).toEqual([sampleWindow]);
            expect(axiosInstance.get).toHaveBeenCalledWith(
                '/api/v1/maintenance-windows',
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(
                new Error('list failed'),
            );
            await expect(maintenanceWindowsService.list()).rejects.toThrow(
                'list failed',
            );
        });
    });

    describe('create', () => {
        it('posts input and returns created window', async () => {
            vi.mocked(axiosInstance.post).mockResolvedValueOnce(
                okResponse(sampleWindow),
            );

            const result = await maintenanceWindowsService.create(sampleInput);

            expect(result).toEqual(sampleWindow);
            expect(axiosInstance.post).toHaveBeenCalledWith(
                '/api/v1/maintenance-windows',
                sampleInput,
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(
                new Error('create failed'),
            );
            await expect(
                maintenanceWindowsService.create(sampleInput),
            ).rejects.toThrow('create failed');
        });
    });

    describe('update', () => {
        it('puts input to the id endpoint and returns updated window', async () => {
            vi.mocked(axiosInstance.put).mockResolvedValueOnce(
                okResponse(sampleWindow),
            );

            const result = await maintenanceWindowsService.update(
                'w1',
                sampleInput,
            );

            expect(result).toEqual(sampleWindow);
            expect(axiosInstance.put).toHaveBeenCalledWith(
                '/api/v1/maintenance-windows/w1',
                sampleInput,
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(
                new Error('update failed'),
            );
            await expect(
                maintenanceWindowsService.update('w1', sampleInput),
            ).rejects.toThrow('update failed');
        });
    });

    describe('remove', () => {
        it('deletes the window', async () => {
            vi.mocked(axiosInstance.delete).mockResolvedValueOnce(
                okResponse(undefined),
            );

            const result = await maintenanceWindowsService.remove('w1');

            expect(result).toBeUndefined();
            expect(axiosInstance.delete).toHaveBeenCalledWith(
                '/api/v1/maintenance-windows/w1',
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.delete).mockRejectedValueOnce(
                new Error('delete failed'),
            );
            await expect(
                maintenanceWindowsService.remove('w1'),
            ).rejects.toThrow('delete failed');
        });
    });

    describe('createOverride', () => {
        it('posts the override payload', async () => {
            vi.mocked(axiosInstance.post).mockResolvedValueOnce(
                okResponse(undefined),
            );

            const result = await maintenanceWindowsService.createOverride(
                'h1',
                'urgent patch',
                30,
            );

            expect(result).toBeUndefined();
            expect(axiosInstance.post).toHaveBeenCalledWith(
                '/api/v1/maintenance-windows/overrides',
                {
                    host_id: 'h1',
                    reason: 'urgent patch',
                    duration_minutes: 30,
                },
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(
                new Error('override failed'),
            );
            await expect(
                maintenanceWindowsService.createOverride('h1', 'r', 10),
            ).rejects.toThrow('override failed');
        });
    });

    describe('hostStatus', () => {
        it('returns the host window status', async () => {
            const status: HostWindowStatus = {
                state: 'in_window',
                override: null,
                active_blackout: null,
                next_window: null,
            };
            vi.mocked(axiosInstance.get).mockResolvedValueOnce(
                okResponse(status),
            );

            const result = await maintenanceWindowsService.hostStatus('h5');

            expect(result).toEqual(status);
            expect(axiosInstance.get).toHaveBeenCalledWith(
                '/api/v1/maintenance-windows/host/h5/status',
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(
                new Error('status failed'),
            );
            await expect(
                maintenanceWindowsService.hostStatus('h5'),
            ).rejects.toThrow('status failed');
        });
    });
});
