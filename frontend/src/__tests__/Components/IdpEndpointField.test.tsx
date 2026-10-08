// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, act } from '@testing-library/react';
import { vi } from 'vitest';
import IdpEndpointField from '../../Components/IdpEndpointField';

describe('IdpEndpointField', () => {
    test('copies the exact address to register with the identity provider', async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        vi.stubGlobal('navigator', { ...globalThis.navigator, clipboard: { writeText } });
        const url = 'http://localhost:3000/api/auth/oidc/p1/callback';
        render(<IdpEndpointField label="Redirect URI" helperText="help" value={url} onChange={vi.fn()} />);
        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
        });
        expect(writeText).toHaveBeenCalledWith(url);
        vi.unstubAllGlobals();
    });

    test('no copy button while the field is blank (filled in on save)', () => {
        render(<IdpEndpointField label="Redirect URI" helperText="help" value="" onChange={vi.fn()} />);
        expect(screen.queryByRole('button', { name: 'Copy' })).not.toBeInTheDocument();
        expect(screen.getByLabelText('Redirect URI')).not.toBeRequired();
    });

    test('read-only without an onChange', () => {
        render(<IdpEndpointField label="SP metadata URL" helperText="help" value="https://x/metadata" />);
        expect(screen.getByLabelText('SP metadata URL')).toHaveAttribute('readonly');
    });
});
