// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for firewallOperationsService API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    deployFirewall,
    enableFirewall,
    disableFirewall,
    restartFirewall,
} from '../firewallOperationsService';
import axiosInstance from '../api';

vi.mock('../api', () => ({
    default: {
        post: vi.fn(),
    },
}));

describe('Firewall Operations Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('deploys the firewall', async () => {
        vi.mocked(axiosInstance.post).mockResolvedValueOnce({} as never);
        await deployFirewall('h1');
        expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/hosts/h1/firewall/deploy');
    });

    it('enables the firewall', async () => {
        vi.mocked(axiosInstance.post).mockResolvedValueOnce({} as never);
        await enableFirewall('h1');
        expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/hosts/h1/firewall/enable');
    });

    it('disables the firewall', async () => {
        vi.mocked(axiosInstance.post).mockResolvedValueOnce({} as never);
        await disableFirewall('h1');
        expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/hosts/h1/firewall/disable');
    });

    it('restarts the firewall', async () => {
        vi.mocked(axiosInstance.post).mockResolvedValueOnce({} as never);
        await restartFirewall('h1');
        expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/hosts/h1/firewall/restart');
    });

    it('rethrows on error', async () => {
        vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('boom'));
        await expect(deployFirewall('h1')).rejects.toThrow('boom');
    });
});
