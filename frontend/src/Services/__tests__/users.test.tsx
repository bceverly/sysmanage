// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for users API service
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import api from '../api';
import {
    doAddUser,
    doDeleteUser,
    doGetMe,
    doGetUserByID,
    doGetUserByUserid,
    doGetUsers,
    doUpdateUser,
    doUnlockUser,
    doLockUser,
    doUploadUserImage,
    doGetUserImage,
    doDeleteUserImage,
} from '../users';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

const resolve = (data: unknown) => ({
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {} as any,
});

const mockUser = {
    id: '1',
    active: true,
    userid: 'test@example.com',
    password: '',
    first_name: 'John',
    last_name: 'Doe',
    is_locked: false,
    failed_login_attempts: 0,
    locked_at: null,
};

describe('Users API Service', () => {
    let logSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
        vi.clearAllMocks();
        logSpy = vi.spyOn(window.console, 'log').mockImplementation(() => {});
    });

    afterEach(() => {
        logSpy.mockRestore();
    });

    describe('doAddUser', () => {
        it('posts a new user with password included', async () => {
            vi.mocked(api.post).mockResolvedValueOnce(resolve(mockUser));

            const result = await doAddUser(true, 'test@example.com', 'secret', 'John', 'Doe');

            expect(result).toEqual(mockUser);
            expect(api.post).toHaveBeenCalledWith('/api/v1/user', {
                active: true,
                userid: 'test@example.com',
                first_name: 'John',
                last_name: 'Doe',
                password: 'secret',
            });
        });

        it('omits password when blank and nulls missing names', async () => {
            vi.mocked(api.post).mockResolvedValueOnce(resolve(mockUser));

            await doAddUser(false, 'test@example.com', '   ');

            expect(api.post).toHaveBeenCalledWith('/api/v1/user', {
                active: false,
                userid: 'test@example.com',
                first_name: null,
                last_name: null,
            });
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('boom'));

            await expect(doAddUser(true, 'a@b.com', 'pw')).rejects.toThrow('boom');
        });
    });

    describe('doDeleteUser', () => {
        it('deletes a user by id', async () => {
            vi.mocked(api.delete).mockResolvedValueOnce(resolve({ result: true }));

            const result = await doDeleteUser('42');

            expect(result).toEqual({ result: true });
            expect(api.delete).toHaveBeenCalledWith('/api/v1/user/42');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.delete).mockRejectedValueOnce(new Error('del fail'));

            await expect(doDeleteUser('42')).rejects.toThrow('del fail');
        });
    });

    describe('doGetMe', () => {
        it('fetches the current user', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve(mockUser));

            const result = await doGetMe();

            expect(result).toEqual(mockUser);
            expect(api.get).toHaveBeenCalledWith('/api/v1/user/me');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('me fail'));

            await expect(doGetMe()).rejects.toThrow('me fail');
        });
    });

    describe('doGetUserByID', () => {
        it('fetches a user by id', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve(mockUser));

            const result = await doGetUserByID('7');

            expect(result).toEqual(mockUser);
            expect(api.get).toHaveBeenCalledWith('/api/v1/user/7');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('byid fail'));

            await expect(doGetUserByID('7')).rejects.toThrow('byid fail');
        });
    });

    describe('doGetUsers', () => {
        it('fetches all users', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve([mockUser]));

            const result = await doGetUsers();

            expect(result).toEqual([mockUser]);
            expect(api.get).toHaveBeenCalledWith('/api/v1/users');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('users fail'));

            await expect(doGetUsers()).rejects.toThrow('users fail');
        });
    });

    describe('doGetUserByUserid', () => {
        it('fetches a user by userid', async () => {
            vi.mocked(api.get).mockResolvedValueOnce(resolve(mockUser));

            const result = await doGetUserByUserid('test@example.com');

            expect(result).toEqual(mockUser);
            expect(api.get).toHaveBeenCalledWith('/api/v1/host/by_userid/test@example.com');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('byuserid fail'));

            await expect(doGetUserByUserid('x')).rejects.toThrow('byuserid fail');
        });
    });

    describe('doUpdateUser', () => {
        it('updates a user', async () => {
            vi.mocked(api.put).mockResolvedValueOnce(resolve({ result: true }));

            const result = await doUpdateUser('5', true, 'test@example.com', 'pw', 'John', 'Doe');

            expect(result).toEqual({ result: true });
            expect(api.put).toHaveBeenCalledWith('/api/v1/user/5', {
                active: true,
                userid: 'test@example.com',
                password: 'pw',
                first_name: 'John',
                last_name: 'Doe',
            });
        });

        it('nulls missing names', async () => {
            vi.mocked(api.put).mockResolvedValueOnce(resolve({ result: true }));

            await doUpdateUser('5', false, 'test@example.com', 'pw');

            expect(api.put).toHaveBeenCalledWith('/api/v1/user/5', {
                active: false,
                userid: 'test@example.com',
                password: 'pw',
                first_name: null,
                last_name: null,
            });
        });

        it('rethrows on error', async () => {
            vi.mocked(api.put).mockRejectedValueOnce(new Error('update fail'));

            await expect(doUpdateUser('5', true, 'x', 'pw')).rejects.toThrow('update fail');
        });
    });

    describe('doUnlockUser', () => {
        it('unlocks a user', async () => {
            vi.mocked(api.post).mockResolvedValueOnce(resolve(mockUser));

            const result = await doUnlockUser('9');

            expect(result).toEqual(mockUser);
            expect(api.post).toHaveBeenCalledWith('/api/v1/user/9/unlock');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('unlock fail'));

            await expect(doUnlockUser('9')).rejects.toThrow('unlock fail');
        });
    });

    describe('doLockUser', () => {
        it('locks a user', async () => {
            vi.mocked(api.post).mockResolvedValueOnce(resolve(mockUser));

            const result = await doLockUser('9');

            expect(result).toEqual(mockUser);
            expect(api.post).toHaveBeenCalledWith('/api/v1/user/9/lock');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('lock fail'));

            await expect(doLockUser('9')).rejects.toThrow('lock fail');
        });
    });

    describe('doUploadUserImage', () => {
        it('uploads an image as multipart form data', async () => {
            vi.mocked(api.post).mockResolvedValueOnce(resolve({ ok: true }));
            const file = new window.File(['abc'], 'avatar.png', { type: 'image/png' });

            const result = await doUploadUserImage('3', file);

            expect(result).toEqual({ ok: true });
            expect(api.post).toHaveBeenCalledWith(
                '/api/v1/user/3/image',
                expect.any(window.FormData),
                { headers: { 'Content-Type': 'multipart/form-data' } }
            );
            const formData = vi.mocked(api.post).mock.calls[0][1] as { get: CallableFunction };
            expect(formData.get('file')).toBe(file);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(new Error('upload fail'));
            const file = new window.File(['abc'], 'avatar.png', { type: 'image/png' });

            await expect(doUploadUserImage('3', file)).rejects.toThrow('upload fail');
        });
    });

    describe('doGetUserImage', () => {
        it('fetches an image as a blob', async () => {
            const blob = new window.Blob(['img']);
            vi.mocked(api.get).mockResolvedValueOnce(resolve(blob));

            const result = await doGetUserImage('3');

            expect(result).toBe(blob);
            expect(api.get).toHaveBeenCalledWith('/api/v1/user/3/image', {
                responseType: 'blob',
            });
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('image fail'));

            await expect(doGetUserImage('3')).rejects.toThrow('image fail');
        });
    });

    describe('doDeleteUserImage', () => {
        it('deletes an image', async () => {
            vi.mocked(api.delete).mockResolvedValueOnce(resolve({ ok: true }));

            const result = await doDeleteUserImage('3');

            expect(result).toEqual({ ok: true });
            expect(api.delete).toHaveBeenCalledWith('/api/v1/user/3/image');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.delete).mockRejectedValueOnce(new Error('delimg fail'));

            await expect(doDeleteUserImage('3')).rejects.toThrow('delimg fail');
        });
    });
});
