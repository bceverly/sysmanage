// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for graylog API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    doCheckGraylogHealth,
    doGetGraylogAttachment,
    doAttachToGraylog,
    GraylogAttachRequest,
} from '../graylog';
import axiosInstance from '../api.js';

vi.mock('../api.js', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

describe('Graylog API Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('doCheckGraylogHealth', () => {
        it('fetches graylog health', async () => {
            const data = { healthy: true, version: '5.0' };
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

            const result = await doCheckGraylogHealth();

            expect(result).toEqual(data);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/graylog/health');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
            await expect(doCheckGraylogHealth()).rejects.toThrow('boom');
        });
    });

    describe('doGetGraylogAttachment', () => {
        it('fetches attachment for a host', async () => {
            const data = { is_attached: false, target_hostname: null };
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

            const result = await doGetGraylogAttachment('host-1');

            expect(result).toEqual(data);
            expect(axiosInstance.get).toHaveBeenCalledWith(
                '/api/v1/host/host-1/graylog_attachment',
            );
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('fail'));
            await expect(doGetGraylogAttachment('h')).rejects.toThrow('fail');
        });
    });

    describe('doAttachToGraylog', () => {
        it('posts attach request', async () => {
            const request: GraylogAttachRequest = {
                mechanism: 'gelf_tcp',
                graylog_server: '10.0.0.1',
                port: 12201,
            };
            const data = { success: true, message: 'ok' };
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data } as never);

            const result = await doAttachToGraylog('host-2', request);

            expect(result).toEqual(data);
            expect(axiosInstance.post).toHaveBeenCalledWith(
                '/api/v1/host/host-2/graylog/attach',
                request,
            );
        });

        it('rethrows on error', async () => {
            const request: GraylogAttachRequest = {
                mechanism: 'gelf_tcp',
                graylog_server: '10.0.0.1',
                port: 12201,
            };
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('nope'));
            await expect(doAttachToGraylog('h', request)).rejects.toThrow('nope');
        });
    });
});
