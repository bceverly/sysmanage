// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for emailService API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { emailService } from '../emailService';
import axiosInstance from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

describe('Email Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('getConfig', () => {
        it('fetches email config', async () => {
            const data = {
                enabled: true,
                smtp_host: 'smtp.example.com',
                smtp_port: 587,
                from_address: 'a@b.com',
                from_name: 'A',
                subject_prefix: '[X]',
                configured: true,
            };
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

            const result = await emailService.getConfig();

            expect(result).toEqual(data);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/email/config');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
            await expect(emailService.getConfig()).rejects.toThrow('boom');
        });
    });

    describe('sendTestEmail', () => {
        it('posts a test email', async () => {
            const data = { success: true, message: 'sent' };
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data } as never);

            const result = await emailService.sendTestEmail('to@example.com');

            expect(result).toEqual(data);
            expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/email/test', {
                to_address: 'to@example.com',
            });
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('fail'));
            await expect(emailService.sendTestEmail('x@y.com')).rejects.toThrow('fail');
        });
    });
});
