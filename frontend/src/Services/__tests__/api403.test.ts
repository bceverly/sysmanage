// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A 403 logs the user out ONLY when the credentials themselves are unusable.
// It used to log out on any 403 whose detail lacked the English words
// "Permission denied", so "Only an administrator can change the threat model"
// threw an administrator-less user to /login mid-questionnaire (2026-10-16).

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { handle403 } from '../api';

describe('handle403', () => {
    const original = globalThis.location;

    beforeEach(() => {
        Object.defineProperty(globalThis, 'location', {
            configurable: true,
            value: { pathname: '/advisor', href: '/advisor' },
        });
    });

    afterEach(() => {
        Object.defineProperty(globalThis, 'location', { configurable: true, value: original });
    });

    it('stays put on an administrator check', () => {
        handle403({ data: { detail: 'Only an administrator can change the threat model' }, headers: {} });
        expect(globalThis.location.href).toBe('/advisor');
    });

    it('stays put on a translated permission denial', () => {
        handle403({ data: { detail: 'Zugriff verweigert' }, headers: {} });
        expect(globalThis.location.href).toBe('/advisor');
    });

    it('stays put on a Pro+ license gate', () => {
        handle403({ data: { detail: { error: 'pro_plus_required' } }, headers: {} });
        expect(globalThis.location.href).toBe('/advisor');
    });

    it('goes to login when the server challenges the credentials', () => {
        handle403({ data: { detail: 'Ungültiger Autorisierungscode.' }, headers: { 'www-authenticate': 'Bearer' } });
        expect(globalThis.location.href).toBe('/login');
    });

    it("goes to login on FastAPI's missing-credentials 403", () => {
        handle403({ data: { detail: 'Not authenticated' }, headers: {} });
        expect(globalThis.location.href).toBe('/login');
    });
});
