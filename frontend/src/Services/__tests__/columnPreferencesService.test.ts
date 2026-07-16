// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for columnPreferencesService API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    getColumnPreferences,
    updateColumnPreferences,
    deleteColumnPreferences,
} from '../columnPreferencesService';
import axiosInstance from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

describe('Column Preferences Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('getColumnPreferences', () => {
        it('fetches column preferences for a grid', async () => {
            const data = {
                id: 'p1',
                user_id: 'u1',
                grid_identifier: 'hosts',
                hidden_columns: ['col1'],
                created_at: 'now',
                updated_at: 'now',
            };
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

            const result = await getColumnPreferences('hosts');

            expect(result).toEqual(data);
            expect(axiosInstance.get).toHaveBeenCalledWith(
                '/api/v1/user-preferences/column-preferences/hosts',
            );
        });

        it('returns null when none set', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: null } as never);
            const result = await getColumnPreferences('hosts');
            expect(result).toBeNull();
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
            await expect(getColumnPreferences('hosts')).rejects.toThrow('boom');
        });
    });

    describe('updateColumnPreferences', () => {
        it('updates column preferences', async () => {
            const data = {
                id: 'p1',
                user_id: 'u1',
                grid_identifier: 'hosts',
                hidden_columns: ['a', 'b'],
                created_at: 'now',
                updated_at: 'now',
            };
            vi.mocked(axiosInstance.put).mockResolvedValueOnce({ data } as never);

            const result = await updateColumnPreferences('hosts', ['a', 'b']);

            expect(result).toEqual(data);
            expect(axiosInstance.put).toHaveBeenCalledWith(
                '/api/v1/user-preferences/column-preferences',
                { grid_identifier: 'hosts', hidden_columns: ['a', 'b'] },
            );
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('fail'));
            await expect(updateColumnPreferences('hosts', [])).rejects.toThrow('fail');
        });
    });

    describe('deleteColumnPreferences', () => {
        it('deletes column preferences', async () => {
            vi.mocked(axiosInstance.delete).mockResolvedValueOnce({} as never);

            await deleteColumnPreferences('hosts');

            expect(axiosInstance.delete).toHaveBeenCalledWith(
                '/api/v1/user-preferences/column-preferences/hosts',
            );
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error('nope'));
            await expect(deleteColumnPreferences('hosts')).rejects.toThrow('nope');
        });
    });
});
