/**
 * Unit tests for profile API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getProfile, updateProfile, ProfileUpdateData } from '../profile';
import axiosInstance from '../api';

// Mock axios instance
vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        put: vi.fn(),
    },
}));

describe('Profile API Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('getProfile', () => {
        it('should fetch profile data successfully', async () => {
            const mockProfileData = {
                userid: 'test@example.com',
                first_name: 'John',
                last_name: 'Doe',
                active: true,
            };

            vi.mocked(axiosInstance.get).mockResolvedValueOnce({
                data: mockProfileData,
                status: 200,
                statusText: 'OK',
                headers: {},
                config: {} as any,
            });

            const result = await getProfile();

            expect(result).toEqual(mockProfileData);
            expect(axiosInstance.get).toHaveBeenCalledWith('/profile');
        });

        it('should throw error when fetch fails', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Network error'));

            await expect(getProfile()).rejects.toThrow('Network error');
        });
    });

    describe('updateProfile', () => {
        it('should update profile successfully', async () => {
            const updateData: ProfileUpdateData = {
                first_name: 'Jane',
                last_name: 'Smith',
            };

            const mockUpdatedProfile = {
                userid: 'test@example.com',
                first_name: 'Jane',
                last_name: 'Smith',
                active: true,
            };

            vi.mocked(axiosInstance.put).mockResolvedValueOnce({
                data: mockUpdatedProfile,
                status: 200,
                statusText: 'OK',
                headers: {},
                config: {} as any,
            });

            const result = await updateProfile(updateData);

            expect(result).toEqual(mockUpdatedProfile);
            expect(axiosInstance.put).toHaveBeenCalledWith('/profile', updateData);
        });

        it('should update profile with partial data', async () => {
            const updateData: ProfileUpdateData = {
                first_name: 'Jane',
            };

            const mockUpdatedProfile = {
                userid: 'test@example.com',
                first_name: 'Jane',
                last_name: 'Doe',
                active: true,
            };

            vi.mocked(axiosInstance.put).mockResolvedValueOnce({
                data: mockUpdatedProfile,
                status: 200,
                statusText: 'OK',
                headers: {},
                config: {} as any,
            });

            const result = await updateProfile(updateData);

            expect(result).toEqual(mockUpdatedProfile);
            expect(axiosInstance.put).toHaveBeenCalledWith('/profile', updateData);
        });

        it('should throw error when update fails', async () => {
            const updateData: ProfileUpdateData = {
                first_name: 'Jane',
            };

            vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('Update failed'));

            await expect(updateProfile(updateData)).rejects.toThrow('Update failed');
        });

        it('should handle empty update data', async () => {
            const updateData: ProfileUpdateData = {};

            const mockUpdatedProfile = {
                userid: 'test@example.com',
                first_name: null,
                last_name: null,
                active: true,
            };

            vi.mocked(axiosInstance.put).mockResolvedValueOnce({
                data: mockUpdatedProfile,
                status: 200,
                statusText: 'OK',
                headers: {},
                config: {} as any,
            });

            const result = await updateProfile(updateData);

            expect(result).toEqual(mockUpdatedProfile);
            expect(axiosInstance.put).toHaveBeenCalledWith('/profile', updateData);
        });
    });
});