// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * What to tell someone whose login failed.
 *
 * The password form used to clear its spinner and say nothing at all -- so a
 * server down for an upgrade (nginx answering 502) looked exactly like a
 * wrong password (production, 2026-10-16).  The cause decides the message:
 * the server unreachable, the server failing, bad credentials, or the
 * server's own reason for a lockout / rate limit / disabled account.
 */

type Translate = (key: string, fallback: string) => string;

interface LoginFailure {
    response?: { status?: number; data?: { detail?: unknown } };
}

// nginx answers these while the app behind it is stopped or restarting.
const UNREACHABLE = new Set([502, 503, 504]);
// The server explains these itself (already in the user's language).
const SERVER_EXPLAINS = new Set([403, 423, 429]);

export const isServerUnreachable = (err: unknown): boolean => {
    const status = (err as LoginFailure | undefined)?.response?.status;
    return status === undefined || UNREACHABLE.has(status);
};

export const loginErrorMessage = (err: unknown, t: Translate): string => {
    if (isServerUnreachable(err)) {
        return t(
            'login.serverUnreachable',
            'Cannot reach the SysManage server. It may be down or restarting -- try again in a minute.',
        );
    }
    const response = (err as LoginFailure).response;
    const status = response?.status ?? 0;
    const detail = response?.data?.detail;
    if (status === 401) {
        return t('login.invalidCredentials', 'Incorrect email or password.');
    }
    if (SERVER_EXPLAINS.has(status) && typeof detail === 'string' && detail) {
        return detail;
    }
    if (status >= 500) {
        return t(
            'login.serverError',
            'The server failed while signing you in. Try again; if it keeps happening, check the server log.',
        );
    }
    return t('login.failed', 'Login failed. Please try again.');
};
