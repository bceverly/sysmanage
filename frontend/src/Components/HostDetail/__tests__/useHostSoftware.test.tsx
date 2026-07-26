// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, afterEach, test, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { TFunction } from 'i18next';

vi.mock('../../../Services/api', () => ({
    default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../Services/hosts', () => ({
    doGetHostSoftware: vi.fn(),
    doRequestPackages: vi.fn(),
}));

import axiosInstance from '../../../Services/api';
import * as hosts from '../../../Services/hosts';
import { useHostSoftware } from '../useHostSoftware';
import type { SysManageHost, SoftwarePackage } from '../../../Services/hosts';
import type { SysManageUser } from '../../../Services/users';

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;
const mockDelete = axiosInstance.delete as unknown as ReturnType<typeof vi.fn>;
const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

const makeHost = (over: Partial<SysManageHost> = {}): SysManageHost =>
    ({ id: 'h1', active: true, ...over } as unknown as SysManageHost);

const currentUser = { first_name: 'Ada', last_name: 'Lovelace', userid: 'ada' } as SysManageUser;
const pkg = (name: string) => ({ package_name: name } as SoftwarePackage);

interface SetupOpts {
    hostId?: string | undefined;
    host?: SysManageHost | null;
    currentTabId?: string;
    currentUser?: SysManageUser | null;
}

const setup = (opts: SetupOpts = {}) => {
    const setCurrentTab = vi.fn();
    const setSnackbarMessage = vi.fn();
    const setSnackbarSeverity = vi.fn();
    const setSnackbarOpen = vi.fn();
    const props = {
        hostId: 'hostId' in opts ? opts.hostId : 'h1',
        host: 'host' in opts ? (opts.host as SysManageHost | null) : makeHost(),
        currentTabId: opts.currentTabId ?? 'overview',
        currentUser: 'currentUser' in opts ? (opts.currentUser as SysManageUser | null) : currentUser,
        tabDefinitions: [{ id: 'info' }, { id: 'software-changes' }],
        setCurrentTab,
        t,
        setSnackbarMessage,
        setSnackbarSeverity,
        setSnackbarOpen,
    };
    const utils = renderHook((p: typeof props) => useHostSoftware(p), { initialProps: props });
    return { ...utils, setCurrentTab, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen };
};

describe('useHostSoftware', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.useFakeTimers();
        mockGet.mockResolvedValue({ data: { installations: [] } });
        mockPost.mockResolvedValue({ data: { success: true, message: 'ok' } });
        mockDelete.mockResolvedValue({ data: {} });
        m(hosts.doGetHostSoftware).mockResolvedValue({
            items: [],
            pagination: { page: 1, page_size: 100, total_items: 0, total_pages: 0, has_next: false, has_prev: false },
        });
        m(hosts.doRequestPackages).mockResolvedValue({});
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    describe('fetchInstallationHistory', () => {
        test('no hostId → noop', async () => {
            const { result } = setup({ hostId: undefined });
            await act(async () => {
                await result.current.fetchInstallationHistory();
            });
            expect(mockGet).not.toHaveBeenCalled();
        });

        test('success sets history', async () => {
            mockGet.mockResolvedValueOnce({ data: { installations: [{ request_id: 'r1' }] } });
            const { result } = setup();
            await act(async () => {
                await result.current.fetchInstallationHistory();
            });
            expect(result.current.installationHistory).toEqual([{ request_id: 'r1' }]);
        });

        test('error resets to empty', async () => {
            mockGet.mockRejectedValueOnce(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                await result.current.fetchInstallationHistory();
            });
            expect(result.current.installationHistory).toEqual([]);
        });
    });

    describe('performPackageSearch', () => {
        test('empty query → noop', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.performPackageSearch('   ');
            });
            expect(mockGet).not.toHaveBeenCalled();
        });

        test('filters out already-installed packages', async () => {
            mockGet.mockResolvedValueOnce({
                data: [
                    { name: 'installed-pkg', description: 'd', version: '1' },
                    { name: 'new-pkg', description: 'd', version: '2' },
                ],
            });
            const { result } = setup();
            act(() => result.current.setSoftwarePackages([pkg('installed-pkg')]));
            await act(async () => {
                await result.current.performPackageSearch('pkg');
            });
            expect(result.current.searchResults).toEqual([
                { name: 'new-pkg', description: 'd', version: '2' },
            ]);
        });

        test('non-array response → empty results', async () => {
            mockGet.mockResolvedValueOnce({ data: { nope: true } });
            const { result } = setup();
            await act(async () => {
                await result.current.performPackageSearch('x');
            });
            expect(result.current.searchResults).toEqual([]);
        });

        test('auth error handled', async () => {
            mockGet.mockRejectedValueOnce({ response: { status: 401 } });
            const { result } = setup();
            await act(async () => {
                await result.current.performPackageSearch('x');
            });
            expect(result.current.searchResults).toEqual([]);
        });
    });

    describe('request packages', () => {
        test('open confirm', () => {
            const { result } = setup();
            act(() => result.current.handleRequestPackages());
            expect(result.current.requestPackagesConfirmOpen).toBe(true);
        });

        test('confirm no host → noop', async () => {
            const { result } = setup({ host: null });
            await act(async () => {
                await result.current.handleRequestPackagesConfirm();
            });
            expect(hosts.doRequestPackages).not.toHaveBeenCalled();
        });

        test('confirm success', async () => {
            const { result, setSnackbarOpen } = setup();
            await act(async () => {
                await result.current.handleRequestPackagesConfirm();
            });
            expect(hosts.doRequestPackages).toHaveBeenCalledWith('h1');
            expect(setSnackbarOpen).toHaveBeenCalledWith(true);
        });

        test('confirm error', async () => {
            m(hosts.doRequestPackages).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarMessage } = setup();
            await act(async () => {
                await result.current.handleRequestPackagesConfirm();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith(expect.stringContaining('Failed'));
        });
    });

    describe('install packages', () => {
        test('toggle selection', () => {
            const { result } = setup();
            act(() => result.current.handlePackageSelect('a'));
            expect(result.current.selectedPackages.has('a')).toBe(true);
            act(() => result.current.handlePackageSelect('a'));
            expect(result.current.selectedPackages.has('a')).toBe(false);
        });

        test('no selection → noop', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleInstallPackages();
            });
            expect(mockPost).not.toHaveBeenCalled();
        });

        test('success navigates to software-changes tab', async () => {
            const { result, setCurrentTab, setSnackbarSeverity } = setup();
            act(() => result.current.handlePackageSelect('nginx'));
            await act(async () => {
                await result.current.handleInstallPackages();
            });
            expect(mockPost).toHaveBeenCalledWith(
                '/api/v1/packages/install/h1',
                expect.objectContaining({ package_names: ['nginx'], requested_by: 'Ada Lovelace' }),
            );
            expect(setCurrentTab).toHaveBeenCalledWith(1);
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
            expect(result.current.packageInstallDialogOpen).toBe(false);
        });

        test('backend failure → error snackbar', async () => {
            mockPost.mockResolvedValueOnce({ data: { success: false, message: 'nope' } });
            const { result, setSnackbarSeverity, setSnackbarMessage } = setup();
            act(() => result.current.handlePackageSelect('nginx'));
            await act(async () => {
                await result.current.handleInstallPackages();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
            expect(setSnackbarMessage).toHaveBeenCalledWith('nope');
        });

        test('http error with detail', async () => {
            mockPost.mockRejectedValueOnce({ response: { data: { detail: 'denied' } } });
            const { result, setSnackbarMessage } = setup();
            act(() => result.current.handlePackageSelect('nginx'));
            await act(async () => {
                await result.current.handleInstallPackages();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith('denied');
        });

        test('unknown-user fallback', async () => {
            const { result } = setup({ currentUser: null });
            act(() => result.current.handlePackageSelect('nginx'));
            await act(async () => {
                await result.current.handleInstallPackages();
            });
            expect(mockPost).toHaveBeenCalledWith(
                '/api/v1/packages/install/h1',
                expect.objectContaining({ requested_by: 'Unknown User' }),
            );
        });

        test('close dialog resets', () => {
            const { result } = setup();
            act(() => result.current.handlePackageSelect('nginx'));
            act(() => result.current.handleClosePackageDialog());
            expect(result.current.selectedPackages.size).toBe(0);
        });
    });

    describe('uninstall', () => {
        test('open + cancel', () => {
            const { result } = setup();
            act(() => result.current.handleUninstallPackage(pkg('nginx')));
            expect(result.current.uninstallConfirmOpen).toBe(true);
            act(() => result.current.handleUninstallCancel());
            expect(result.current.uninstallConfirmOpen).toBe(false);
        });

        test('confirm success', async () => {
            const { result, setCurrentTab, setSnackbarSeverity } = setup();
            act(() => result.current.handleUninstallPackage(pkg('nginx')));
            await act(async () => {
                await result.current.handleUninstallConfirm();
            });
            expect(mockPost).toHaveBeenCalledWith(
                '/api/v1/packages/uninstall/h1',
                expect.objectContaining({ package_names: ['nginx'] }),
            );
            expect(setCurrentTab).toHaveBeenCalledWith(1);
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('confirm backend failure', async () => {
            mockPost.mockResolvedValueOnce({ data: { success: false, message: 'busy' } });
            const { result, setSnackbarMessage } = setup();
            act(() => result.current.handleUninstallPackage(pkg('nginx')));
            await act(async () => {
                await result.current.handleUninstallConfirm();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith('busy');
        });

        test('confirm no package → noop', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleUninstallConfirm();
            });
            expect(mockPost).not.toHaveBeenCalled();
        });
    });

    describe('installation log + delete', () => {
        test('view + close log', () => {
            const item = { request_id: 'r1' } as never;
            const { result } = setup();
            act(() => result.current.handleViewInstallationLog(item));
            expect(result.current.installationLogDialogOpen).toBe(true);
            act(() => result.current.handleCloseInstallationLogDialog());
            expect(result.current.installationLogDialogOpen).toBe(false);
        });

        test('delete flow success refreshes', async () => {
            const item = { request_id: 'r1' } as never;
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleDeleteInstallation(item));
            expect(result.current.installationDeleteConfirmOpen).toBe(true);
            await act(async () => {
                await result.current.handleConfirmDeleteInstallation();
            });
            expect(mockDelete).toHaveBeenCalledWith('/api/v1/packages/installation-history/r1');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('delete no selection → noop', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleConfirmDeleteInstallation();
            });
            expect(mockDelete).not.toHaveBeenCalled();
        });

        test('delete error', async () => {
            mockDelete.mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleDeleteInstallation({ request_id: 'r1' } as never));
            await act(async () => {
                await result.current.handleConfirmDeleteInstallation();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });

        test('cancel delete', () => {
            const { result } = setup();
            act(() => result.current.handleDeleteInstallation({ request_id: 'r1' } as never));
            act(() => result.current.handleCancelDeleteInstallation());
            expect(result.current.installationDeleteConfirmOpen).toBe(false);
        });
    });

    describe('effects', () => {
        test('software tab loads packages', async () => {
            setup({ currentTabId: 'software' });
            await act(async () => {
                await vi.advanceTimersByTimeAsync(50);
            });
            expect(hosts.doGetHostSoftware).toHaveBeenCalled();
        });

        test('software-changes tab fetches + auto-refreshes history', async () => {
            setup({ currentTabId: 'software-changes' });
            await act(async () => {
                await vi.advanceTimersByTimeAsync(50);
            });
            expect(mockGet).toHaveBeenCalledWith('/api/v1/packages/installation-history/h1');
            mockGet.mockClear();
            await act(async () => {
                await vi.advanceTimersByTimeAsync(30000);
            });
            expect(mockGet).toHaveBeenCalled();
        });
    });
});
