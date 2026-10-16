// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The "Administrator" switch: only an administrator can flip it, it sends
// is_admin for that user, and the server's refusal (the last active
// administrator) is shown rather than swallowed.

import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('react-i18next', () => ({
    useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));
vi.mock('../../../Services/users', () => ({ doSetUserAdmin: vi.fn() }));

import { doSetUserAdmin } from '../../../Services/users';
import UserAdminToggle from '../UserAdminToggle';

const setAdmin = vi.mocked(doSetUserAdmin);

describe('UserAdminToggle', () => {
    beforeEach(() => vi.clearAllMocks());

    test('is read-only for someone who is not an administrator', () => {
        render(<UserAdminToggle userId="u1" isAdmin={false} canManage={false} onChanged={vi.fn()} />);
        expect(screen.getByRole('checkbox', { name: 'Administrator' })).toBeDisabled();
        expect(screen.getByText('Only an administrator can change this.')).toBeInTheDocument();
    });

    test('an administrator grants it and the new value is reported back', async () => {
        setAdmin.mockResolvedValue({ id: 'u1', is_admin: true });
        const onChanged = vi.fn();
        render(<UserAdminToggle userId="u1" isAdmin={false} canManage onChanged={onChanged} />);
        const toggle = screen.getByRole('checkbox', { name: 'Administrator' });
        expect(toggle).toBeEnabled();
        await act(async () => { fireEvent.click(toggle); });
        expect(setAdmin).toHaveBeenCalledWith('u1', true);
        expect(onChanged).toHaveBeenCalledWith(true);
    });

    test("the server's refusal is shown and nothing changes", async () => {
        setAdmin.mockRejectedValue({
            response: { status: 409, data: { detail: 'This is the last active administrator.' } },
        });
        const onChanged = vi.fn();
        render(<UserAdminToggle userId="u1" isAdmin canManage onChanged={onChanged} />);
        await act(async () => { fireEvent.click(screen.getByRole('checkbox', { name: 'Administrator' })); });
        expect(setAdmin).toHaveBeenCalledWith('u1', false);
        expect(onChanged).not.toHaveBeenCalled();
        expect(screen.getByText('This is the last active administrator.')).toBeInTheDocument();
    });

    test('a failure without a reason gets a generic message', async () => {
        setAdmin.mockRejectedValue(new Error('network'));
        render(<UserAdminToggle userId="u1" isAdmin={false} canManage onChanged={vi.fn()} />);
        await act(async () => { fireEvent.click(screen.getByRole('checkbox', { name: 'Administrator' })); });
        expect(screen.getByText('Administrator rights could not be changed.')).toBeInTheDocument();
    });
});
