// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import SsoButtons from '../../Components/Login/SsoButtons';
import { getSsoProviders } from '../../Services/sso';

vi.mock('../../Services/sso', () => ({ getSsoProviders: vi.fn() }));

describe('SsoButtons', () => {
    beforeEach(() => vi.clearAllMocks());

    test('one button per provider, which starts that provider\'s sign-in', async () => {
        vi.mocked(getSsoProviders).mockResolvedValue([
            { id: 'a', name: 'Okta', type: 'oidc', start_url: '/api/auth/oidc/a/start' },
            { id: 'b', name: 'Azure', type: 'saml', start_url: '/api/auth/saml/b/start' },
        ]);
        const assign = vi.fn();
        vi.stubGlobal('location', { ...globalThis.location, assign });
        render(<SsoButtons />);
        const okta = await screen.findByRole('button', { name: 'Sign in with Okta' });
        expect(screen.getByRole('button', { name: 'Sign in with Azure' })).toBeInTheDocument();
        fireEvent.click(okta);
        expect(assign).toHaveBeenCalledWith('/api/auth/oidc/a/start');
        vi.unstubAllGlobals();
    });

    test('renders nothing when no provider is on offer or the call fails', async () => {
        vi.mocked(getSsoProviders).mockRejectedValue(new Error('402'));
        const { container } = render(<SsoButtons />);
        await waitFor(() => expect(getSsoProviders).toHaveBeenCalled());
        expect(container).toBeEmptyDOMElement();
    });
});
