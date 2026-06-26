import React, { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { refreshLicenseCache, isModuleLicensed } from '../Services/license';

/**
 * Route guard for Enterprise/Pro+ pages.
 *
 * Renders ``children`` only when the given license module is active; otherwise
 * redirects to the dashboard so the page is unreachable by direct URL on a
 * license that doesn't include it.  Defence-in-depth alongside the nav-level
 * gating and the API's own 402 responses — a Professional user who types
 * ``/airgap/repositories`` or ``/sites`` lands back on the dashboard rather
 * than on an Enterprise feature they aren't licensed for.
 */
const LicensedRoute: React.FC<{
  module: string;
  children: React.ReactElement;
}> = ({ module, children }) => {
  // 'checking' renders nothing so the guarded page never flashes before the
  // license cache resolves.
  const [state, setState] = useState<'checking' | 'allowed' | 'denied'>(
    'checking',
  );

  useEffect(() => {
    let cancelled = false;
    refreshLicenseCache()
      .then(() => {
        if (!cancelled) {
          setState(isModuleLicensed(module) ? 'allowed' : 'denied');
        }
      })
      .catch(() => {
        if (!cancelled) setState('denied');
      });
    return () => {
      cancelled = true;
    };
  }, [module]);

  if (state === 'checking') return null;
  if (state === 'denied') return <Navigate to="/" replace />;
  return children;
};

export default LicensedRoute;
