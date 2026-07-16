// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for processes API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    doGetHostProcesses,
    doRefreshHostProcesses,
    doKillHostProcess,
    HostProcess,
} from '../processes';
import api from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

const mockProcess: HostProcess = {
    id: 'proc-1',
    pid: 42,
    parent_pid: 1,
    process_name: 'nginx',
    username: 'root',
    status: 'running',
    cpu_percent: 0.5,
    memory_percent: 1.2,
    memory_rss_bytes: 1024,
    command_line: '/usr/sbin/nginx',
    started_at: null,
    collected_at: null,
};

const mockSimpleResult = { result: true, message: 'ok' };

describe('processes service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('doGetHostProcesses', () => {
        it('fetches processes for a host', async () => {
            vi.mocked(api.get).mockResolvedValueOnce({ data: [mockProcess] });

            const result = await doGetHostProcesses('host-1');

            expect(result).toEqual([mockProcess]);
            expect(api.get).toHaveBeenCalledWith('/api/v1/host/host-1/processes');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('Get failed'));
            await expect(doGetHostProcesses('host-1')).rejects.toThrow('Get failed');
        });
    });

    describe('doRefreshHostProcesses', () => {
        it('posts a refresh request', async () => {
            vi.mocked(api.post).mockResolvedValueOnce({ data: mockSimpleResult });

            const result = await doRefreshHostProcesses('host-1');

            expect(result).toEqual(mockSimpleResult);
            expect(api.post).toHaveBeenCalledWith('/api/v1/host/host-1/processes/refresh');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('Refresh failed'));
            await expect(doRefreshHostProcesses('host-1')).rejects.toThrow('Refresh failed');
        });
    });

    describe('doKillHostProcess', () => {
        it('kills a process with default options', async () => {
            vi.mocked(api.post).mockResolvedValueOnce({ data: mockSimpleResult });

            const result = await doKillHostProcess('host-1', 42);

            expect(result).toEqual(mockSimpleResult);
            expect(api.post).toHaveBeenCalledWith('/api/v1/host/host-1/processes/42/kill', {
                force: false,
                expected_name: null,
            });
        });

        it('kills a process with force and expectedName options', async () => {
            vi.mocked(api.post).mockResolvedValueOnce({ data: mockSimpleResult });

            const result = await doKillHostProcess('host-1', 42, {
                force: true,
                expectedName: 'nginx',
            });

            expect(result).toEqual(mockSimpleResult);
            expect(api.post).toHaveBeenCalledWith('/api/v1/host/host-1/processes/42/kill', {
                force: true,
                expected_name: 'nginx',
            });
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('Kill failed'));
            await expect(doKillHostProcess('host-1', 42)).rejects.toThrow('Kill failed');
        });
    });
});
