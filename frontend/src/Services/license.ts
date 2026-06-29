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
// The cache is intentionally simple: no TTL, no auto-refresh.  It
// invalidates explicitly when the user installs a new license or signs
// in.  Components that need the freshest value can ``await
// refreshLicenseCache()`` first, but the typical render path reads the
// cached snapshot.

let _cachedLicense: LicenseInfo | null = null;
const _subscribers = new Set<() => void>();

/**
 * Refresh the cached license snapshot from the server.  Call after
 * login and after ``installLicense`` to invalidate stale state.
 */
export const refreshLicenseCache = async (): Promise<LicenseInfo | null> => {
    try {
        _cachedLicense = await getLicenseInfo();
    } catch {
        _cachedLicense = null;
    }
    _subscribers.forEach(fn => fn());
    return _cachedLicense;
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
 * populated yet — components should treat "no license loaded" as
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

/** Clear the cached license — used by tests and on logout. */
export const clearLicenseCache = (): void => {
    _cachedLicense = null;
    _subscribers.forEach(fn => fn());
};
