// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, afterEach, test, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { TFunction } from 'i18next';

vi.mock('../../../Services/api', () => ({
    default: { get: vi.fn() },
}));

vi.mock('../../../Services/hosts', () => ({
    doGetHostByID: vi.fn(),
    doGetHostDiagnostics: vi.fn(),
    doRequestHostDiagnostics: vi.fn(),
    doGetDiagnosticDetail: vi.fn(),
    doDeleteDiagnostic: vi.fn(),
    doRebootHost: vi.fn(),
    doShutdownHost: vi.fn(),
    doUpdateAgent: vi.fn(),
    doRequestSystemInfo: vi.fn(),
    doRefreshUserAccessData: vi.fn(),
    doRefreshSoftwareData: vi.fn(),
    doRefreshUpdatesCheck: vi.fn(),
    doChangeHostname: vi.fn(),
    doRebootPreCheck: vi.fn(),
    doOrchestratedReboot: vi.fn(),
    getRebootOrchestrationStatus: vi.fn(),
}));

import axiosInstance from '../../../Services/api';
import * as hosts from '../../../Services/hosts';
import { useHostLifecycle } from '../useHostLifecycle';
import type { SysManageHost } from '../../../Services/hosts';

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

const makeHost = (over: Partial<SysManageHost> = {}): SysManageHost =>
    ({ id: 'h1', active: true, fqdn: 'box.example.com', ...over } as unknown as SysManageHost);

interface SetupOpts {
    hostId?: string | undefined;
    host?: SysManageHost | null;
    supportsChildHosts?: () => boolean;
}

const setup = (opts: SetupOpts = {}) => {
    const setHost = vi.fn();
    const setSnackbarMessage = vi.fn();
    const setSnackbarSeverity = vi.fn();
    const setSnackbarOpen = vi.fn();
    const fetchVirtualizationStatus = vi.fn().mockResolvedValue(undefined);
    const props = {
        hostId: 'hostId' in opts ? opts.hostId : 'h1',
        host: 'host' in opts ? (opts.host as SysManageHost | null) : makeHost(),
        setHost,
        supportsChildHosts: opts.supportsChildHosts ?? (() => false),
        fetchVirtualizationStatus,
        t,
        setSnackbarMessage,
        setSnackbarSeverity,
        setSnackbarOpen,
    };
    const utils = renderHook((p: typeof props) => useHostLifecycle(p), { initialProps: props });
    return { ...utils, setHost, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen, fetchVirtualizationStatus };
};

describe('useHostLifecycle', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.useFakeTimers();
        m(axiosInstance.get).mockResolvedValue({ status: 200, data: {} });
        m(hosts.doRequestHostDiagnostics).mockResolvedValue({});
        m(hosts.doRequestSystemInfo).mockResolvedValue({});
        m(hosts.doRefreshUserAccessData).mockResolvedValue({});
        m(hosts.doRefreshSoftwareData).mockResolvedValue({});
        m(hosts.doRefreshUpdatesCheck).mockResolvedValue({});
        m(hosts.doGetHostByID).mockResolvedValue(makeHost({ diagnostics_request_status: 'complete' }));
        m(hosts.doGetHostDiagnostics).mockResolvedValue([]);
        m(hosts.doGetDiagnosticDetail).mockResolvedValue({ id: 'd1' });
        m(hosts.doDeleteDiagnostic).mockResolvedValue({});
        m(hosts.doRebootHost).mockResolvedValue({});
        m(hosts.doShutdownHost).mockResolvedValue({});
        m(hosts.doUpdateAgent).mockResolvedValue({});
        m(hosts.doChangeHostname).mockResolvedValue({});
        m(hosts.doRebootPreCheck).mockResolvedValue({ has_running_children: false, has_container_engine: false });
        m(hosts.doOrchestratedReboot).mockResolvedValue({ orchestration_id: 'orch1', child_count: 2 });
        m(hosts.getRebootOrchestrationStatus).mockResolvedValue({ status: 'in_progress' });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    test('initial state', () => {
        const { result } = setup();
        expect(result.current.diagnosticsData).toEqual([]);
        expect(result.current.rebootConfirmOpen).toBe(false);
    });

    describe('handleRequestDiagnostics', () => {
        test('no hostId → noop', async () => {
            const { result } = setup({ hostId: undefined });
            await act(async () => {
                await result.current.handleRequestDiagnostics();
            });
            expect(hosts.doRequestHostDiagnostics).not.toHaveBeenCalled();
        });

        test('success requests all data and refreshes host', async () => {
            const { result, setHost } = setup();
            await act(async () => {
                await result.current.handleRequestDiagnostics();
            });
            expect(hosts.doRequestHostDiagnostics).toHaveBeenCalledWith('h1');
            expect(hosts.doRequestSystemInfo).toHaveBeenCalledWith('h1');
            expect(setHost).toHaveBeenCalled();
        });

        test('supportsChildHosts adds virtualization request', async () => {
            const { result } = setup({ supportsChildHosts: () => true });
            await act(async () => {
                await result.current.handleRequestDiagnostics();
            });
            expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/host/h1/virtualization');
        });

        test('pending status triggers polling until complete', async () => {
            m(hosts.doGetHostByID)
                .mockResolvedValueOnce(makeHost({ diagnostics_request_status: 'pending' }))
                .mockResolvedValueOnce(makeHost({ diagnostics_request_status: 'complete' }));
            const { result } = setup();
            await act(async () => {
                await result.current.handleRequestDiagnostics();
            });
            await act(async () => {
                await vi.advanceTimersByTimeAsync(3500);
            });
            expect(hosts.doGetHostDiagnostics).toHaveBeenCalledWith('h1');
        });

        test('request error is swallowed', async () => {
            m(hosts.doRequestHostDiagnostics).mockRejectedValueOnce(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                await result.current.handleRequestDiagnostics();
            });
            expect(result.current.diagnosticsLoading).toBe(false);
        });
    });

    describe('diagnostic detail + delete', () => {
        test('handleDeleteDiagnostic opens confirm', () => {
            const { result } = setup();
            act(() => result.current.handleDeleteDiagnostic('d9'));
            expect(result.current.deleteConfirmOpen).toBe(true);
        });

        test('handleViewDiagnosticDetail success', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleViewDiagnosticDetail('d1');
            });
            expect(result.current.selectedDiagnostic).toEqual({ id: 'd1' });
            expect(result.current.diagnosticDetailOpen).toBe(true);
        });

        test('handleViewDiagnosticDetail error closes dialog', async () => {
            m(hosts.doGetDiagnosticDetail).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleViewDiagnosticDetail('d1');
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
            expect(result.current.diagnosticDetailOpen).toBe(false);
        });

        test('handleConfirmDelete no selection → noop', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleConfirmDelete();
            });
            expect(hosts.doDeleteDiagnostic).not.toHaveBeenCalled();
        });

        test('handleConfirmDelete success refreshes', async () => {
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleDeleteDiagnostic('d9'));
            await act(async () => {
                await result.current.handleConfirmDelete();
            });
            expect(hosts.doDeleteDiagnostic).toHaveBeenCalledWith('d9');
            expect(hosts.doGetHostDiagnostics).toHaveBeenCalled();
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('handleConfirmDelete refresh error still succeeds', async () => {
            m(hosts.doGetHostDiagnostics).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleDeleteDiagnostic('d9'));
            await act(async () => {
                await result.current.handleConfirmDelete();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('handleConfirmDelete delete error', async () => {
            m(hosts.doDeleteDiagnostic).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleDeleteDiagnostic('d9'));
            await act(async () => {
                await result.current.handleConfirmDelete();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });

        test('handleCancelDelete closes', () => {
            const { result } = setup();
            act(() => result.current.handleDeleteDiagnostic('d9'));
            act(() => result.current.handleCancelDelete());
            expect(result.current.deleteConfirmOpen).toBe(false);
        });
    });

    describe('reboot', () => {
        test('handleRebootClick without child support skips pre-check', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleRebootClick();
            });
            expect(hosts.doRebootPreCheck).not.toHaveBeenCalled();
            expect(result.current.rebootConfirmOpen).toBe(true);
        });

        test('handleRebootClick with child support runs pre-check', async () => {
            const { result } = setup({ supportsChildHosts: () => true });
            await act(async () => {
                await result.current.handleRebootClick();
            });
            expect(hosts.doRebootPreCheck).toHaveBeenCalledWith('h1');
            expect(result.current.rebootConfirmOpen).toBe(true);
        });

        test('handleRebootClick pre-check error clears data', async () => {
            m(hosts.doRebootPreCheck).mockRejectedValueOnce(new Error('boom'));
            const { result } = setup({ supportsChildHosts: () => true });
            await act(async () => {
                await result.current.handleRebootClick();
            });
            expect(result.current.rebootPreCheckData).toBeNull();
        });

        test('handleRebootConfirm standard path', async () => {
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleRebootConfirm();
            });
            expect(hosts.doRebootHost).toHaveBeenCalledWith('h1');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('handleRebootConfirm orchestrated path', async () => {
            const { result } = setup();
            act(() =>
                result.current.setRebootPreCheckData({
                    has_running_children: true,
                    has_container_engine: true,
                } as never),
            );
            await act(async () => {
                await result.current.handleRebootConfirm();
            });
            expect(hosts.doOrchestratedReboot).toHaveBeenCalledWith('h1');
            expect(result.current.rebootOrchestrationId).toBe('orch1');
        });

        test('handleRebootConfirm error', async () => {
            m(hosts.doRebootHost).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleRebootConfirm();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });

        test('orchestration polling reports completion', async () => {
            m(hosts.getRebootOrchestrationStatus).mockResolvedValue({ status: 'completed', error_message: null });
            const { result, setSnackbarSeverity } = setup();
            act(() =>
                result.current.setRebootPreCheckData({
                    has_running_children: true,
                    has_container_engine: true,
                } as never),
            );
            await act(async () => {
                await result.current.handleRebootConfirm();
            });
            await act(async () => {
                await vi.advanceTimersByTimeAsync(100);
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('orchestration polling reports failure', async () => {
            m(hosts.getRebootOrchestrationStatus).mockResolvedValue({ status: 'failed', error_message: 'kaboom' });
            const { result, setSnackbarSeverity } = setup();
            act(() =>
                result.current.setRebootPreCheckData({
                    has_running_children: true,
                    has_container_engine: true,
                } as never),
            );
            await act(async () => {
                await result.current.handleRebootConfirm();
            });
            await act(async () => {
                await vi.advanceTimersByTimeAsync(100);
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });

    describe('shutdown', () => {
        test('handleShutdownClick opens confirm', () => {
            const { result } = setup();
            act(() => result.current.handleShutdownClick());
            expect(result.current.shutdownConfirmOpen).toBe(true);
        });

        test('handleShutdownConfirm success', async () => {
            const { result, setSnackbarOpen } = setup();
            await act(async () => {
                await result.current.handleShutdownConfirm();
            });
            expect(hosts.doShutdownHost).toHaveBeenCalledWith('h1');
            expect(setSnackbarOpen).toHaveBeenCalledWith(true);
        });

        test('handleShutdownConfirm error', async () => {
            m(hosts.doShutdownHost).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarMessage } = setup();
            await act(async () => {
                await result.current.handleShutdownConfirm();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith(expect.stringContaining('Failed'));
        });

        test('no host → noop', async () => {
            const { result } = setup({ host: null });
            await act(async () => {
                await result.current.handleShutdownConfirm();
            });
            expect(hosts.doShutdownHost).not.toHaveBeenCalled();
        });
    });

    describe('update agent', () => {
        test('success', async () => {
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleUpdateAgent();
            });
            expect(hosts.doUpdateAgent).toHaveBeenCalledWith('h1');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('error', async () => {
            m(hosts.doUpdateAgent).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleUpdateAgent();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });

    describe('hostname edit', () => {
        test('handleHostnameEditClick seeds from fqdn', () => {
            const { result } = setup();
            act(() => result.current.handleHostnameEditClick());
            expect(result.current.newHostname).toBe('box.example.com');
            expect(result.current.hostnameEditOpen).toBe(true);
        });

        test('handleHostnameChange empty → noop', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleHostnameChange();
            });
            expect(hosts.doChangeHostname).not.toHaveBeenCalled();
        });

        test('handleHostnameChange success', async () => {
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.setNewHostname('new.example.com'));
            await act(async () => {
                await result.current.handleHostnameChange();
            });
            expect(hosts.doChangeHostname).toHaveBeenCalledWith('h1', 'new.example.com');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('handleHostnameChange error', async () => {
            m(hosts.doChangeHostname).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.setNewHostname('new.example.com'));
            await act(async () => {
                await result.current.handleHostnameChange();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });
});
