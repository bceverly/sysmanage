/**
 * useModuleLicensed — reactive Pro+ module-license gate.
 *
 * Returns ``true`` iff the cached license advertises ``moduleCode`` in its
 * ``modules`` list.  Backed by the license cache in ``Services/license`` and
 * subscribed via ``onLicenseChange``, so a component re-renders when the
 * license is (re)loaded — e.g. the Navbar's startup ``refreshLicenseCache``,
 * or after a license-key install.
 *
 * Use this to AVOID calling Pro+/Enterprise-gated endpoints (which return
 * HTTP 402) from open-source or wrong-tier deployments:
 *
 *   const mirrorsLicensed = useModuleLicensed('repository_mirroring_engine');
 *   useEffect(() => { if (mirrorsLicensed) load(); }, [mirrorsLicensed]);
 *   if (!mirrorsLicensed) return null;   // hide the panel entirely
 *
 * Not-loaded-yet reads as ``false`` (same semantics as ``isModuleLicensed``),
 * so a feature is treated as unavailable until the license proves otherwise —
 * the cache flips it on (and re-renders) once it loads.
 */
import { useSyncExternalStore } from 'react';

import { isModuleLicensed, onLicenseChange } from '../Services/license';

export const useModuleLicensed = (moduleCode: string): boolean =>
    useSyncExternalStore(
        onLicenseChange,
        () => isModuleLicensed(moduleCode),
    );

export default useModuleLicensed;
