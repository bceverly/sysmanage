// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi } from 'vitest';
import SsoCallback from '../../Pages/SsoCallback';
import { takeSsoSession } from '../../Services/sso';

vi.mock('../../Services/sso', () => ({ takeSsoSession: vi.fn() }));
vi.mock('../../Services/permissions', () => ({ clearPermissionsCache: vi.fn() }));

const at = (url: string) => render(
    <MemoryRouter initialEntries={[url]}><SsoCallback /></MemoryRouter>,
);

describe('SsoCallback', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        localStorage.clear();
    });
    afterEach(() => vi.unstubAllGlobals());

    test('takes the session once, stores it like a password login, enters the app', async () => {
        vi.mocked(takeSsoSession).mockResolvedValue({ Authorization: 'h.jwt.s', userid: 'user@acme.com' });
        const replace = vi.fn();
        vi.stubGlobal('location', { ...globalThis.location, replace });
        at('/login/sso');
        await waitFor(() => expect(replace).toHaveBeenCalledWith('/'));
        expect(takeSsoSession).toHaveBeenCalledTimes(1);
        expect(localStorage.getItem('bearer_token')).toBe('h.jwt.s');
        expect(localStorage.getItem('userid')).toBe('user@acme.com');
    });

    test('a sign-in without multi-factor proof says so (22.8)', async () => {
        at('/login/sso?error=mfa_required');
        expect(await screen.findByText(/did not confirm multi-factor sign-in/)).toBeInTheDocument();
        expect(takeSsoSession).not.toHaveBeenCalled();
    });

    test('an expired hand-off says so', async () => {
        vi.mocked(takeSsoSession).mockRejectedValue(new Error('401'));
        at('/login/sso');
        expect(await screen.findByText(/session has expired/)).toBeInTheDocument();
        expect(localStorage.getItem('bearer_token')).toBeNull();
    });

    test('a refusal the server sent is explained without asking for a session', () => {
        at('/login/sso?error=denied');
        expect(screen.getByText(/no active SysManage account/)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Back to sign in' })).toBeInTheDocument();
        expect(takeSsoSession).not.toHaveBeenCalled();
    });

    test('an unknown reason falls back to the generic message', () => {
        at('/login/sso?error=<script>');
        expect(screen.getByText(/did not complete/)).toBeInTheDocument();
    });
});
