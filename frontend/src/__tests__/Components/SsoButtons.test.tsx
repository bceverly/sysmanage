// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import SsoButtons from '../../Components/Login/SsoButtons';
import type { SsoProvider } from '../../Services/sso';

const providers: SsoProvider[] = [
    { id: 'a', name: 'Okta', type: 'oidc', start_url: '/api/auth/oidc/a/start' },
    { id: 'b', name: 'Azure', type: 'saml', start_url: '/api/auth/saml/b/start' },
];

describe('SsoButtons', () => {
    test('one button per provider, which starts that provider\'s sign-in', () => {
        const assign = vi.fn();
        vi.stubGlobal('location', { ...globalThis.location, assign });
        render(<SsoButtons providers={providers} />);
        expect(screen.getByRole('button', { name: 'Sign in with Azure' })).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Sign in with Okta' }));
        expect(assign).toHaveBeenCalledWith('/api/auth/oidc/a/start');
        vi.unstubAllGlobals();
    });

    test('renders nothing when no provider is on offer', () => {
        const { container } = render(<SsoButtons providers={[]} />);
        expect(container).toBeEmptyDOMElement();
    });

    test('no "or" divider when there is no password form above', () => {
        render(<SsoButtons providers={providers} divider={false} />);
        expect(screen.queryByText('or')).not.toBeInTheDocument();
    });
});
