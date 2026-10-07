// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import IdpMfaFields from '../../Components/IdpMfaFields';
import type { IdpProviderCreate } from '../../Services/externalIdp';

const draft = (over: Partial<IdpProviderCreate>): IdpProviderCreate => ({
    name: 'Entra', type: 'oidc', ...over,
});

describe('IdpMfaFields (Phase 22.8)', () => {
    test('LDAP providers get no MFA setting', () => {
        const { container } = render(<IdpMfaFields draft={draft({ type: 'ldap' })} setDraft={vi.fn()} />);
        expect(container).toBeEmptyDOMElement();
    });

    test('the switch turns require_mfa on', () => {
        const setDraft = vi.fn();
        render(<IdpMfaFields draft={draft({})} setDraft={setDraft} />);
        fireEvent.click(screen.getByRole('switch'));
        expect(setDraft).toHaveBeenCalledWith(expect.objectContaining({ require_mfa: true }));
    });

    test('OIDC with MFA on offers acr values, not SAML contexts', () => {
        render(<IdpMfaFields draft={draft({ require_mfa: true })} setDraft={vi.fn()} />);
        expect(screen.getByLabelText(/Accepted assurance levels/)).toBeInTheDocument();
        expect(screen.queryByLabelText(/authentication contexts/)).toBeNull();
    });

    test('SAML with MFA on offers the authentication contexts', () => {
        const setDraft = vi.fn();
        render(<IdpMfaFields draft={draft({ type: 'saml', require_mfa: true })} setDraft={setDraft} />);
        const field = screen.getByLabelText(/Multi-factor authentication contexts/);
        fireEvent.change(field, { target: { value: 'urn:example:mfa' } });
        expect(setDraft).toHaveBeenCalledWith(
            expect.objectContaining({ saml_mfa_authn_contexts: 'urn:example:mfa' }),
        );
    });

    test('with MFA off only the switch shows', () => {
        render(<IdpMfaFields draft={draft({ type: 'saml' })} setDraft={vi.fn()} />);
        expect(screen.queryByRole('textbox')).toBeNull();
    });
});
