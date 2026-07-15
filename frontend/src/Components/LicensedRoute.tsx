import React, { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import {
  refreshLicenseCache,
  isModuleLicensed,
  isFeatureLicensed,
} from '../Services/license';

/**
 * Route guard for Enterprise/Pro+ pages.
 *
 * Renders ``children`` only when the license passes the given gate(s); otherwise
 * redirects to the dashboard so the page is unreachable by direct URL on a
 * license that doesn't include it.  Defence-in-depth alongside the nav-level
 * gating and the API's own 402 responses — a Professional user who types
 * ``/airgap/repositories``, ``/sites``, or ``/fips-compliance`` lands back on
 * the dashboard rather than on a feature they aren't licensed for.
 *
 * Pass ``module`` (a ModuleCode) and/or ``feature`` (a FeatureCode). When both
 * are given, BOTH must pass — this is what blocks reaching an Enterprise-feature
 * page whose engine module ships at a lower tier.
 */
const LicensedRoute: React.FC<{
  module?: string;
  feature?: string;
  children: React.ReactElement;
}> = ({ module, feature, children }) => {
  // 'checking' renders nothing so the guarded page never flashes before the
  // license cache resolves.
  const [state, setState] = useState<'checking' | 'allowed' | 'denied'>(
    'checking',
  );

  useEffect(() => {
    let cancelled = false;
    refreshLicenseCache()
      .then(() => {
        if (cancelled) return;
        const moduleOk = !module || isModuleLicensed(module);
        const featureOk = !feature || isFeatureLicensed(feature);
        setState(moduleOk && featureOk ? 'allowed' : 'denied');
      })
      .catch(() => {
        if (!cancelled) setState('denied');
      });
    return () => {
      cancelled = true;
    };
  }, [module, feature]);

  if (state === 'checking') return null;
  if (state === 'denied') return <Navigate to="/" replace />;
  return children;
};

export default LicensedRoute;
