// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for childHostDistributions API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    distributionService,
    Distribution,
    CreateDistributionRequest,
    UpdateDistributionRequest,
} from '../childHostDistributions';
import axiosInstance from '../api.js';

vi.mock('../api.js', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

const mockDistribution: Distribution = {
    id: 'dist-1',
    child_type: 'container',
    distribution_name: 'ubuntu',
    distribution_version: '22.04',
    display_name: 'Ubuntu 22.04',
    install_identifier: null,
    executable_name: null,
    agent_install_method: null,
    agent_install_commands: null,
    is_active: true,
    min_agent_version: null,
    notes: null,
    created_at: null,
    updated_at: null,
};

describe('distributionService', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('getAll', () => {
        it('fetches all distributions with no filter', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: [mockDistribution] });

            const result = await distributionService.getAll();

            expect(result).toEqual([mockDistribution]);
            expect(axiosInstance.get).toHaveBeenCalledWith(
                '/api/v1/child-host-distributions/all',
                { params: {} },
            );
        });

        it('fetches distributions filtered by child type', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: [mockDistribution] });

            const result = await distributionService.getAll('container');

            expect(result).toEqual([mockDistribution]);
            expect(axiosInstance.get).toHaveBeenCalledWith(
                '/api/v1/child-host-distributions/all',
                { params: { child_type: 'container' } },
            );
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Network error'));
            await expect(distributionService.getAll()).rejects.toThrow('Network error');
        });
    });

    describe('get', () => {
        it('fetches a single distribution by id', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: mockDistribution });

            const result = await distributionService.get('dist-1');

            expect(result).toEqual(mockDistribution);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/child-host-distributions/dist-1');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Not found'));
            await expect(distributionService.get('dist-1')).rejects.toThrow('Not found');
        });
    });

    describe('create', () => {
        it('creates a distribution', async () => {
            const request: CreateDistributionRequest = {
                child_type: 'container',
                distribution_name: 'ubuntu',
                distribution_version: '22.04',
                display_name: 'Ubuntu 22.04',
            };
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data: mockDistribution });

            const result = await distributionService.create(request);

            expect(result).toEqual(mockDistribution);
            expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/child-host-distributions', request);
        });

        it('rethrows on error', async () => {
            const request: CreateDistributionRequest = {
                child_type: 'container',
                distribution_name: 'ubuntu',
                distribution_version: '22.04',
                display_name: 'Ubuntu 22.04',
            };
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('Create failed'));
            await expect(distributionService.create(request)).rejects.toThrow('Create failed');
        });
    });

    describe('update', () => {
        it('updates a distribution', async () => {
            const request: UpdateDistributionRequest = { display_name: 'New Name' };
            vi.mocked(axiosInstance.put).mockResolvedValueOnce({ data: mockDistribution });

            const result = await distributionService.update('dist-1', request);

            expect(result).toEqual(mockDistribution);
            expect(axiosInstance.put).toHaveBeenCalledWith(
                '/api/v1/child-host-distributions/dist-1',
                request,
            );
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('Update failed'));
            await expect(distributionService.update('dist-1', {})).rejects.toThrow('Update failed');
        });
    });

    describe('delete', () => {
        it('deletes a distribution', async () => {
            vi.mocked(axiosInstance.delete).mockResolvedValueOnce({ data: undefined });

            const result = await distributionService.delete('dist-1');

            expect(result).toBeUndefined();
            expect(axiosInstance.delete).toHaveBeenCalledWith('/api/v1/child-host-distributions/dist-1');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error('Delete failed'));
            await expect(distributionService.delete('dist-1')).rejects.toThrow('Delete failed');
        });
    });

    describe('toggleActive', () => {
        it('toggles active flag via put', async () => {
            vi.mocked(axiosInstance.put).mockResolvedValueOnce({ data: mockDistribution });

            const result = await distributionService.toggleActive('dist-1', false);

            expect(result).toEqual(mockDistribution);
            expect(axiosInstance.put).toHaveBeenCalledWith(
                '/api/v1/child-host-distributions/dist-1',
                { is_active: false },
            );
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('Toggle failed'));
            await expect(distributionService.toggleActive('dist-1', true)).rejects.toThrow('Toggle failed');
        });
    });
});
