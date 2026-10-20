// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * License service for Pro+ license management.
 *
 * Core license types and functions only. Pro+ module-specific
 * types and API functions are provided by the Pro+ plugin bundle.
 */

import axiosInstance from './api';

export interface LicenseInfo {
    active: boolean;
    tier?: string;
    license_id?: string;
    features?: string[];
    modules?: string[];
    expires_at?: string;
    customer_name?: string;
    parent_hosts?: number;
    child_hosts?: number;
}

/**
 * Get current license information.
 */
export const getLicenseInfo = async (): Promise<LicenseInfo> => {
    const response = await axiosInstance.get('/api/v1/license');
    return response.data;
};

/**
 * Install a new license key.
 */
export const installLicense = async (licenseKey: string): Promise<{
    success: boolean;
    message: string;
    license_info?: LicenseInfo;
}> => {
    const response = await axiosInstance.post('/api/v1/license', {
        license_key: licenseKey
    });
    return response.data;
};

// -------------------------------------------------------------------
// Cached license + synchronous gating helpers
// -------------------------------------------------------------------
//
// Components throughout the app need to decide *during render* whether
// to surface a Pro+ feature.  The async ``getLicenseInfo`` round-trips
// the server every call, which is wrong for that use.  We cache the
// active license in module scope, refresh it via ``refreshLicenseCache``
// after login / license-key changes, and expose synchronous predicate
// helpers for components.
//
// The cache is refreshed after login / license-key changes, when the window
// regains focus, and -- after a FAILED fetch -- on a backoff until one
// succeeds.  A failure is never stored as "no license": during a server
// upgrade every request 502s or cannot connect, and storing that as an empty
// license left an open session showing the OSS menus (no Pro+ items) until
// the user logged out and back in (Bryan, 2026-10-19).  Only a real answer
// replaces the snapshot: a 2xx (an unlicensed server says ``active: false``)
// or a genuine 402.

let _cachedLicense: LicenseInfo | null = null;
const _subscribers = new Set<() => void>();

// Seconds between retries after a failed fetch; the last repeats forever.
export const LICENSE_RETRY_DELAYS_S = [2, 5, 10, 30];
let _retryTimer: ReturnType<typeof setTimeout> | null = null;
let _retryIndex = 0;
let _watching = false;

type FetchOutcome = { ok: true; license: LicenseInfo } | { ok: false };

/** A real answer (2xx, or 402 "no license") -- or a failure to retry. */
const fetchLicense = async (): Promise<FetchOutcome> => {
    try {
        return { ok: true, license: await getLicenseInfo() };
    } catch (error) {
        const status = (error as { response?: { status?: number } })?.response?.status;
        if (status === 402) return { ok: true, license: { active: false } };
        return { ok: false };
    }
};

const cancelRetry = () => {
    if (_retryTimer !== null) clearTimeout(_retryTimer);
    _retryTimer = null;
};

const scheduleRetry = () => {
    if (_retryTimer !== null) return;
    const delays = LICENSE_RETRY_DELAYS_S;
    const seconds = delays[Math.min(_retryIndex, delays.length - 1)];
    _retryIndex += 1;
    _retryTimer = setTimeout(() => {
        _retryTimer = null;
        void refreshLicenseCache();
    }, seconds * 1000);
};

/**
 * Refresh the cached license snapshot from the server.  Call after
 * login and after ``installLicense`` to invalidate stale state.  On a
 * failure the last known license stays and a retry is scheduled.
 */
export const refreshLicenseCache = async (): Promise<LicenseInfo | null> => {
    const outcome = await fetchLicense();
    if (!outcome.ok) {
        scheduleRetry();
        return _cachedLicense;
    }
    cancelRetry();
    _retryIndex = 0;
    _cachedLicense = outcome.license;
    _subscribers.forEach(fn => fn());
    return _cachedLicense;
};

const onFocusOrVisible = () => {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
    if (!localStorage.getItem('bearer_token')) return;
    void refreshLicenseCache();
};

/**
 * Refetch the license whenever the window regains focus or becomes visible
 * (cheap; catches a server upgrade under an open session).  Idempotent.
 */
export const watchLicense = (): void => {
    if (_watching || typeof globalThis.addEventListener !== 'function') return;
    _watching = true;
    globalThis.addEventListener('focus', onFocusOrVisible);
    if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', onFocusOrVisible);
    }
};

/** Read the cached license (or null if it hasn't been fetched yet). */
export const getCachedLicense = (): LicenseInfo | null => _cachedLicense;

/**
 * Subscribe to cache-refresh events so React components can re-render
 * when the license changes (e.g. on key install).  Returns an
 * unsubscribe function suitable for a ``useEffect`` cleanup.
 */
export const onLicenseChange = (fn: () => void): (() => void) => {
    _subscribers.add(fn);
    return () => _subscribers.delete(fn);
};

/**
 * True iff the cached license advertises ``featureCode`` in its
 * ``features`` array.  Returns false when the cache hasn't been
 * populated yet -- components should treat "no license loaded" as
 * "feature unavailable" rather than rendering and 402-ing.
 */
export const isFeatureLicensed = (featureCode: string): boolean =>
    !!_cachedLicense?.features?.includes(featureCode);

/**
 * True iff the cached license advertises ``moduleCode`` in its
 * ``modules`` array.  Same not-loaded-means-false semantics as
 * ``isFeatureLicensed``.
 */
export const isModuleLicensed = (moduleCode: string): boolean =>
    !!_cachedLicense?.modules?.includes(moduleCode);

/** Clear the cached license -- used by tests and on logout. */
export const clearLicenseCache = (): void => {
    cancelRetry();
    _retryIndex = 0;
    _cachedLicense = null;
    _subscribers.forEach(fn => fn());
};
