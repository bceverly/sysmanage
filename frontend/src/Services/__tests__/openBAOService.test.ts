// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for openBAOService API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { openBAOService } from '../openBAOService';
import axiosInstance from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

const mockStatus = {
    running: true,
    status: 'running',
    message: 'ok',
    pid: 1234,
    server_url: 'http://localhost:8200',
    health: null,
    recent_logs: [],
    sealed: false,
};

const mockConfig = {
    enabled: true,
    url: 'http://localhost:8200',
    mount_path: 'secret',
    timeout: 30,
    verify_ssl: false,
    dev_mode: true,
    has_token: true,
};

const mockOpResult = {
    success: true,
    message: 'done',
    status: mockStatus,
};

describe('openBAOService', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('getStatus', () => {
        it('fetches status', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: mockStatus });

            const result = await openBAOService.getStatus();

            expect(result).toEqual(mockStatus);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/openbao/status');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Network error'));
            await expect(openBAOService.getStatus()).rejects.toThrow('Network error');
        });
    });

    describe('getConfig', () => {
        it('fetches config', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: mockConfig });

            const result = await openBAOService.getConfig();

            expect(result).toEqual(mockConfig);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/openbao/config');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Config failed'));
            await expect(openBAOService.getConfig()).rejects.toThrow('Config failed');
        });
    });

    describe('start', () => {
        it('posts start', async () => {
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data: mockOpResult });

            const result = await openBAOService.start();

            expect(result).toEqual(mockOpResult);
            expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/openbao/start');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('Start failed'));
            await expect(openBAOService.start()).rejects.toThrow('Start failed');
        });
    });

    describe('stop', () => {
        it('posts stop', async () => {
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data: mockOpResult });

            const result = await openBAOService.stop();

            expect(result).toEqual(mockOpResult);
            expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/openbao/stop');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('Stop failed'));
            await expect(openBAOService.stop()).rejects.toThrow('Stop failed');
        });
    });

    describe('seal', () => {
        it('posts seal', async () => {
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data: mockOpResult });

            const result = await openBAOService.seal();

            expect(result).toEqual(mockOpResult);
            expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/openbao/seal');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('Seal failed'));
            await expect(openBAOService.seal()).rejects.toThrow('Seal failed');
        });
    });

    describe('unseal', () => {
        it('posts unseal', async () => {
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data: mockOpResult });

            const result = await openBAOService.unseal();

            expect(result).toEqual(mockOpResult);
            expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/openbao/unseal');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('Unseal failed'));
            await expect(openBAOService.unseal()).rejects.toThrow('Unseal failed');
        });
    });
});
