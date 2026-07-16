// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for updates API service
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import api from '../api';
import { updatesService } from '../updates';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

const resolve = (data: unknown) => ({
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {} as any,
});

describe('Updates API Service', () => {
    let errSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
        vi.clearAllMocks();
        errSpy = vi.spyOn(window.console, 'error').mockImplementation(() => {});
    });

    afterEach(() => {
        errSpy.mockRestore();
    });

    describe('getUpdatesSummary', () => {
        it('fetches the updates summary', async () => {
            const summary = { total_hosts: 5, hosts_with_updates: 2, total_updates: 10 };
            vi.mocked(api.get).mockResolvedValueOnce(resolve(summary));

            const result = await updatesService.getUpdatesSummary();

            expect(result).toEqual(summary);
            expect(api.get).toHaveBeenCalledWith('/api/v1/updates/summary');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('summary fail'));

            await expect(updatesService.getUpdatesSummary()).rejects.toThrow('summary fail');
        });
    });

    describe('getAllUpdates', () => {
        it('fetches updates with default params', async () => {
            const payload = { updates: [], total_count: 0, limit: 100, offset: 0 };
            vi.mocked(api.get).mockResolvedValueOnce(resolve(payload));

            const result = await updatesService.getAllUpdates();

            expect(result).toEqual(payload);
            expect(api.get).toHaveBeenCalledWith('/api/v1/updates/?limit=100&offset=0');
        });

        it('builds query string with all filters set', async () => {
            const payload = { updates: [], total_count: 0, limit: 25, offset: 5 };
            vi.mocked(api.get).mockResolvedValueOnce(resolve(payload));

            await updatesService.getAllUpdates(true, true, true, 'apt', 25, 5);

            expect(api.get).toHaveBeenCalledWith(
                '/api/v1/updates/?security_only=true&system_only=true&application_only=true&package_manager=apt&limit=25&offset=5'
            );
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('all fail'));

            await expect(updatesService.getAllUpdates()).rejects.toThrow('all fail');
        });
    });

    describe('getHostUpdates', () => {
        it('fetches host updates with no optional filters', async () => {
            const payload = { host_id: 'h1', hostname: 'host1', updates: [] };
            vi.mocked(api.get).mockResolvedValueOnce(resolve(payload));

            const result = await updatesService.getHostUpdates('h1');

            expect(result).toEqual(payload);
            expect(api.get).toHaveBeenCalledWith('/api/v1/updates/h1?');
        });

        it('fetches host updates with all filters', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve({}));

            await updatesService.getHostUpdates('h1', 'apt', true, true, true);

            expect(api.get).toHaveBeenCalledWith(
                '/api/v1/updates/h1?package_manager=apt&security_only=true&system_only=true&application_only=true'
            );
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('host fail'));

            await expect(updatesService.getHostUpdates('h1')).rejects.toThrow('host fail');
        });
    });

    describe('executeUpdates', () => {
        it('posts an execute request', async () => {
            vi.mocked(api.post).mockResolvedValueOnce(resolve({ queued: true }));

            const result = await updatesService.executeUpdates(['h1'], ['pkg'], ['apt']);

            expect(result).toEqual({ queued: true });
            expect(api.post).toHaveBeenCalledWith('/api/v1/updates/execute', {
                host_ids: ['h1'],
                package_names: ['pkg'],
                package_managers: ['apt'],
            });
        });

        it('passes undefined package managers through', async () => {
            vi.mocked(api.post).mockResolvedValueOnce(resolve({}));

            await updatesService.executeUpdates(['h1'], ['pkg']);

            expect(api.post).toHaveBeenCalledWith('/api/v1/updates/execute', {
                host_ids: ['h1'],
                package_names: ['pkg'],
                package_managers: undefined,
            });
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('exec fail'));

            await expect(updatesService.executeUpdates(['h1'], ['pkg'])).rejects.toThrow('exec fail');
        });
    });

    describe('getExecutionLog', () => {
        it('fetches the execution log with default paging', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve({ entries: [] }));

            const result = await updatesService.getExecutionLog('h1');

            expect(result).toEqual({ entries: [] });
            expect(api.get).toHaveBeenCalledWith('/api/v1/updates/execution-log/h1?limit=50&offset=0');
        });

        it('fetches the execution log with custom paging', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve({}));

            await updatesService.getExecutionLog('h1', 10, 20);

            expect(api.get).toHaveBeenCalledWith('/api/v1/updates/execution-log/h1?limit=10&offset=20');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('log fail'));

            await expect(updatesService.getExecutionLog('h1')).rejects.toThrow('log fail');
        });
    });

    describe('getUpdateResults', () => {
        it('fetches update results from the summary endpoint', async () => {
            const payload = { total_hosts: 3, results: {} };
            vi.mocked(api.get).mockResolvedValueOnce(resolve(payload));

            const result = await updatesService.getUpdateResults();

            expect(result).toEqual(payload);
            expect(api.get).toHaveBeenCalledWith('/api/v1/updates/summary');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('results fail'));

            await expect(updatesService.getUpdateResults()).rejects.toThrow('results fail');
        });
    });

    describe('getOSUpgrades', () => {
        it('fetches OS upgrades', async () => {
            const payload = { os_upgrades: [], total_count: 0, hosts_with_upgrades: 0 };
            vi.mocked(api.get).mockResolvedValueOnce(resolve(payload));

            const result = await updatesService.getOSUpgrades();

            expect(result).toEqual(payload);
            expect(api.get).toHaveBeenCalledWith('/api/v1/updates/os-upgrades');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('os fail'));

            await expect(updatesService.getOSUpgrades()).rejects.toThrow('os fail');
        });
    });

    describe('getOSUpgradesSummary', () => {
        it('fetches OS upgrades summary', async () => {
            const payload = { total_hosts: 2, hosts_with_os_upgrades: 1, total_os_upgrades: 1, os_upgrades_by_type: {} };
            vi.mocked(api.get).mockResolvedValueOnce(resolve(payload));

            const result = await updatesService.getOSUpgradesSummary();

            expect(result).toEqual(payload);
            expect(api.get).toHaveBeenCalledWith('/api/v1/updates/os-upgrades/summary');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('os summary fail'));

            await expect(updatesService.getOSUpgradesSummary()).rejects.toThrow('os summary fail');
        });
    });

    describe('executeOSUpgrades', () => {
        it('posts an OS upgrade execute request', async () => {
            vi.mocked(api.post).mockResolvedValueOnce(resolve({ queued: true }));

            const result = await updatesService.executeOSUpgrades(['h1'], ['apt']);

            expect(result).toEqual({ queued: true });
            expect(api.post).toHaveBeenCalledWith('/api/v1/updates/execute-os-upgrades', {
                host_ids: ['h1'],
                package_managers: ['apt'],
            });
        });

        it('passes undefined package managers through', async () => {
            vi.mocked(api.post).mockResolvedValueOnce(resolve({}));

            await updatesService.executeOSUpgrades(['h1']);

            expect(api.post).toHaveBeenCalledWith('/api/v1/updates/execute-os-upgrades', {
                host_ids: ['h1'],
                package_managers: undefined,
            });
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('os exec fail'));

            await expect(updatesService.executeOSUpgrades(['h1'])).rejects.toThrow('os exec fail');
        });
    });
});
