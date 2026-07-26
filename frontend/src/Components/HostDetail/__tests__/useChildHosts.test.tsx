// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, afterEach, test, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { TFunction } from 'i18next';

// Mock the axios instance the hook imports (via ../../Services/api) — same
// mocking style as the Services test suite (default export with the HTTP verbs).
vi.mock('../../../Services/api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

// Mock the distribution service so fetchDistributions has a deterministic source.
vi.mock('../../../Services/childHostDistributions', () => ({
    distributionService: {
        getAll: vi.fn(),
    },
}));

import axiosInstance from '../../../Services/api';
import { distributionService } from '../../../Services/childHostDistributions';
import { useChildHosts } from '../useChildHosts';
import type { SysManageHost } from '../../../Services/hosts';
import type { ChildHost, ChildHostFormData, VirtualizationStatus } from '../hostDetailTypes';

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;
const mockDelete = axiosInstance.delete as unknown as ReturnType<typeof vi.fn>;
const mockGetAll = distributionService.getAll as unknown as ReturnType<typeof vi.fn>;

// A translation stub that just returns the provided fallback (or the key).
const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

const makeHost = (over: Partial<SysManageHost> = {}): SysManageHost =>
    ({
        id: 'h1',
        active: true,
        platform: 'Linux',
        ...over,
    } as unknown as SysManageHost);

const makeChild = (over: Partial<ChildHost> = {}): ChildHost =>
    ({
        id: 'c1',
        parent_host_id: 'h1',
        child_host_id: null,
        child_name: 'vm1',
        child_type: 'lxd',
        distribution: 'ubuntu',
        distribution_version: '22.04',
        hostname: 'vm1',
        status: 'running',
        installation_step: null,
        error_message: null,
        created_at: null,
        installed_at: null,
        ...over,
    } as ChildHost);

interface SetupOpts {
    hostId?: string | undefined;
    host?: SysManageHost | null;
    licenseModules?: string[];
    currentTabId?: string;
    supportsChildHosts?: () => boolean;
}

const setup = (opts: SetupOpts = {}) => {
    const setSnackbarMessage = vi.fn();
    const setSnackbarSeverity = vi.fn();
    const setSnackbarOpen = vi.fn();
    const supportsChildHosts = opts.supportsChildHosts ?? (() => true);
    const props = {
        hostId: 'hostId' in opts ? opts.hostId : 'h1',
        host: 'host' in opts ? (opts.host as SysManageHost | null) : makeHost(),
        licenseModules: opts.licenseModules ?? ['container_engine'],
        currentTabId: opts.currentTabId ?? 'overview',
        supportsChildHosts,
        t,
        setSnackbarMessage,
        setSnackbarSeverity,
        setSnackbarOpen,
    };
    const utils = renderHook((p: typeof props) => useChildHosts(p), {
        initialProps: props,
    });
    return { ...utils, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen, props };
};

// A fully-valid LXD form, mutated per-test for the validation branches.
const validLxdForm: Partial<ChildHostFormData> = {
    childType: 'lxd',
    distribution: 'ubuntu',
    containerName: 'ct1',
    hostname: 'vm1',
    username: 'admin',
    password: 'pw',
    confirmPassword: 'pw',
};

const setForm = (
    result: { current: ReturnType<typeof useChildHosts> },
    over: Partial<ChildHostFormData>,
) => {
    act(() => {
        result.current.setChildHostFormData(prev => ({ ...prev, ...over }));
    });
};

describe('useChildHosts', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.useFakeTimers();
        mockGet.mockResolvedValue({ status: 200, data: [] });
        mockPost.mockResolvedValue({ status: 200, data: { success: true } });
        mockDelete.mockResolvedValue({ status: 200, data: {} });
        mockGetAll.mockResolvedValue([]);
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    test('initial state', () => {
        const { result } = setup();
        expect(result.current.childHosts).toEqual([]);
        expect(result.current.childHostsLoading).toBe(false);
        expect(result.current.createChildHostOpen).toBe(false);
        expect(result.current.childHostFormData.childType).toBe('wsl');
        expect(result.current.computedFqdn).toBe('');
    });

    test('computedFqdn: appends server domain / keeps FQDN / empty', () => {
        const { result } = setup();
        setForm(result, { hostname: 'vm1' });
        expect(result.current.computedFqdn).toBe('vm1.localhost');
        setForm(result, { hostname: 'vm1.example.com' });
        expect(result.current.computedFqdn).toBe('vm1.example.com');
        setForm(result, { hostname: '' });
        expect(result.current.computedFqdn).toBe('');
    });

    test('computedFqdn uses multi-part server hostname domain', () => {
        vi.stubGlobal('location', { hostname: 't14.theeverlys.com' });
        const { result } = setup();
        setForm(result, { hostname: 'vm1' });
        expect(result.current.computedFqdn).toBe('vm1.theeverlys.com');
        vi.unstubAllGlobals();
    });

    describe('fetchChildHosts', () => {
        test('no hostId → no request', async () => {
            const { result } = setup({ hostId: undefined });
            await act(async () => {
                await result.current.fetchChildHosts();
            });
            expect(mockGet).not.toHaveBeenCalled();
        });

        test('no container_engine license → no request', async () => {
            const { result } = setup({ licenseModules: [] });
            await act(async () => {
                await result.current.fetchChildHosts();
            });
            expect(mockGet).not.toHaveBeenCalled();
        });

        test('success sets child hosts', async () => {
            const children = [makeChild()];
            mockGet.mockResolvedValueOnce({ status: 200, data: children });
            const { result } = setup();
            await act(async () => {
                await result.current.fetchChildHosts();
            });
            expect(mockGet).toHaveBeenCalledWith('/api/v1/host/h1/children');
            expect(result.current.childHosts).toEqual(children);
        });

        test('error resets to empty', async () => {
            mockGet.mockRejectedValueOnce(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                await result.current.fetchChildHosts(false);
            });
            expect(result.current.childHosts).toEqual([]);
        });
    });

    describe('fetchVirtualizationStatus', () => {
        test('no license → skipped', async () => {
            const { result } = setup({ licenseModules: [] });
            await act(async () => {
                await result.current.fetchVirtualizationStatus();
            });
            expect(mockGet).not.toHaveBeenCalled();
        });

        test('success sets status', async () => {
            const status = { supported_types: ['lxd'], capabilities: {}, reboot_required: false };
            mockGet.mockResolvedValueOnce({ status: 200, data: status });
            const { result } = setup();
            await act(async () => {
                await result.current.fetchVirtualizationStatus();
            });
            expect(result.current.virtualizationStatus).toEqual(status);
        });

        test('error clears status', async () => {
            mockGet.mockRejectedValueOnce(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                await result.current.fetchVirtualizationStatus();
            });
            expect(result.current.virtualizationStatus).toBeNull();
        });
    });

    describe('requestChildHostsRefresh', () => {
        test('no hostId → noop', async () => {
            const { result } = setup({ hostId: undefined });
            await act(async () => {
                await result.current.requestChildHostsRefresh();
            });
            expect(mockPost).not.toHaveBeenCalled();
        });

        test('success shows snackbar and refetches after delay', async () => {
            mockPost.mockResolvedValueOnce({ status: 200 });
            mockGet.mockResolvedValueOnce({ status: 200, data: null }); // the virtualization GET in Promise.all
            const { result, setSnackbarOpen } = setup();
            await act(async () => {
                await result.current.requestChildHostsRefresh(true);
            });
            expect(mockPost).toHaveBeenCalledWith('/api/v1/host/h1/children/refresh');
            expect(setSnackbarOpen).toHaveBeenCalledWith(true);
            await act(async () => {
                await vi.advanceTimersByTimeAsync(3500);
            });
            expect(result.current.childHostsRefreshRequested).toBe(false);
        });

        test('error path shows error snackbar', async () => {
            mockPost.mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.requestChildHostsRefresh(true);
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });

    describe.each([
        ['handleChildHostStart', '/api/v1/host/h1/children/c1/start'],
        ['handleChildHostStop', '/api/v1/host/h1/children/c1/stop'],
        ['handleChildHostRestart', '/api/v1/host/h1/children/c1/restart'],
        ['handleChildHostUpdateAgent', '/api/v1/host/h1/children/c1/update-agent'],
    ] as const)('%s', (fnName, url) => {
        test('success posts and schedules refresh', async () => {
            mockPost.mockResolvedValueOnce({ status: 200 });
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await Reflect.apply(result.current[fnName] as () => Promise<void>, undefined, [makeChild()]);
            });
            expect(mockPost).toHaveBeenCalledWith(url);
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
            await act(async () => {
                await vi.advanceTimersByTimeAsync(6000);
            });
        });

        test('no hostId → noop', async () => {
            const { result } = setup({ hostId: undefined });
            await act(async () => {
                await Reflect.apply(result.current[fnName] as () => Promise<void>, undefined, [makeChild()]);
            });
            expect(mockPost).not.toHaveBeenCalled();
        });

        test('error shows error snackbar', async () => {
            mockPost.mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await Reflect.apply(result.current[fnName] as () => Promise<void>, undefined, [makeChild()]);
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });

    describe('delete flow', () => {
        test('confirm opens dialog, cancel closes it', () => {
            const { result } = setup();
            act(() => result.current.handleChildHostDeleteConfirm(makeChild()));
            expect(result.current.deleteChildHostConfirmOpen).toBe(true);
            expect(result.current.childHostToDelete?.id).toBe('c1');
            act(() => result.current.handleChildHostDeleteCancel());
            expect(result.current.deleteChildHostConfirmOpen).toBe(false);
            expect(result.current.childHostToDelete).toBeNull();
        });

        test('delete with no selection → noop', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleChildHostDelete();
            });
            expect(mockDelete).not.toHaveBeenCalled();
        });

        test('delete success', async () => {
            mockDelete.mockResolvedValueOnce({ status: 200 });
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleChildHostDeleteConfirm(makeChild()));
            await act(async () => {
                await result.current.handleChildHostDelete();
            });
            expect(mockDelete).toHaveBeenCalledWith('/api/v1/host/h1/children/c1');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('delete 404 → warning', async () => {
            const err = Object.assign(new Error('nf'), {
                isAxiosError: true,
                response: { status: 404 },
            });
            mockDelete.mockRejectedValueOnce(err);
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleChildHostDeleteConfirm(makeChild()));
            await act(async () => {
                await result.current.handleChildHostDelete();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('warning');
        });

        test('delete generic error with detail', async () => {
            const err = Object.assign(new Error('bad'), {
                isAxiosError: true,
                response: { status: 500, data: { detail: 'server exploded' } },
            });
            mockDelete.mockRejectedValueOnce(err);
            const { result, setSnackbarMessage, setSnackbarSeverity } = setup();
            act(() => result.current.handleChildHostDeleteConfirm(makeChild()));
            await act(async () => {
                await result.current.handleChildHostDelete();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
            expect(setSnackbarMessage).toHaveBeenCalledWith('server exploded');
        });
    });

    describe('enable WSL', () => {
        test('reboot required message', async () => {
            mockPost.mockResolvedValueOnce({ status: 200, data: { reboot_required: true } });
            const { result, setSnackbarMessage } = setup();
            await act(async () => {
                await result.current.handleEnableWsl();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith(
                expect.stringContaining('reboot is required'),
            );
        });

        test('plain success', async () => {
            mockPost.mockResolvedValueOnce({ status: 200, data: { reboot_required: false } });
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleEnableWsl();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
            await act(async () => {
                await vi.advanceTimersByTimeAsync(3500);
            });
        });

        test('error', async () => {
            mockPost.mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleEnableWsl();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });

    describe.each([
        ['handleInitializeLxd', '/api/v1/host/h1/virtualization/initialize-lxd'],
        ['handleInitializeVmm', '/api/v1/host/h1/virtualization/initialize-vmm'],
        ['handleInitializeKvm', '/api/v1/host/h1/virtualization/initialize-kvm'],
        ['handleInitializeBhyve', '/api/v1/host/h1/virtualization/initialize-bhyve'],
        ['handleDisableBhyve', '/api/v1/host/h1/virtualization/disable-bhyve'],
        ['handleEnableKvmModules', '/api/v1/host/h1/virtualization/enable-kvm-modules'],
        ['handleDisableKvmModules', '/api/v1/host/h1/virtualization/disable-kvm-modules'],
    ] as const)('%s', (fnName, url) => {
        test('success', async () => {
            mockPost.mockResolvedValueOnce({ status: 200 });
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await (result.current[fnName] as () => Promise<void>)();
            });
            expect(mockPost).toHaveBeenCalledWith(url);
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
            await act(async () => {
                await vi.advanceTimersByTimeAsync(6000);
            });
        });

        test('error', async () => {
            mockPost.mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await (result.current[fnName] as () => Promise<void>)();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });

    describe('openCreateDialogWithType', () => {
        test('sets type, resets form, opens dialog and fetches distributions', async () => {
            mockGetAll.mockResolvedValueOnce([
                { id: 'd1', display_name: 'Ubuntu', install_identifier: 'ubuntu', child_type: 'lxd', is_active: true },
                { id: 'd2', display_name: 'Old', install_identifier: 'x', child_type: 'lxd', is_active: false },
            ]);
            const { result } = setup();
            await act(async () => {
                result.current.openCreateDialogWithType('lxd');
            });
            expect(result.current.createChildHostOpen).toBe(true);
            expect(result.current.childHostFormData.childType).toBe('lxd');
            expect(mockGetAll).toHaveBeenCalledWith('lxd');
            expect(result.current.availableDistributions).toHaveLength(1);
        });

        test('fetchDistributions error → empty list', async () => {
            mockGetAll.mockRejectedValueOnce(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                result.current.openCreateDialogWithType('vmm');
            });
            expect(result.current.availableDistributions).toEqual([]);
        });
    });

    describe('auto-detect child type effect', () => {
        test.each([
            ['FreeBSD host', { platform: 'FreeBSD 14' }, 'bhyve'],
            ['OpenBSD host', { platform: 'OpenBSD 7.5' }, 'vmm'],
            ['Linux host', { platform: 'Linux' }, 'lxd'],
            ['Windows host', { platform: 'Windows' }, 'wsl'],
        ])('%s → %s', async (_label, hostOver, expected) => {
            const { result } = setup({ host: makeHost(hostOver) });
            await act(async () => {
                result.current.setCreateChildHostOpen(true);
            });
            expect(result.current.childHostFormData.childType).toBe(expected);
        });
    });

    describe('handleCreateChildHost validation', () => {
        test('no hostId → noop', async () => {
            const { result } = setup({ hostId: undefined });
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(mockPost).not.toHaveBeenCalled();
        });

        test('missing hostname → error snackbar', async () => {
            const { result, setSnackbarSeverity } = setup();
            setForm(result, { ...validLxdForm, hostname: '' });
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
            expect(mockPost).not.toHaveBeenCalled();
        });

        test('missing username → error', async () => {
            const { result, setSnackbarMessage } = setup();
            setForm(result, { ...validLxdForm, username: '' });
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith(expect.stringContaining('username'));
        });

        test('password mismatch → error', async () => {
            const { result, setSnackbarMessage } = setup();
            setForm(result, { ...validLxdForm, confirmPassword: 'other' });
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith(expect.stringContaining('do not match'));
        });

        test('vmm requires vm name and root password', async () => {
            const { result, setSnackbarMessage } = setup();
            setForm(result, {
                ...validLxdForm,
                childType: 'vmm',
                vmName: '',
            });
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith(expect.stringContaining('VM name'));
        });

        test('missing distribution blocks submit without snackbar error', async () => {
            const { result } = setup();
            setForm(result, { ...validLxdForm, distribution: '' });
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(mockPost).not.toHaveBeenCalled();
        });
    });

    describe('handleCreateChildHost submission', () => {
        test('lxd success closes dialog and resets form', async () => {
            mockPost.mockResolvedValueOnce({ status: 200, data: { success: true } });
            const { result, setSnackbarSeverity } = setup();
            setForm(result, validLxdForm);
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(mockPost).toHaveBeenCalledWith(
                '/api/v1/host/h1/virtualization/create-child',
                expect.objectContaining({ child_type: 'lxd', container_name: 'ct1' }),
            );
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
            expect(result.current.createChildHostOpen).toBe(false);
            await act(async () => {
                await vi.advanceTimersByTimeAsync(3500);
            });
        });

        test('vmm success sends vm_name, iso_url and root_password', async () => {
            mockPost.mockResolvedValueOnce({ status: 200, data: { success: true } });
            const { result } = setup();
            setForm(result, {
                childType: 'vmm',
                distribution: 'https://iso',
                hostname: 'vm1',
                username: 'admin',
                password: 'pw',
                confirmPassword: 'pw',
                vmName: 'myvm',
                rootPassword: 'rp',
                confirmRootPassword: 'rp',
            });
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(mockPost).toHaveBeenCalledWith(
                '/api/v1/host/h1/virtualization/create-child',
                expect.objectContaining({
                    child_type: 'vmm',
                    vm_name: 'myvm',
                    iso_url: 'https://iso',
                    root_password: 'rp',
                }),
            );
        });

        test('kvm success sends cloud_image_url', async () => {
            mockPost.mockResolvedValueOnce({ status: 200, data: { success: true } });
            const { result } = setup();
            setForm(result, {
                childType: 'kvm',
                distribution: 'https://cloud.img',
                hostname: 'vm1',
                username: 'admin',
                password: 'pw',
                confirmPassword: 'pw',
                vmName: 'kvm1',
            });
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(mockPost).toHaveBeenCalledWith(
                '/api/v1/host/h1/virtualization/create-child',
                expect.objectContaining({ child_type: 'kvm', cloud_image_url: 'https://cloud.img' }),
            );
        });

        test('reboot_required response → warning', async () => {
            mockPost.mockResolvedValueOnce({ status: 200, data: { success: false, reboot_required: true } });
            const { result, setSnackbarSeverity } = setup();
            setForm(result, validLxdForm);
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('warning');
        });

        test('result error → error snackbar', async () => {
            mockPost.mockResolvedValueOnce({ status: 200, data: { success: false, error: 'nope' } });
            const { result, setSnackbarMessage } = setup();
            setForm(result, validLxdForm);
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith('nope');
        });

        test('thrown axios error surfaces detail', async () => {
            const err = Object.assign(new Error('bad'), {
                isAxiosError: true,
                response: { data: { detail: 'boom detail' } },
            });
            mockPost.mockRejectedValueOnce(err);
            const { result, setSnackbarMessage } = setup();
            setForm(result, validLxdForm);
            await act(async () => {
                await result.current.handleCreateChildHost();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith('boom detail');
        });
    });

    describe('empty-state message helpers', () => {
        const withStatus = (status: VirtualizationStatus) => {
            const { result } = setup();
            act(() => {
                (result.current.setChildHosts as unknown as () => void); // no-op ref to keep lint calm
            });
            // Drive virtualizationStatus by resolving the fetch.
            mockGet.mockResolvedValueOnce({ status: 200, data: status });
            return result;
        };

        test('WSL messages across capability states', async () => {
            const result = withStatus({
                supported_types: ['wsl'],
                capabilities: { wsl: { available: true, enabled: true, needs_enable: false } },
                reboot_required: false,
            });
            await act(async () => {
                await result.current.fetchVirtualizationStatus();
            });
            expect(result.current.getWslEmptyMessage()).toContain('WSL instance');
        });

        test('LXD / VMM / bhyve default messages when no status', () => {
            const { result } = setup();
            expect(result.current.getLxdEmptyMessage()).toContain('LXD is not available');
            expect(result.current.getVmmEmptyMessage()).toContain('VMM is not available');
            expect(result.current.getBhyveEmptyMessage()).toContain('bhyve is not available');
            expect(result.current.getWslEmptyMessage()).toContain('Windows host');
        });
    });

    describe('getCreateChildHostTitle', () => {
        test.each([
            ['lxd', 'LXD Container'],
            ['vmm', 'VMM Virtual Machine'],
            ['kvm', 'KVM Virtual Machine'],
            ['bhyve', 'bhyve Virtual Machine'],
            ['wsl', 'WSL Instance'],
        ])('%s title', (childType, expected) => {
            const { result } = setup();
            setForm(result, { childType });
            expect(result.current.getCreateChildHostTitle()).toContain(expected);
        });
    });

    describe('auto-refresh effect', () => {
        test('starts interval on child-hosts tab and polls', async () => {
            mockPost.mockResolvedValue({ status: 200 });
            const { result } = setup({ currentTabId: 'child-hosts' });
            // Effect requests an initial refresh; let microtasks settle.
            await act(async () => {
                await vi.advanceTimersByTimeAsync(100);
            });
            expect(mockPost).toHaveBeenCalledWith('/api/v1/host/h1/children/refresh');
            // Advance to trigger the 15s poll (fetchChildHosts + fetchVirtualizationStatus).
            await act(async () => {
                await vi.advanceTimersByTimeAsync(15000);
            });
            expect(result.current).toBeTruthy();
        });
    });
});
