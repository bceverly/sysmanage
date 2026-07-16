// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for packageProfiles API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    packageProfilesService,
    PackageProfile,
    PackageProfileCreate,
    PackageProfileUpdate,
    HostComplianceStatus,
} from '../packageProfiles';
import axiosInstance from '../api.js';

vi.mock('../api.js', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

const okResponse = (data: unknown) => ({
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {} as any,
});

describe('packageProfilesService', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('list', () => {
        it('returns list of profiles', async () => {
            const profiles: PackageProfile[] = [
                {
                    id: '1',
                    name: 'p1',
                    description: null,
                    enabled: true,
                    created_at: null,
                    updated_at: null,
                },
            ];
            vi.mocked(axiosInstance.get).mockResolvedValueOnce(
                okResponse(profiles),
            );

            const result = await packageProfilesService.list();

            expect(result).toEqual(profiles);
            expect(axiosInstance.get).toHaveBeenCalledWith(
                '/api/v1/package-profiles',
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(
                new Error('list failed'),
            );
            await expect(packageProfilesService.list()).rejects.toThrow(
                'list failed',
            );
        });
    });

    describe('get', () => {
        it('returns a single profile', async () => {
            const profile: PackageProfile = {
                id: 'abc',
                name: 'p',
                description: 'd',
                enabled: false,
                created_at: null,
                updated_at: null,
            };
            vi.mocked(axiosInstance.get).mockResolvedValueOnce(
                okResponse(profile),
            );

            const result = await packageProfilesService.get('abc');

            expect(result).toEqual(profile);
            expect(axiosInstance.get).toHaveBeenCalledWith(
                '/api/v1/package-profiles/abc',
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(
                new Error('not found'),
            );
            await expect(packageProfilesService.get('abc')).rejects.toThrow(
                'not found',
            );
        });
    });

    describe('create', () => {
        it('posts payload and returns created profile', async () => {
            const payload: PackageProfileCreate = { name: 'new' };
            const created: PackageProfile = {
                id: '99',
                name: 'new',
                description: null,
                enabled: true,
                created_at: null,
                updated_at: null,
            };
            vi.mocked(axiosInstance.post).mockResolvedValueOnce(
                okResponse(created),
            );

            const result = await packageProfilesService.create(payload);

            expect(result).toEqual(created);
            expect(axiosInstance.post).toHaveBeenCalledWith(
                '/api/v1/package-profiles',
                payload,
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(
                new Error('create failed'),
            );
            await expect(
                packageProfilesService.create({ name: 'x' }),
            ).rejects.toThrow('create failed');
        });
    });

    describe('update', () => {
        it('puts payload and returns updated profile', async () => {
            const payload: PackageProfileUpdate = { enabled: false };
            const updated: PackageProfile = {
                id: '5',
                name: 'p',
                description: null,
                enabled: false,
                created_at: null,
                updated_at: null,
            };
            vi.mocked(axiosInstance.put).mockResolvedValueOnce(
                okResponse(updated),
            );

            const result = await packageProfilesService.update('5', payload);

            expect(result).toEqual(updated);
            expect(axiosInstance.put).toHaveBeenCalledWith(
                '/api/v1/package-profiles/5',
                payload,
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(
                new Error('update failed'),
            );
            await expect(
                packageProfilesService.update('5', {}),
            ).rejects.toThrow('update failed');
        });
    });

    describe('remove', () => {
        it('deletes the profile', async () => {
            vi.mocked(axiosInstance.delete).mockResolvedValueOnce(
                okResponse(undefined),
            );

            const result = await packageProfilesService.remove('7');

            expect(result).toBeUndefined();
            expect(axiosInstance.delete).toHaveBeenCalledWith(
                '/api/v1/package-profiles/7',
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.delete).mockRejectedValueOnce(
                new Error('delete failed'),
            );
            await expect(packageProfilesService.remove('7')).rejects.toThrow(
                'delete failed',
            );
        });
    });

    describe('scanHost', () => {
        it('posts to the scan endpoint and returns status', async () => {
            const status: HostComplianceStatus = {
                id: 's1',
                host_id: 'h1',
                profile_id: 'p1',
                status: 'COMPLIANT',
                violations: [],
                last_scan_at: null,
            };
            vi.mocked(axiosInstance.post).mockResolvedValueOnce(
                okResponse(status),
            );

            const result = await packageProfilesService.scanHost('p1', 'h1');

            expect(result).toEqual(status);
            expect(axiosInstance.post).toHaveBeenCalledWith(
                '/api/v1/package-profiles/p1/scan/h1',
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(
                new Error('scan failed'),
            );
            await expect(
                packageProfilesService.scanHost('p1', 'h1'),
            ).rejects.toThrow('scan failed');
        });
    });

    describe('dispatchToAgent', () => {
        it('posts to the dispatch endpoint and returns status', async () => {
            const resp = { status: 'queued' };
            vi.mocked(axiosInstance.post).mockResolvedValueOnce(
                okResponse(resp),
            );

            const result = await packageProfilesService.dispatchToAgent(
                'p2',
                'h2',
            );

            expect(result).toEqual(resp);
            expect(axiosInstance.post).toHaveBeenCalledWith(
                '/api/v1/package-profiles/p2/dispatch/h2',
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(
                new Error('dispatch failed'),
            );
            await expect(
                packageProfilesService.dispatchToAgent('p2', 'h2'),
            ).rejects.toThrow('dispatch failed');
        });
    });

    describe('statusForHost', () => {
        it('returns compliance statuses for a host', async () => {
            const statuses: HostComplianceStatus[] = [
                {
                    id: 's1',
                    host_id: 'h3',
                    profile_id: 'p1',
                    status: 'NON_COMPLIANT',
                    violations: [{ package_name: 'foo', reason: 'blocked' }],
                    last_scan_at: null,
                },
            ];
            vi.mocked(axiosInstance.get).mockResolvedValueOnce(
                okResponse(statuses),
            );

            const result = await packageProfilesService.statusForHost('h3');

            expect(result).toEqual(statuses);
            expect(axiosInstance.get).toHaveBeenCalledWith(
                '/api/v1/package-profiles/status/host/h3',
            );
        });

        it('rejects when the request fails', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(
                new Error('status failed'),
            );
            await expect(
                packageProfilesService.statusForHost('h3'),
            ).rejects.toThrow('status failed');
        });
    });
});
