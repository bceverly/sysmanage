// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { describe, expect, test, beforeEach } from 'vitest';
import { isBearerToken, storeBearerToken } from '../../Services/bearerToken';

describe('storeBearerToken', () => {
    beforeEach(() => localStorage.clear());

    test('a JWT-shaped token is stored', () => {
        storeBearerToken('eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl');
        expect(localStorage.getItem('bearer_token')).toBe('eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl');
    });

    test.each([undefined, null, 42, '', 'not-a-jwt', 'a.b', 'a.b.c<script>', 'a.b.c.d', 'x'.repeat(9000)])(
        'anything else is refused and nothing is stored (%s)',
        (value) => {
            expect(() => storeBearerToken(value)).toThrow('valid session token');
            expect(localStorage.getItem('bearer_token')).toBeNull();
        },
    );

    test('isBearerToken mirrors the rule', () => {
        expect(isBearerToken('a.b.c')).toBe(true);
        expect(isBearerToken('a.b')).toBe(false);
    });
});
