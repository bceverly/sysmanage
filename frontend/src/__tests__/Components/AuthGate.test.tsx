// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { vi } from 'vitest';
import AuthGate, { tokenExpired } from '../../Components/AuthGate';
import axiosInstance from '../../Services/api';

vi.mock('../../Services/api', () => ({ default: { post: vi.fn() } }));

const jwt = (exp: number) => `h.${globalThis.btoa(JSON.stringify({ exp }))}.s`;
const future = () => Math.floor(Date.now() / 1000) + 3600;
const past = () => Math.floor(Date.now() / 1000) - 60;

const renderAt = (path: string) =>
    render(
        <MemoryRouter initialEntries={[path]}>
            <AuthGate>
                <Routes>
                    <Route path="/" element={<div>dashboard</div>} />
                    <Route path="/login" element={<div>login form</div>} />
                </Routes>
            </AuthGate>
        </MemoryRouter>,
    );

describe('AuthGate', () => {
    beforeEach(() => {
        localStorage.clear();
        vi.clearAllMocks();
    });

    test('signed out: the dashboard never renders, not even for one frame', () => {
        renderAt('/');
        expect(screen.queryByText('dashboard')).not.toBeInTheDocument();
        expect(screen.getByText('login form')).toBeInTheDocument();
    });

    test('public pages render without a session', () => {
        renderAt('/login');
        expect(screen.getByText('login form')).toBeInTheDocument();
    });

    test('a live token renders the page', () => {
        localStorage.setItem('bearer_token', jwt(future()));
        renderAt('/');
        expect(screen.getByText('dashboard')).toBeInTheDocument();
    });

    test('an expired token shows nothing, refreshes, then renders', async () => {
        localStorage.setItem('bearer_token', jwt(past()));
        vi.mocked(axiosInstance.post).mockResolvedValue({ data: { Authorization: jwt(future()) } });
        renderAt('/');
        expect(screen.queryByText('dashboard')).not.toBeInTheDocument();
        expect(await screen.findByText('dashboard')).toBeInTheDocument();
    });

    test('an expired token whose refresh fails goes to the login page', async () => {
        localStorage.setItem('bearer_token', jwt(past()));
        vi.mocked(axiosInstance.post).mockRejectedValue(new Error('401'));
        renderAt('/');
        await waitFor(() => expect(screen.getByText('login form')).toBeInTheDocument());
        expect(localStorage.getItem('bearer_token')).toBeNull();
    });

    test('tokenExpired reads exp, and cannot-tell counts as not expired', () => {
        expect(tokenExpired(jwt(past()))).toBe(true);
        expect(tokenExpired(jwt(future()))).toBe(false);
        expect(tokenExpired('not-a-jwt')).toBe(false);
    });
});
