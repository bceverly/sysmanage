// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for hosts API service
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as hosts from '../hosts';
import api from '../api';

// Mock axios instance
vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

const ok = (data: unknown) =>
    ({
        data,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {} as unknown,
    }) as never;

describe('Hosts API Service', () => {
    let logSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
        vi.clearAllMocks();
        logSpy = vi.spyOn(window.console, 'log').mockImplementation(() => {});
    });

    afterEach(() => {
        logSpy.mockRestore();
    });

    describe('doDeleteHost', () => {
        it('calls DELETE and returns response data', async () => {
            const payload = { result: true };
            vi.mocked(api.delete).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doDeleteHost('42');

            expect(api.delete).toHaveBeenCalledWith('/api/v1/host/42');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.delete).mockRejectedValueOnce(new Error('boom'));
            await expect(hosts.doDeleteHost('42')).rejects.toThrow('boom');
        });
    });

    describe('doGetHostByID', () => {
        it('calls GET and returns host', async () => {
            const host = { id: '1', fqdn: 'a.example.com' };
            vi.mocked(api.get).mockResolvedValueOnce(ok(host));

            const result = await hosts.doGetHostByID('1');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/1');
            expect(result).toEqual(host);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('nope'));
            await expect(hosts.doGetHostByID('1')).rejects.toThrow('nope');
        });
    });

    describe('doGetHosts', () => {
        it('calls GET /hosts and returns array', async () => {
            const list = [{ id: '1' }, { id: '2' }];
            vi.mocked(api.get).mockResolvedValueOnce(ok(list));

            const result = await hosts.doGetHosts();

            expect(api.get).toHaveBeenCalledWith('/api/v1/hosts');
            expect(result).toEqual(list);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('fail'));
            await expect(hosts.doGetHosts()).rejects.toThrow('fail');
        });
    });

    describe('doApproveHost', () => {
        it('calls PUT approve and returns host', async () => {
            const host = { id: '7', approval_status: 'approved' };
            vi.mocked(api.put).mockResolvedValueOnce(ok(host));

            const result = await hosts.doApproveHost('7');

            expect(api.put).toHaveBeenCalledWith('/api/v1/host/7/approve');
            expect(result).toEqual(host);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.put).mockRejectedValueOnce(new Error('err'));
            await expect(hosts.doApproveHost('7')).rejects.toThrow('err');
        });
    });

    describe('doRefreshHostData', () => {
        it('calls POST request-os-update', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRefreshHostData('3');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/3/request-os-update');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('x'));
            await expect(hosts.doRefreshHostData('3')).rejects.toThrow('x');
        });
    });

    describe('doRefreshHardwareData', () => {
        it('calls POST request-hardware-update', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRefreshHardwareData('3');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/3/request-hardware-update');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('x'));
            await expect(hosts.doRefreshHardwareData('3')).rejects.toThrow('x');
        });
    });

    describe('doRefreshUpdatesCheck', () => {
        it('calls POST request-updates-check', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRefreshUpdatesCheck('3');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/3/request-updates-check');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('x'));
            await expect(hosts.doRefreshUpdatesCheck('3')).rejects.toThrow('x');
        });
    });

    describe('doRefreshAllHostData', () => {
        it('fires all four refresh requests and returns success', async () => {
            vi.mocked(api.post).mockResolvedValue(ok({ result: true }));

            const result = await hosts.doRefreshAllHostData('5');

            expect(result).toEqual({ result: true });
            expect(api.post).toHaveBeenCalledWith('/api/v1/host/5/request-os-update');
            expect(api.post).toHaveBeenCalledWith('/api/v1/host/5/request-hardware-update');
            expect(api.post).toHaveBeenCalledWith('/api/v1/host/5/request-updates-check');
            expect(api.post).toHaveBeenCalledWith('/api/v1/host/5/request-system-info');
            expect(api.post).toHaveBeenCalledTimes(4);
        });

        it('rejects if any sub-request fails', async () => {
            vi.mocked(api.post).mockRejectedValue(new Error('sub-fail'));
            await expect(hosts.doRefreshAllHostData('5')).rejects.toThrow('sub-fail');
        });
    });

    describe('doGetHostStorage', () => {
        it('calls GET storage and returns array', async () => {
            const devices = [{ id: 'd1' }];
            vi.mocked(api.get).mockResolvedValueOnce(ok(devices));

            const result = await hosts.doGetHostStorage('9');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/9/storage');
            expect(result).toEqual(devices);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doGetHostStorage('9')).rejects.toThrow('e');
        });
    });

    describe('doGetHostNetwork', () => {
        it('calls GET network and returns array', async () => {
            const nics = [{ id: 'n1', is_active: true }];
            vi.mocked(api.get).mockResolvedValueOnce(ok(nics));

            const result = await hosts.doGetHostNetwork('9');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/9/network');
            expect(result).toEqual(nics);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doGetHostNetwork('9')).rejects.toThrow('e');
        });
    });

    describe('doGetHostUsers', () => {
        it('calls GET users and returns array', async () => {
            const users = [{ id: 'u1', username: 'root', is_system_user: true, groups: [] }];
            vi.mocked(api.get).mockResolvedValueOnce(ok(users));

            const result = await hosts.doGetHostUsers('9');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/9/users');
            expect(result).toEqual(users);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doGetHostUsers('9')).rejects.toThrow('e');
        });
    });

    describe('doGetHostGroups', () => {
        it('calls GET groups and returns array', async () => {
            const groups = [{ id: 'g1', group_name: 'wheel', is_system_group: true, users: [] }];
            vi.mocked(api.get).mockResolvedValueOnce(ok(groups));

            const result = await hosts.doGetHostGroups('9');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/9/groups');
            expect(result).toEqual(groups);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doGetHostGroups('9')).rejects.toThrow('e');
        });
    });

    describe('doRefreshUserAccessData', () => {
        it('calls POST request-user-access-update', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRefreshUserAccessData('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/request-user-access-update');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doRefreshUserAccessData('9')).rejects.toThrow('e');
        });
    });

    describe('doRequestSystemInfo', () => {
        it('calls POST request-system-info', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRequestSystemInfo('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/request-system-info');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doRequestSystemInfo('9')).rejects.toThrow('e');
        });
    });

    describe('doGetHostSoftware', () => {
        it('uses default page/pageSize params', async () => {
            const payload = {
                items: [],
                pagination: {
                    page: 1,
                    page_size: 100,
                    total_items: 0,
                    total_pages: 0,
                    has_next: false,
                    has_prev: false,
                },
            };
            vi.mocked(api.get).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doGetHostSoftware('9');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/9/software?page=1&page_size=100');
            expect(result).toEqual(payload);
        });

        it('passes explicit page, pageSize and search', async () => {
            const payload = { items: [{ id: 'p1' }], pagination: {} };
            vi.mocked(api.get).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doGetHostSoftware('9', 2, 50, 'ssh');

            expect(api.get).toHaveBeenCalledWith(
                '/api/v1/host/9/software?page=2&page_size=50&search=ssh',
            );
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doGetHostSoftware('9')).rejects.toThrow('e');
        });
    });

    describe('doRefreshSoftwareData', () => {
        it('calls POST refresh software', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRefreshSoftwareData('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/refresh/software/9');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doRefreshSoftwareData('9')).rejects.toThrow('e');
        });
    });

    describe('doGetHostDiagnostics', () => {
        it('extracts diagnostics array from response', async () => {
            const reports = [{ id: 'r1' }];
            vi.mocked(api.get).mockResolvedValueOnce(ok({ host_id: '9', diagnostics: reports }));

            const result = await hosts.doGetHostDiagnostics('9');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/9/diagnostics');
            expect(result).toEqual(reports);
        });

        it('defaults to empty array when diagnostics missing', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(ok({ host_id: '9' }));

            const result = await hosts.doGetHostDiagnostics('9');

            expect(result).toEqual([]);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doGetHostDiagnostics('9')).rejects.toThrow('e');
        });
    });

    describe('doRequestHostDiagnostics', () => {
        it('calls POST collect-diagnostics', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRequestHostDiagnostics('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/collect-diagnostics');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doRequestHostDiagnostics('9')).rejects.toThrow('e');
        });
    });

    describe('doGetDiagnosticDetail', () => {
        it('calls GET diagnostic detail', async () => {
            const detail = { id: 'diag1', host_id: '9' };
            vi.mocked(api.get).mockResolvedValueOnce(ok(detail));

            const result = await hosts.doGetDiagnosticDetail('diag1');

            expect(api.get).toHaveBeenCalledWith('/api/v1/diagnostic/diag1');
            expect(result).toEqual(detail);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doGetDiagnosticDetail('diag1')).rejects.toThrow('e');
        });
    });

    describe('doDeleteDiagnostic', () => {
        it('calls DELETE diagnostic', async () => {
            const payload = { result: true };
            vi.mocked(api.delete).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doDeleteDiagnostic('diag1');

            expect(api.delete).toHaveBeenCalledWith('/api/v1/diagnostic/diag1');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.delete).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doDeleteDiagnostic('diag1')).rejects.toThrow('e');
        });
    });

    describe('doRebootHost', () => {
        it('calls POST reboot', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRebootHost('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/reboot/9');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doRebootHost('9')).rejects.toThrow('e');
        });
    });

    describe('doShutdownHost', () => {
        it('calls POST shutdown', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doShutdownHost('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/shutdown/9');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doShutdownHost('9')).rejects.toThrow('e');
        });
    });

    describe('doUpdateAgent', () => {
        it('calls POST update-agent', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doUpdateAgent('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/update-agent/9');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doUpdateAgent('9')).rejects.toThrow('e');
        });
    });

    describe('doRequestPackages', () => {
        it('calls POST request-packages', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRequestPackages('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/request-packages');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doRequestPackages('9')).rejects.toThrow('e');
        });
    });

    describe('doGetHostUbuntuPro', () => {
        it('calls GET ubuntu-pro', async () => {
            const info = { available: true, attached: false };
            vi.mocked(api.get).mockResolvedValueOnce(ok(info));

            const result = await hosts.doGetHostUbuntuPro('9');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/9/ubuntu-pro');
            expect(result).toEqual(info);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doGetHostUbuntuPro('9')).rejects.toThrow('e');
        });
    });

    describe('doAttachUbuntuPro', () => {
        it('calls POST attach with token body', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doAttachUbuntuPro('9', 'tok123');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/ubuntu-pro/attach', {
                token: 'tok123',
            });
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doAttachUbuntuPro('9', 'tok123')).rejects.toThrow('e');
        });
    });

    describe('doDetachUbuntuPro', () => {
        it('calls POST detach', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doDetachUbuntuPro('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/ubuntu-pro/detach');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doDetachUbuntuPro('9')).rejects.toThrow('e');
        });
    });

    describe('doEnableUbuntuProService', () => {
        it('calls POST service enable with service body', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doEnableUbuntuProService('9', 'esm-infra');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/ubuntu-pro/service/enable', {
                service: 'esm-infra',
            });
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doEnableUbuntuProService('9', 'esm-infra')).rejects.toThrow('e');
        });
    });

    describe('doDisableUbuntuProService', () => {
        it('calls POST service disable with service body', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doDisableUbuntuProService('9', 'esm-apps');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/ubuntu-pro/service/disable', {
                service: 'esm-apps',
            });
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doDisableUbuntuProService('9', 'esm-apps')).rejects.toThrow('e');
        });
    });

    describe('doRebootPreCheck', () => {
        it('calls GET reboot pre-check', async () => {
            const payload = {
                has_running_children: false,
                running_children: [],
                running_count: 0,
                total_children: 0,
                has_container_engine: false,
            };
            vi.mocked(api.get).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doRebootPreCheck('9');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/9/reboot/pre-check');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doRebootPreCheck('9')).rejects.toThrow('e');
        });
    });

    describe('doOrchestratedReboot', () => {
        it('calls POST orchestrated reboot', async () => {
            const payload = { orchestration_id: 'orch1', status: 'pending', child_count: 2 };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doOrchestratedReboot('9');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/reboot/orchestrated');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doOrchestratedReboot('9')).rejects.toThrow('e');
        });
    });

    describe('getRebootOrchestrationStatus', () => {
        it('calls GET orchestration status', async () => {
            const payload = { orchestration_id: 'orch1', status: 'running' };
            vi.mocked(api.get).mockResolvedValueOnce(ok(payload));

            const result = await hosts.getRebootOrchestrationStatus('9', 'orch1');

            expect(api.get).toHaveBeenCalledWith('/api/v1/host/9/reboot/orchestration/orch1');
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.getRebootOrchestrationStatus('9', 'orch1')).rejects.toThrow('e');
        });
    });

    describe('doChangeHostname', () => {
        it('calls POST change-hostname with new_hostname body', async () => {
            const payload = { result: true };
            vi.mocked(api.post).mockResolvedValueOnce(ok(payload));

            const result = await hosts.doChangeHostname('9', 'newname.example.com');

            expect(api.post).toHaveBeenCalledWith('/api/v1/host/9/change-hostname', {
                new_hostname: 'newname.example.com',
            });
            expect(result).toEqual(payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('e'));
            await expect(hosts.doChangeHostname('9', 'newname')).rejects.toThrow('e');
        });
    });
});
