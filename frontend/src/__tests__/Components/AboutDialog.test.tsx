// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import AboutDialog, { shortVersion } from '../../Components/AboutDialog';
import UserProfileDropdown from '../../Components/UserProfileDropdown';
import { server } from '../../mocks/node';

vi.mock('../../Services/api', () => ({
    default: { get: vi.fn(() => Promise.resolve({ data: { has_profile_image: false } })) },
}));

const INFO = {
    version: '3.11.0.11+ppa1~resolute1',
    license_tier: 'enterprise',
    role: 'standard',
    federation_role: 'none',
};

describe('AboutDialog', () => {
    beforeEach(() => {
        localStorage.setItem('bearer_token', 'test-token');
        localStorage.setItem('userid', 'admin@example.invalid');
    });
    afterEach(() => {
        localStorage.clear();
    });

    it('shortens a packaged version to the release number', () => {
        expect(shortVersion('3.11.0.11+ppa1~resolute1')).toBe('3.11.0.11');
        expect(shortVersion('3.11.0.11-1')).toBe('3.11.0.11');
        expect(shortVersion('3.11.0.11')).toBe('3.11.0.11');
    });

    it('shows the server version, its build string and the edition', () => {
        render(<AboutDialog open onClose={() => {}} serverInfo={INFO} />);
        expect(screen.getByTestId('about-version').textContent).toBe('3.11.0.11');
        expect(screen.getByTestId('about-build').textContent).toBe('3.11.0.11+ppa1~resolute1');
        expect(screen.getByTestId('about-edition').textContent).toBe('Enterprise');
        expect(screen.getByText(/AGPL-3\.0/)).toBeTruthy();
        expect(screen.getByText('https://sysmanage.org')).toBeTruthy();
    });

    it('asks the server itself when the Navbar had no server-info', async () => {
        server.use(http.get('/api/v1/server-info', () => HttpResponse.json(INFO)));
        render(<AboutDialog open onClose={() => {}} serverInfo={null} />);
        expect((await screen.findByTestId('about-version')).textContent).not.toBe('');
        expect((await screen.findByText('3.11.0.11'))).toBeTruthy();
    });

    it('opens from the user menu', async () => {
        render(
            <BrowserRouter>
                <UserProfileDropdown serverInfo={INFO} />
            </BrowserRouter>,
        );
        fireEvent.click(screen.getByRole('button', { name: /user menu/i }));
        fireEvent.click(await screen.findByText('About'));
        expect((await screen.findByTestId('about-version')).textContent).toBe('3.11.0.11');
    });
});
