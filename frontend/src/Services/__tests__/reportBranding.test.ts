// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for reportBranding API service
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { reportBrandingService, ReportBranding, ReportBrandingUpdate } from '../reportBranding';
import axiosInstance from '../api.js';

vi.mock('../api.js', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

const mockBranding: ReportBranding = {
    company_name: 'Acme',
    header_text: 'Report',
    has_logo: true,
    logo_mime_type: 'image/png',
    updated_at: null,
};

describe('reportBrandingService', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('get', () => {
        it('fetches branding', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: mockBranding });

            const result = await reportBrandingService.get();

            expect(result).toEqual(mockBranding);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/report-branding');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Get failed'));
            await expect(reportBrandingService.get()).rejects.toThrow('Get failed');
        });
    });

    describe('update', () => {
        it('updates branding', async () => {
            const payload: ReportBrandingUpdate = { company_name: 'Acme' };
            vi.mocked(axiosInstance.put).mockResolvedValueOnce({ data: mockBranding });

            const result = await reportBrandingService.update(payload);

            expect(result).toEqual(mockBranding);
            expect(axiosInstance.put).toHaveBeenCalledWith('/api/v1/report-branding', payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('Update failed'));
            await expect(reportBrandingService.update({})).rejects.toThrow('Update failed');
        });
    });

    describe('uploadLogo', () => {
        it('uploads a logo as multipart form data', async () => {
            const file = new window.File(['abc'], 'logo.png', { type: 'image/png' });
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data: mockBranding });

            const result = await reportBrandingService.uploadLogo(file);

            expect(result).toEqual(mockBranding);
            expect(axiosInstance.post).toHaveBeenCalledTimes(1);
            const [url, form, config] = vi.mocked(axiosInstance.post).mock.calls[0];
            expect(url).toBe('/api/v1/report-branding/logo');
            expect(form).toBeInstanceOf(window.FormData);
            expect((form as { get: CallableFunction }).get('file')).toBe(file);
            expect(config).toEqual({ headers: { 'Content-Type': 'multipart/form-data' } });
        });

        it('rethrows on error', async () => {
            const file = new window.File(['abc'], 'logo.png', { type: 'image/png' });
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('Upload failed'));
            await expect(reportBrandingService.uploadLogo(file)).rejects.toThrow('Upload failed');
        });
    });

    describe('deleteLogo', () => {
        it('deletes a logo', async () => {
            vi.mocked(axiosInstance.delete).mockResolvedValueOnce({ data: mockBranding });

            const result = await reportBrandingService.deleteLogo();

            expect(result).toEqual(mockBranding);
            expect(axiosInstance.delete).toHaveBeenCalledWith('/api/v1/report-branding/logo');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error('Delete failed'));
            await expect(reportBrandingService.deleteLogo()).rejects.toThrow('Delete failed');
        });
    });

    describe('fetchLogoObjectUrl', () => {
        const originalCreate = globalThis.URL.createObjectURL;

        afterEach(() => {
            globalThis.URL.createObjectURL = originalCreate;
        });

        it('fetches the logo blob and returns an object URL', async () => {
            const blob = new window.Blob(['bytes'], { type: 'image/png' });
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: blob });
            globalThis.URL.createObjectURL = vi.fn(() => 'blob:mock-url');

            const result = await reportBrandingService.fetchLogoObjectUrl();

            expect(result).toBe('blob:mock-url');
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/report-branding/logo', {
                responseType: 'blob',
            });
            expect(globalThis.URL.createObjectURL).toHaveBeenCalledWith(blob);
        });

        it('returns null when the request fails (error swallowed)', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Fetch failed'));

            const result = await reportBrandingService.fetchLogoObjectUrl();

            expect(result).toBeNull();
        });
    });
});
