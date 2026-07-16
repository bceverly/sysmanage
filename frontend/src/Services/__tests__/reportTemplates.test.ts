// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for reportTemplates API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    reportTemplatesService,
    ReportTemplate,
    ReportTemplateCreate,
    ReportTemplateUpdate,
} from '../reportTemplates';
import axiosInstance from '../api.js';

vi.mock('../api.js', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

const mockTemplate: ReportTemplate = {
    id: 't-1',
    name: 'Inventory',
    description: null,
    base_report_type: 'hosts',
    selected_fields: ['fqdn', 'os'],
    enabled: true,
    created_at: null,
    updated_at: null,
};

describe('reportTemplatesService', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('list', () => {
        it('lists templates', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: [mockTemplate] });

            const result = await reportTemplatesService.list();

            expect(result).toEqual([mockTemplate]);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/report-templates');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('List failed'));
            await expect(reportTemplatesService.list()).rejects.toThrow('List failed');
        });
    });

    describe('get', () => {
        it('fetches a template', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: mockTemplate });

            const result = await reportTemplatesService.get('t-1');

            expect(result).toEqual(mockTemplate);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/report-templates/t-1');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Not found'));
            await expect(reportTemplatesService.get('t-1')).rejects.toThrow('Not found');
        });
    });

    describe('create', () => {
        it('creates a template', async () => {
            const payload: ReportTemplateCreate = {
                name: 'Inventory',
                base_report_type: 'hosts',
                selected_fields: ['fqdn'],
            };
            vi.mocked(axiosInstance.post).mockResolvedValueOnce({ data: mockTemplate });

            const result = await reportTemplatesService.create(payload);

            expect(result).toEqual(mockTemplate);
            expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/report-templates', payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('Create failed'));
            await expect(
                reportTemplatesService.create({ name: 'x', base_report_type: 'hosts', selected_fields: [] }),
            ).rejects.toThrow('Create failed');
        });
    });

    describe('update', () => {
        it('updates a template', async () => {
            const payload: ReportTemplateUpdate = { enabled: false };
            vi.mocked(axiosInstance.put).mockResolvedValueOnce({ data: mockTemplate });

            const result = await reportTemplatesService.update('t-1', payload);

            expect(result).toEqual(mockTemplate);
            expect(axiosInstance.put).toHaveBeenCalledWith('/api/v1/report-templates/t-1', payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('Update failed'));
            await expect(reportTemplatesService.update('t-1', {})).rejects.toThrow('Update failed');
        });
    });

    describe('remove', () => {
        it('removes a template', async () => {
            vi.mocked(axiosInstance.delete).mockResolvedValueOnce({ data: undefined });

            const result = await reportTemplatesService.remove('t-1');

            expect(result).toBeUndefined();
            expect(axiosInstance.delete).toHaveBeenCalledWith('/api/v1/report-templates/t-1');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error('Remove failed'));
            await expect(reportTemplatesService.remove('t-1')).rejects.toThrow('Remove failed');
        });
    });

    describe('fieldsFor', () => {
        it('fetches fields for a base type', async () => {
            const data = {
                base_report_type: 'hosts',
                fields: [{ code: 'fqdn', label: 'FQDN' }],
            };
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data });

            const result = await reportTemplatesService.fieldsFor('hosts');

            expect(result).toEqual(data);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/report-templates/fields/hosts');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Fields failed'));
            await expect(reportTemplatesService.fieldsFor('hosts')).rejects.toThrow('Fields failed');
        });
    });

    describe('baseTypes', () => {
        it('returns the base_types array from the response', async () => {
            vi.mocked(axiosInstance.get).mockResolvedValueOnce({
                data: { base_types: ['hosts', 'packages'] },
            });

            const result = await reportTemplatesService.baseTypes();

            expect(result).toEqual(['hosts', 'packages']);
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/report-templates/base-types');
        });

        it('rethrows on error', async () => {
            vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('Base types failed'));
            await expect(reportTemplatesService.baseTypes()).rejects.toThrow('Base types failed');
        });
    });
});
