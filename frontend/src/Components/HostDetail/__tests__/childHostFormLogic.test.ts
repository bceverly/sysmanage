// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { describe, test, expect } from 'vitest';
import type { TFunction } from 'i18next';

import { buildCreateChildRequest, validateChildHostForm } from '../childHostFormLogic';
import type { ChildHostFormData } from '../hostDetailTypes';

// Stand-in for i18next's t(key, fallback): return the English default.
const t = ((_key: string, fallback?: string) => fallback ?? _key) as unknown as TFunction;

const form = (overrides: Partial<ChildHostFormData> = {}): ChildHostFormData => ({
    childType: 'kvm',
    distribution: 'windows-server-2022',
    containerName: '',
    vmName: 'win01',
    hostname: 'win01',
    username: '',
    password: 'Pa55w0rd!',
    confirmPassword: 'Pa55w0rd!',
    rootPassword: '',
    confirmRootPassword: '',
    autoApprove: false,
    windowsEdition: 'standard-core',
    windowsProductKey: '',
    windowsIsoPath: '/var/lib/libvirt/images/iso/server2022.iso',
    windowsTimezone: 'UTC',
    windowsLocale: 'en-US',
    windowsJoinDomain: '',
    windowsDomainOu: '',
    windowsDomainUser: '',
    windowsDomainPassword: '',
    ...overrides,
});

describe('validateChildHostForm — Windows', () => {
    test('accepts a complete workgroup request', () => {
        expect(validateChildHostForm(t, form(), 'win01.example.com')).toBeNull();
    });

    test('requires the ISO path', () => {
        // There is no download URL for Server media, so without this the VM
        // boots to firmware and sits there.
        expect(validateChildHostForm(t, form({ windowsIsoPath: '' }), 'win01.example.com')).toMatch(
            /Windows installation ISO/i,
        );
    });

    test('rejects a domain with no join credentials', () => {
        // Half-configured join fails the specialize pass mid-install.
        const result = validateChildHostForm(
            t,
            form({ windowsJoinDomain: 'corp.example.com' }),
            'win01.example.com',
        );
        expect(result).toMatch(/domain join account/i);
    });

    test('accepts a fully configured domain join', () => {
        expect(
            validateChildHostForm(
                t,
                form({
                    windowsJoinDomain: 'corp.example.com',
                    windowsDomainUser: 'svc-join',
                    windowsDomainPassword: 'secret',
                }),
                'win01.example.com',
            ),
        ).toBeNull();
    });

    test('does not apply Windows rules to a Linux guest', () => {
        // A Linux KVM guest has no ISO path and must not be blocked by it.
        expect(
            validateChildHostForm(
                t,
                form({ distribution: 'ubuntu:24.04', username: 'bryan', windowsIsoPath: '' }),
                'box.example.com',
            ),
        ).toBeNull();
    });
});

describe('buildCreateChildRequest — Windows', () => {
    test('forwards the Windows fields', () => {
        const payload = buildCreateChildRequest(form({ windowsEdition: 'datacenter-core' }), 'win01.example.com');
        expect(payload).toMatchObject({
            distribution: 'windows-server-2022',
            windows_edition: 'datacenter-core',
            windows_iso_path: '/var/lib/libvirt/images/iso/server2022.iso',
            windows_timezone: 'UTC',
            windows_locale: 'en-US',
        });
    });

    test('uses the built-in Administrator and reuses the typed password', () => {
        const payload = buildCreateChildRequest(form(), 'win01.example.com');
        expect(payload.username).toBe('Administrator');
        expect(payload.windows_admin_password).toBe('Pa55w0rd!');
    });

    test('does not send a cloud image URL for Windows', () => {
        // The distribution is a dispatch token, not a URL — the KVM branch sets
        // cloud_image_url from it, and the Windows branch must undo that.
        const payload = buildCreateChildRequest(form(), 'win01.example.com');
        expect(payload).not.toHaveProperty('cloud_image_url');
    });

    test('omits the licence key entirely when blank', () => {
        // Evaluation media installs without one; an empty key must not be sent
        // (it would create an empty OpenBAO secret).
        const payload = buildCreateChildRequest(form(), 'win01.example.com');
        expect(payload).not.toHaveProperty('windows_product_key');
    });

    test('sends the licence key when given', () => {
        const payload = buildCreateChildRequest(
            form({ windowsProductKey: 'XXXXX-XXXXX-XXXXX-XXXXX-XXXXX' }),
            'win01.example.com',
        );
        expect(payload.windows_product_key).toBe('XXXXX-XXXXX-XXXXX-XXXXX-XXXXX');
    });

    test('omits domain credentials when no domain is set', () => {
        // Otherwise credentials ride along on the config ISO for a join that
        // never happens.
        const payload = buildCreateChildRequest(
            form({ windowsDomainUser: 'leftover', windowsDomainPassword: 'leftover' }),
            'win01.example.com',
        );
        expect(payload).not.toHaveProperty('windows_domain_user');
        expect(payload).not.toHaveProperty('windows_domain_password');
        expect(payload).not.toHaveProperty('windows_join_domain');
    });

    test('sends the domain group together, OU only when set', () => {
        const payload = buildCreateChildRequest(
            form({
                windowsJoinDomain: 'corp.example.com',
                windowsDomainUser: 'svc-join',
                windowsDomainPassword: 'secret',
            }),
            'win01.example.com',
        );
        expect(payload).toMatchObject({
            windows_join_domain: 'corp.example.com',
            windows_domain_user: 'svc-join',
            windows_domain_password: 'secret',
        });
        expect(payload).not.toHaveProperty('windows_domain_ou');
    });

    test('a Linux guest carries no Windows fields at all', () => {
        const payload = buildCreateChildRequest(
            form({ distribution: 'ubuntu:24.04', username: 'bryan' }),
            'box.example.com',
        );
        expect(Object.keys(payload).filter((k) => k.startsWith('windows_'))).toEqual([]);
        expect(payload.username).toBe('bryan');
        expect(payload.cloud_image_url).toBe('ubuntu:24.04');
    });
});
