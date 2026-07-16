// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for scripts API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import api from '../api';
import { scriptsService, Script, ExecuteScriptRequest } from '../scripts';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
        request: vi.fn(),
    },
}));

const resolve = (data: unknown) => ({
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {} as any,
});

const mockScript: Script = {
    id: '1',
    name: 'test',
    description: 'desc',
    content: 'echo hi',
    shell_type: 'bash',
    is_active: true,
};

describe('Scripts API Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('getSavedScripts', () => {
        it('fetches saved scripts', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve([mockScript]));

            const result = await scriptsService.getSavedScripts();

            expect(result).toEqual([mockScript]);
            expect(api.get).toHaveBeenCalledWith('/api/v1/scripts/');
        });
    });

    describe('createScript', () => {
        it('posts a new script', async () => {
            const newScript = {
                name: 'test',
                description: 'desc',
                content: 'echo hi',
                shell_type: 'bash',
                is_active: true,
            };
            vi.mocked(api.post).mockResolvedValueOnce(resolve(mockScript));

            const result = await scriptsService.createScript(newScript);

            expect(result).toEqual(mockScript);
            expect(api.post).toHaveBeenCalledWith('/api/v1/scripts/', newScript);
        });
    });

    describe('updateScript', () => {
        it('puts an updated script', async () => {
            const patch = { name: 'renamed' };
            vi.mocked(api.put).mockResolvedValueOnce(resolve({ ...mockScript, name: 'renamed' }));

            const result = await scriptsService.updateScript('1', patch);

            expect(result).toEqual({ ...mockScript, name: 'renamed' });
            expect(api.put).toHaveBeenCalledWith('/api/v1/scripts/1', patch);
        });
    });

    describe('deleteScript', () => {
        it('deletes a script', async () => {
            vi.mocked(api.delete).mockResolvedValueOnce(resolve(undefined));

            await scriptsService.deleteScript('1');

            expect(api.delete).toHaveBeenCalledWith('/api/v1/scripts/1');
        });
    });

    describe('getScript', () => {
        it('fetches a single script', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve(mockScript));

            const result = await scriptsService.getScript('1');

            expect(result).toEqual(mockScript);
            expect(api.get).toHaveBeenCalledWith('/api/v1/scripts/1');
        });
    });

    describe('executeScript', () => {
        it('posts an execute request', async () => {
            const req: ExecuteScriptRequest = {
                host_id: 'h1',
                saved_script_id: '1',
            };
            const response = { message: 'queued', execution_id: 'e1' };
            vi.mocked(api.post).mockResolvedValueOnce(resolve(response));

            const result = await scriptsService.executeScript(req);

            expect(result).toEqual(response);
            expect(api.post).toHaveBeenCalledWith('/api/v1/scripts/execute', req);
        });
    });

    describe('getScriptExecutions', () => {
        it('fetches executions with default paging', async () => {
            const payload = { executions: [], total: 0, page: 1, pages: 0 };
            vi.mocked(api.get).mockResolvedValueOnce(resolve(payload));

            const result = await scriptsService.getScriptExecutions();

            expect(result).toEqual(payload);
            expect(api.get).toHaveBeenCalledWith('/api/v1/scripts/executions/', {
                params: { page: 1, limit: 50 },
            });
        });

        it('fetches executions with custom paging', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve({}));

            await scriptsService.getScriptExecutions(2, 10);

            expect(api.get).toHaveBeenCalledWith('/api/v1/scripts/executions/', {
                params: { page: 2, limit: 10 },
            });
        });
    });

    describe('getScriptExecution', () => {
        it('fetches a single execution', async () => {
            const exec = { id: 'e1', host_id: 'h1' };
            vi.mocked(api.get).mockResolvedValueOnce(resolve(exec));

            const result = await scriptsService.getScriptExecution('e1');

            expect(result).toEqual(exec);
            expect(api.get).toHaveBeenCalledWith('/api/v1/scripts/executions/e1');
        });
    });

    describe('deleteScriptExecution', () => {
        it('deletes a single execution', async () => {
            vi.mocked(api.delete).mockResolvedValueOnce(resolve(undefined));

            await scriptsService.deleteScriptExecution('e1');

            expect(api.delete).toHaveBeenCalledWith('/api/v1/scripts/executions/e1');
        });
    });

    describe('deleteScriptExecutionsBulk', () => {
        it('sends a bulk delete request with stringified ids', async () => {
            vi.mocked(api.request).mockResolvedValueOnce(resolve(undefined));

            await scriptsService.deleteScriptExecutionsBulk([1, '2', 3]);

            expect(api.request).toHaveBeenCalledWith({
                method: 'DELETE',
                url: '/api/v1/scripts/executions/bulk',
                data: ['1', '2', '3'],
            });
        });
    });

    describe('getActiveHosts', () => {
        it('returns only approved hosts that are active or up', async () => {
            const hosts = [
                { id: '1', fqdn: 'a', status: 'up', active: true, approval_status: 'approved', last_access: '' },
                { id: '2', fqdn: 'b', status: 'up', active: false, approval_status: 'approved', last_access: '' },
                { id: '3', fqdn: 'c', status: 'down', active: false, approval_status: 'approved', last_access: '' },
                { id: '4', fqdn: 'd', status: 'up', active: true, approval_status: 'pending', last_access: '' },
            ];
            vi.mocked(api.get).mockResolvedValueOnce(resolve(hosts));

            const result = await scriptsService.getActiveHosts();

            expect(result.map((h) => h.id)).toEqual(['1', '2']);
            expect(api.get).toHaveBeenCalledWith('/api/v1/hosts');
        });
    });
});
