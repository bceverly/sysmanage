// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, afterEach, test, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { TFunction } from 'i18next';

vi.mock('../../../Services/api', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import axiosInstance from '../../../Services/api';
import { useHostRolesAndCerts } from '../useHostRolesAndCerts';
import type { SysManageHost } from '../../../Services/hosts';

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;
const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

const makeHost = (over: Partial<SysManageHost> = {}): SysManageHost =>
    ({ id: 'h1', active: true, ...over } as unknown as SysManageHost);

const setSnackbarMessage = vi.fn();
const setSnackbarSeverity = vi.fn();
const setSnackbarOpen = vi.fn();

const setup = (over: Partial<Parameters<typeof useHostRolesAndCerts>[0]> = {}) =>
    renderHook(() =>
        useHostRolesAndCerts({
            hostId: 'h1',
            host: makeHost(),
            currentTabId: 'info',
            t,
            setSnackbarMessage,
            setSnackbarSeverity,
            setSnackbarOpen,
            ...over,
        }),
    );

const role = (id: string, service_name: string | null = 'nginx') =>
    ({ id, service_name }) as unknown as { id: string; service_name: string | null };

beforeEach(() => {
    vi.clearAllMocks();
});
afterEach(() => {
    vi.restoreAllMocks();
});

describe('certificates', () => {
    test('a 200 populates the list', async () => {
        mockGet.mockResolvedValue({ status: 200, data: { certificates: [{ id: 'c1' }] } });
        const { result } = setup();
        await act(async () => { await result.current.fetchCertificates(); });
        expect(result.current.certificates).toEqual([{ id: 'c1' }]);
        expect(result.current.certificatesLoading).toBe(false);
    });

    test('a missing certificates key yields an empty list, not undefined', async () => {
        mockGet.mockResolvedValue({ status: 200, data: {} });
        const { result } = setup();
        await act(async () => { await result.current.fetchCertificates(); });
        expect(result.current.certificates).toEqual([]);
    });

    test('a failure clears the list instead of failing the page', async () => {
        // Certificates are optional data on Host Detail; an error here must not
        // take the whole page down with it.
        mockGet.mockRejectedValue(new Error('boom'));
        const { result } = setup();
        await act(async () => { await result.current.fetchCertificates(); });
        expect(result.current.certificates).toEqual([]);
        expect(result.current.certificatesLoading).toBe(false);
    });

    test('no hostId means no request at all', async () => {
        const { result } = setup({ hostId: undefined });
        await act(async () => { await result.current.fetchCertificates(); });
        expect(mockGet).not.toHaveBeenCalled();
    });
});

describe('certificate collection request', () => {
    test('success reports through the snackbar and schedules a refetch', async () => {
        vi.useFakeTimers();
        mockPost.mockResolvedValue({ status: 200 });
        mockGet.mockResolvedValue({ status: 200, data: { certificates: [{ id: 'c9' }] } });
        const { result } = setup();

        await act(async () => { await result.current.requestCertificatesCollection(); });
        expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        expect(setSnackbarOpen).toHaveBeenCalledWith(true);
        // The refetch is deliberately delayed to let collection finish.
        expect(mockGet).not.toHaveBeenCalled();

        await act(async () => { vi.advanceTimersByTime(3000); });
        expect(mockGet).toHaveBeenCalled();
        vi.useRealTimers();
    });

    test('failure reports an error severity', async () => {
        mockPost.mockRejectedValue(new Error('nope'));
        const { result } = setup();
        await act(async () => { await result.current.requestCertificatesCollection(); });
        expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        expect(result.current.certificatesLoading).toBe(false);
    });
});

describe('roles', () => {
    test('a 200 populates roles', async () => {
        mockGet.mockResolvedValue({ status: 200, data: { roles: [role('r1')] } });
        const { result } = setup();
        await act(async () => { await result.current.fetchRoles(); });
        expect(result.current.roles).toHaveLength(1);
        expect(result.current.rolesLoading).toBe(false);
    });

    test('showLoading=false never raises the loading flag', async () => {
        // This is the path the 30s auto-refresh uses: the table must not flash a
        // spinner every half minute while the operator is reading it.
        // Deferred so the request is still in flight while we assert the flag.
        const deferred: { resolve?: () => void } = {};
        mockGet.mockReturnValue(
            new Promise(r => {
                deferred.resolve = () => r({ status: 200, data: { roles: [] } });
            }),
        );
        const { result } = setup();
        act(() => { void result.current.fetchRoles(false); });
        expect(result.current.rolesLoading).toBe(false);
        await act(async () => { deferred.resolve?.(); });
    });

    test('a failure clears roles rather than failing the page', async () => {
        mockGet.mockRejectedValue(new Error('boom'));
        const { result } = setup();
        await act(async () => { await result.current.fetchRoles(); });
        expect(result.current.roles).toEqual([]);
    });

    test('requestRolesCollection success schedules a refetch', async () => {
        vi.useFakeTimers();
        mockPost.mockResolvedValue({ status: 200 });
        mockGet.mockResolvedValue({ status: 200, data: { roles: [] } });
        const { result } = setup();
        await act(async () => { await result.current.requestRolesCollection(); });
        expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        await act(async () => { vi.advanceTimersByTime(3000); });
        expect(mockGet).toHaveBeenCalled();
        vi.useRealTimers();
    });

    test('requestRolesCollection failure reports an error', async () => {
        mockPost.mockRejectedValue(new Error('nope'));
        const { result } = setup();
        await act(async () => { await result.current.requestRolesCollection(); });
        expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
    });
});

describe('role selection', () => {
    test('add and remove are independent', () => {
        const { result } = setup();
        act(() => { result.current.addRoleToSelection('a'); });
        act(() => { result.current.addRoleToSelection('b'); });
        expect(result.current.selectedRoles).toEqual(['a', 'b']);
        act(() => { result.current.removeRoleFromSelection('a'); });
        expect(result.current.selectedRoles).toEqual(['b']);
    });

    test('select-all skips roles with no service to control', async () => {
        // A role without a service_name cannot be started or stopped, so
        // selecting it would arm a button that can only fail.
        mockGet.mockResolvedValue({
            status: 200,
            data: { roles: [role('r1', 'nginx'), role('r2', null), role('r3', '   ')] },
        });
        const { result } = setup();
        await act(async () => { await result.current.fetchRoles(); });
        act(() => { result.current.selectAllRoles(); });
        expect(result.current.selectedRoles).toEqual(['r1']);
        act(() => { result.current.deselectAllRoles(); });
        expect(result.current.selectedRoles).toEqual([]);
    });
});

describe('service control', () => {
    const withSelection = async () => {
        mockGet.mockResolvedValue({ status: 200, data: { roles: [role('r1', 'nginx')] } });
        const hook = setup();
        await act(async () => { await hook.result.current.fetchRoles(); });
        act(() => { hook.result.current.addRoleToSelection('r1'); });
        return hook;
    };

    test('nothing selected means no request', async () => {
        const { result } = setup();
        await act(async () => { await result.current.handleServiceControl('start'); });
        expect(mockPost).not.toHaveBeenCalled();
    });

    test('a successful action posts the service names and clears the selection', async () => {
        vi.useFakeTimers();
        const { result } = await withSelection();
        mockPost.mockResolvedValue({ status: 200 });
        await act(async () => { await result.current.handleServiceControl('restart'); });

        expect(mockPost).toHaveBeenCalledWith(
            '/api/v1/host/h1/service-control',
            { action: 'restart', services: ['nginx'] },
        );
        expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        expect(result.current.selectedRoles).toEqual([]);
        await act(async () => { vi.advanceTimersByTime(3000); });
        vi.useRealTimers();
    });

    test('selected roles with no service_name warn instead of posting', async () => {
        mockGet.mockResolvedValue({ status: 200, data: { roles: [role('r1', null)] } });
        const { result } = setup();
        await act(async () => { await result.current.fetchRoles(); });
        act(() => { result.current.addRoleToSelection('r1'); });
        await act(async () => { await result.current.handleServiceControl('stop'); });

        expect(mockPost).not.toHaveBeenCalled();
        expect(setSnackbarSeverity).toHaveBeenCalledWith('warning');
    });

    test('a failed action reports an error and drops the loading flag', async () => {
        const { result } = await withSelection();
        mockPost.mockRejectedValue(new Error('boom'));
        await act(async () => { await result.current.handleServiceControl('start'); });
        expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        expect(result.current.serviceControlLoading).toBe(false);
    });
});

describe('auto-refresh', () => {
    test('polls only while the server-roles tab is open on an active host', async () => {
        vi.useFakeTimers();
        mockGet.mockResolvedValue({ status: 200, data: { roles: [] } });
        const { rerender, unmount } = renderHook(
            ({ tab }: { tab: string }) =>
                useHostRolesAndCerts({
                    hostId: 'h1',
                    host: makeHost(),
                    currentTabId: tab,
                    t,
                    setSnackbarMessage,
                    setSnackbarSeverity,
                    setSnackbarOpen,
                }),
            { initialProps: { tab: 'info' } },
        );

        await act(async () => { vi.advanceTimersByTime(31000); });
        expect(mockGet).not.toHaveBeenCalled();

        rerender({ tab: 'server-roles' });
        await act(async () => { vi.advanceTimersByTime(31000); });
        expect(mockGet).toHaveBeenCalled();

        // Leaving the tab must stop the timer, or a long-lived page accumulates
        // one poll per tab visit for ever.
        const after = mockGet.mock.calls.length;
        rerender({ tab: 'info' });
        await act(async () => { vi.advanceTimersByTime(120000); });
        expect(mockGet.mock.calls.length).toBe(after);

        unmount();
        vi.useRealTimers();
    });

    test('an inactive host is never polled', async () => {
        vi.useFakeTimers();
        mockGet.mockResolvedValue({ status: 200, data: { roles: [] } });
        renderHook(() =>
            useHostRolesAndCerts({
                hostId: 'h1',
                host: makeHost({ active: false } as Partial<SysManageHost>),
                currentTabId: 'server-roles',
                t,
                setSnackbarMessage,
                setSnackbarSeverity,
                setSnackbarOpen,
            }),
        );
        await act(async () => { vi.advanceTimersByTime(90000); });
        expect(mockGet).not.toHaveBeenCalled();
        vi.useRealTimers();
    });
});
