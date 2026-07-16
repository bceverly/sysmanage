// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for broadcast API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { broadcastService, BroadcastRequest } from '../broadcast';
import axiosInstance from '../api.js';

vi.mock('../api.js', () => ({
    default: {
        post: vi.fn(),
    },
}));

describe('Broadcast Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('posts a broadcast payload', async () => {
        const payload: BroadcastRequest = {
            broadcast_action: 'ping',
            message: 'hello',
        };
        const data = {
            broadcast_id: 'b1',
            broadcast_action: 'ping',
            delivered_count: 3,
            elapsed_ms: 12,
            target_filter: 'all',
        };
        vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data } as never);

        const result = await broadcastService.send(payload);

        expect(result).toEqual(data);
        expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/broadcast', payload);
    });

    it('rethrows on error', async () => {
        vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('boom'));
        await expect(
            broadcastService.send({ broadcast_action: 'ping' }),
        ).rejects.toThrow('boom');
    });
});
