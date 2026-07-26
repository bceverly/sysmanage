// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, test, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { TFunction } from 'i18next';

vi.mock('../../../Services/api', () => ({
    default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import axiosInstance from '../../../Services/api';
import { useHostAccessManagement } from '../useHostAccessManagement';
import type { SysManageHost, UserAccount, UserGroup } from '../../../Services/hosts';

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;
const mockDelete = axiosInstance.delete as unknown as ReturnType<typeof vi.fn>;
const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

const makeHost = (over: Partial<SysManageHost> = {}): SysManageHost =>
    ({ id: 'h1', active: true, ...over } as unknown as SysManageHost);

const user = { username: 'alice' } as UserAccount;
const group = { group_name: 'devs' } as UserGroup;

const sshKeySecret = { id: 's1', name: 'key1', filename: 'id_rsa', secret_type: 'ssh_key' };
const certSecret = { id: 'c1', name: 'cert1', filename: 'srv.pem', secret_type: 'ssl_certificate' };

const axiosErr = (detail: string) =>
    Object.assign(new Error('bad'), { isAxiosError: true, response: { data: { detail } } });

const setup = (opts: { hostId?: string | undefined; host?: SysManageHost | null } = {}) => {
    const setSnackbarMessage = vi.fn();
    const setSnackbarSeverity = vi.fn();
    const setSnackbarOpen = vi.fn();
    const props = {
        hostId: 'hostId' in opts ? opts.hostId : 'h1',
        host: 'host' in opts ? (opts.host as SysManageHost | null) : makeHost(),
        t,
        setSnackbarMessage,
        setSnackbarSeverity,
        setSnackbarOpen,
    };
    const utils = renderHook((p: typeof props) => useHostAccessManagement(p), { initialProps: props });
    return { ...utils, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen };
};

describe('useHostAccessManagement', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockGet.mockResolvedValue({ data: [sshKeySecret, certSecret] });
        mockPost.mockResolvedValue({ data: { ok: true } });
        mockDelete.mockResolvedValue({ data: {} });
    });

    test('show/close generic dialog', () => {
        const { result } = setup();
        act(() => result.current.handleShowDialog('Title', 'Content'));
        expect(result.current.dialogOpen).toBe(true);
        expect(result.current.dialogTitle).toBe('Title');
        act(() => result.current.handleCloseDialog());
        expect(result.current.dialogOpen).toBe(false);
        expect(result.current.dialogContent).toBe('');
    });

    describe('SSH key dialog', () => {
        test('handleAddSSHKey loads and filters ssh keys', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleAddSSHKey(user);
            });
            expect(mockGet).toHaveBeenCalledWith('/api/v1/stored-secrets?type=ssh_key');
            expect(result.current.availableSSHKeys).toEqual([sshKeySecret]);
            expect(result.current.sshKeyDialogOpen).toBe(true);
            expect(result.current.selectedUser).toEqual(user);
        });

        test('handleAddSSHKey error', async () => {
            mockGet.mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleAddSSHKey(user);
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });

        test('handleSSHKeyDialogClose resets', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleAddSSHKey(user);
            });
            act(() => result.current.handleSSHKeyDialogClose());
            expect(result.current.sshKeyDialogOpen).toBe(false);
            expect(result.current.selectedUser).toBeNull();
        });

        test('handleSSHKeySearch empty + matching term', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleAddSSHKey(user);
            });
            act(() => result.current.handleSSHKeySearch());
            expect(result.current.filteredSSHKeys).toEqual([sshKeySecret]);
            act(() => result.current.setSshKeySearchTerm('id_rsa'));
            act(() => result.current.handleSSHKeySearch());
            expect(result.current.filteredSSHKeys).toEqual([sshKeySecret]);
            act(() => result.current.setSshKeySearchTerm('nomatch'));
            act(() => result.current.handleSSHKeySearch());
            expect(result.current.filteredSSHKeys).toEqual([]);
        });

        test('handleDeploySSHKeys guard when nothing selected', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleDeploySSHKeys();
            });
            expect(mockPost).not.toHaveBeenCalled();
        });

        test('handleDeploySSHKeys success', async () => {
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleAddSSHKey(user);
            });
            act(() => result.current.setSelectedSSHKeys(['s1']));
            await act(async () => {
                await result.current.handleDeploySSHKeys();
            });
            expect(mockPost).toHaveBeenCalledWith(
                '/api/v1/stored-secrets/deploy-ssh-keys',
                expect.objectContaining({ host_id: 'h1', username: 'alice', secret_ids: ['s1'] }),
            );
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('handleDeploySSHKeys error with detail', async () => {
            mockPost.mockRejectedValueOnce(axiosErr('ssh boom'));
            const { result, setSnackbarMessage } = setup();
            await act(async () => {
                await result.current.handleAddSSHKey(user);
            });
            act(() => result.current.setSelectedSSHKeys(['s1']));
            await act(async () => {
                await result.current.handleDeploySSHKeys();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith('ssh boom');
        });
    });

    describe('delete user', () => {
        test('click opens confirm, cancel closes', () => {
            const { result } = setup();
            act(() => result.current.handleDeleteUserClick(user));
            expect(result.current.deleteUserConfirmOpen).toBe(true);
            expect(result.current.userToDelete).toEqual(user);
            act(() => result.current.handleDeleteUserCancel());
            expect(result.current.deleteUserConfirmOpen).toBe(false);
        });

        test('confirm no selection → noop', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleDeleteUserConfirm();
            });
            expect(mockDelete).not.toHaveBeenCalled();
        });

        test('confirm success', async () => {
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleDeleteUserClick(user));
            await act(async () => {
                await result.current.handleDeleteUserConfirm();
            });
            expect(mockDelete).toHaveBeenCalledWith(
                '/api/v1/host/h1/accounts/alice?delete_default_group=true',
            );
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('confirm error with detail', async () => {
            mockDelete.mockRejectedValueOnce(axiosErr('cannot delete'));
            const { result, setSnackbarMessage } = setup();
            act(() => result.current.handleDeleteUserClick(user));
            await act(async () => {
                await result.current.handleDeleteUserConfirm();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith('cannot delete');
        });
    });

    describe('delete group', () => {
        test('click + cancel', () => {
            const { result } = setup();
            act(() => result.current.handleDeleteGroupClick(group));
            expect(result.current.deleteGroupConfirmOpen).toBe(true);
            act(() => result.current.handleDeleteGroupCancel());
            expect(result.current.deleteGroupConfirmOpen).toBe(false);
        });

        test('confirm success', async () => {
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleDeleteGroupClick(group));
            await act(async () => {
                await result.current.handleDeleteGroupConfirm();
            });
            expect(mockDelete).toHaveBeenCalledWith('/api/v1/host/h1/groups/devs');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('confirm error with detail', async () => {
            mockDelete.mockRejectedValueOnce(axiosErr('group busy'));
            const { result, setSnackbarMessage } = setup();
            act(() => result.current.handleDeleteGroupClick(group));
            await act(async () => {
                await result.current.handleDeleteGroupConfirm();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith('group busy');
        });
    });

    describe('certificates', () => {
        test('loadAvailableCertificates success + close', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.loadAvailableCertificates();
            });
            expect(mockGet).toHaveBeenCalledWith('/api/v1/stored-secrets?type=ssl_certificate');
            expect(result.current.availableCertificates).toEqual([certSecret]);
            act(() => result.current.handleCertificateDialogClose());
            expect(result.current.availableCertificates).toEqual([]);
        });

        test('loadAvailableCertificates error', async () => {
            mockGet.mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.loadAvailableCertificates();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });

        test('handleCertificateSearch empty + term', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.loadAvailableCertificates();
            });
            act(() => result.current.handleCertificateSearch());
            expect(result.current.filteredCertificates).toEqual([certSecret]);
            act(() => result.current.setCertificateDialogSearchTerm('srv'));
            act(() => result.current.handleCertificateSearch());
            expect(result.current.filteredCertificates).toEqual([certSecret]);
            act(() => result.current.setCertificateDialogSearchTerm('none'));
            act(() => result.current.handleCertificateSearch());
            expect(result.current.filteredCertificates).toEqual([]);
        });

        test('handleDeployCertificates guard', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleDeployCertificates();
            });
            expect(mockPost).not.toHaveBeenCalled();
        });

        test('handleDeployCertificates success', async () => {
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.setSelectedCertificates(['c1']));
            await act(async () => {
                await result.current.handleDeployCertificates();
            });
            expect(mockPost).toHaveBeenCalledWith(
                '/api/v1/stored-secrets/deploy-certificates',
                expect.objectContaining({ host_id: 'h1', secret_ids: ['c1'] }),
            );
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('handleDeployCertificates error with detail', async () => {
            mockPost.mockRejectedValueOnce(axiosErr('cert boom'));
            const { result, setSnackbarMessage } = setup();
            act(() => result.current.setSelectedCertificates(['c1']));
            await act(async () => {
                await result.current.handleDeployCertificates();
            });
            expect(setSnackbarMessage).toHaveBeenCalledWith('cert boom');
        });
    });
});
