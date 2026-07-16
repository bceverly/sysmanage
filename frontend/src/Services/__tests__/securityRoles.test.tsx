// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for securityRoles API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    doGetAllRoleGroups,
    doGetUserRoles,
    doUpdateUserRoles,
} from '../securityRoles';
import axiosInstance from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        put: vi.fn(),
    },
}));

describe('Security Roles API Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('doGetAllRoleGroups', () => {
        it('fetches all role groups', async () => {
            const data = [{ id: 'g1', name: 'Group', description: null, roles: [] }];
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

            const result = await doGetAllRoleGroups();

            expect(result).toEqual(data);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/security-roles/groups');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
            await expect(doGetAllRoleGroups()).rejects.toThrow('boom');
        });
    });

    describe('doGetUserRoles', () => {
        it('fetches roles for a user', async () => {
            const data = { user_id: 'u1', role_ids: ['r1', 'r2'] };
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data } as never);

            const result = await doGetUserRoles('u1');

            expect(result).toEqual(data);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/security-roles/user/u1');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('fail'));
            await expect(doGetUserRoles('u1')).rejects.toThrow('fail');
        });
    });

    describe('doUpdateUserRoles', () => {
        it('updates roles for a user', async () => {
            const data = { user_id: 'u1', role_ids: ['r3'] };
            vi.mocked(axiosInstance.put).mockResolvedValueOnce({ data } as never);

            const result = await doUpdateUserRoles('u1', ['r3']);

            expect(result).toEqual(data);
            expect(axiosInstance.put).toHaveBeenCalledWith(
                '/api/v1/security-roles/user/u1',
                { role_ids: ['r3'] },
            );
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('nope'));
            await expect(doUpdateUserRoles('u1', [])).rejects.toThrow('nope');
        });
    });
});
