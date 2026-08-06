// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { vi, describe, test, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// i18next's t(key, defaultValue) — return the English default so assertions
// read as the user sees them rather than as key strings.
vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (_key: string, fallback?: string) => fallback ?? _key,
    }),
}));

import WindowsChildHostFields from '../WindowsChildHostFields';
import { isWindowsDistribution } from '../hostDetailHelpers';
import type { ChildHostFormData } from '../hostDetailTypes';

const baseForm = (overrides: Partial<ChildHostFormData> = {}): ChildHostFormData => ({
    childType: 'kvm',
    distribution: 'windows-server-2022',
    containerName: '',
    vmName: 'win01',
    hostname: 'win01',
    username: '',
    password: '',
    confirmPassword: '',
    rootPassword: '',
    confirmRootPassword: '',
    autoApprove: false,
    windowsEdition: 'standard-core',
    windowsProductKey: '',
    windowsIsoPath: '',
    windowsTimezone: 'UTC',
    windowsLocale: 'en-US',
    windowsJoinDomain: '',
    windowsDomainOu: '',
    windowsDomainUser: '',
    windowsDomainPassword: '',
    ...overrides,
});

const renderFields = (form: ChildHostFormData, setForm = vi.fn(), validated = false) => {
    render(
        <WindowsChildHostFields
            formData={form}
            setFormData={setForm}
            disabled={false}
            validated={validated}
        />,
    );
    return setForm;
};

describe('isWindowsDistribution', () => {
    test.each([
        ['windows-server-2022', true],
        ['windows-server-2025', true],
        ['Windows-Server-2022', true], // catalog casing must not matter
        ['  windows-server-2022  ', true],
        ['ubuntu:24.04', false],
        ['', false],
        [undefined, false],
    ])('%s -> %s', (identifier, expected) => {
        expect(isWindowsDistribution(identifier as string | undefined)).toBe(expected);
    });

    test('does not match on the display name', () => {
        // Display names are localized; matching them would break the dispatch
        // in every non-English UI.
        expect(isWindowsDistribution('Windows Server 2022 LTSC')).toBe(false);
    });
});

describe('WindowsChildHostFields', () => {
    test('the licence key field is secret-typed', () => {
        // ROADMAP requirement: the key must never be shoulder-readable.
        renderFields(baseForm());
        const key = screen.getByLabelText(/License key/i);
        expect(key).toHaveAttribute('type', 'password');
    });

    test('offers exactly the editions the engine can deploy', async () => {
        renderFields(baseForm());
        fireEvent.mouseDown(screen.getByLabelText(/Edition/i));
        const options = await screen.findAllByRole('option');
        expect(options.map((o) => o.textContent)).toEqual([
            'Standard (Core, no GUI)',
            'Standard (Desktop Experience)',
            'Datacenter (Core, no GUI)',
            'Datacenter (Desktop Experience)',
        ]);
    });

    test('domain fields stay hidden until the join toggle is on', () => {
        renderFields(baseForm());
        expect(screen.queryByLabelText(/Join account/i)).toBeNull();
    });

    test('domain fields appear once a domain is set', () => {
        renderFields(baseForm({ windowsJoinDomain: 'corp.example.com' }));
        // MUI appends " *" to a required label, so match by role instead:
        // the password field is type=password and therefore not a textbox,
        // which makes this uniquely the join-account username.
        expect(
            screen.getByRole('textbox', { name: /join account/i }),
        ).toBeInTheDocument();
        expect(screen.getByLabelText(/Join account password/i)).toHaveAttribute(
            'type',
            'password',
        );
    });

    test('turning the domain toggle off clears the credentials with it', () => {
        // Leaving an orphaned username/password behind would put credentials on
        // the config ISO for a join that is never attempted.
        const setForm = renderFields(
            baseForm({
                windowsJoinDomain: 'corp.example.com',
                windowsDomainOu: 'OU=Servers',
                windowsDomainUser: 'svc-join',
                windowsDomainPassword: 'secret',
            }),
        );
        // MUI's Switch does not expose a "checkbox" role; go via its label.
        fireEvent.click(screen.getByLabelText(/Join an Active Directory domain/i));
        expect(setForm).toHaveBeenCalledWith(
            expect.objectContaining({
                windowsJoinDomain: '',
                windowsDomainOu: '',
                windowsDomainUser: '',
                windowsDomainPassword: '',
            }),
        );
    });

    test('a missing ISO path is flagged only after validation runs', () => {
        renderFields(baseForm(), vi.fn(), false);
        expect(
            screen.queryByText(/Please enter the path to the Windows installation ISO/i),
        ).toBeNull();
    });

    test('a missing ISO path is flagged once validated', () => {
        renderFields(baseForm(), vi.fn(), true);
        expect(
            screen.getByText(/Please enter the path to the Windows installation ISO/i),
        ).toBeInTheDocument();
    });
});
