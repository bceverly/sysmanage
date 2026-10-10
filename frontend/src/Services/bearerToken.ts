// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The ONE place the session token is written to browser storage.  Every
// login, refresh and SSO path stored whatever the server's "Authorization"
// field held; a value that is not a JWT is now refused instead of stored
// (SonarCloud "browser storage poisoning", 2026-10-11).  A refusal throws,
// so each caller's existing failure path runs: sign-in fails, nothing kept.

/** A JWT: three base64url segments separated by dots. */
const JWT_SHAPE = /^[\w-]+\.[\w-]+\.[\w-]+$/;

export function isBearerToken(value: unknown): value is string {
    return typeof value === 'string' && value.length < 8192 && JWT_SHAPE.test(value);
}

export function storeBearerToken(value: unknown): void {
    if (!isBearerToken(value)) {
        throw new Error('The server did not return a valid session token.');
    }
    localStorage.setItem('bearer_token', value);
}
