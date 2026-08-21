// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import Backend from 'i18next-http-backend';

// Injected by Vite at build time (see vite.config.ts ``define``).  Falls back
// to a constant so unit tests / non-Vite contexts don't break.
declare const __LOCALE_BUILD_ID__: string;
let localeBuildId: string;
try {
  // Vite's `define` replaces this identifier with a string literal; a non-Vite
  // context (e.g. a bare ts-node import) leaves it undeclared, which throws.
  localeBuildId = __LOCALE_BUILD_ID__;
} catch {
  localeBuildId = 'dev';
}

i18n
  .use(Backend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    // Catalogs are stored per BASE language (/locales/en/, /locales/fr/).  The
    // default `load: 'all'` also requests the region code a browser reports --
    // /locales/en-US/translation.json -- which serves index.html, fails to
    // parse, and logs an error on every single boot for no benefit.  Note the
    // zh_CN / zh_TW locales use an underscore, so they are untouched by this
    // (i18next splits region codes on '-').
    load: 'languageOnly',
    debug: false,
    showSupportNotice: false,
    
    interpolation: {
      escapeValue: false,
    },

    backend: {
      loadPath: '/locales/{{lng}}/{{ns}}.json',
      // Cache-bust so a redeploy after `make translate` re-fetches the current
      // catalog instead of the browser's stale copy.
      queryStringParams: { v: localeBuildId },
    },

    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage'],
    },

    react: {
      // Hardening, not a proven fix -- said plainly because the difference
      // matters.  Catalogs load over HTTP, and by default react-i18next
      // re-renders on 'languageChanged' but IGNORES store events, so any
      // bundle that arrives after that moment paints nothing.  In the
      // measured case changeLanguage() already awaits the load, so this
      // changes nothing today; it covers the namespace/bundle-arrives-later
      // path, which is the documented reason http-backend users set it.
      //
      // The bug actually behind "the UI stays English" was different: 44 keys
      // reached t() only through object literals (t(META[id].key, …)), were
      // therefore invisible to the extractor, existed in NO locale, and
      // rendered their English default in all 14 languages for ever.  See
      // KEY_PROP_REFERENCE in scripts/i18n_validate.py.
      bindI18nStore: 'added',
    },
  });

// A catalog that fails to fetch is otherwise SILENT: i18next falls back to
// English and reports nothing, so the UI looks like a translation bug ("the
// strings are English") when it is really a transport bug ("es/translation.json
// never arrived").  Diagnosing that cost six rounds of guesswork; it should
// cost one glance at the console.
i18n.on('failedLoading', (lng, ns, msg) => {
  // eslint-disable-next-line no-console
  console.error(
    `[i18n] FAILED to load ${lng}/${ns} from ` +
      `${(i18n.options.backend as { loadPath?: string } | undefined)?.loadPath} — ` +
      `every string in ${lng} will silently fall back to English. Cause: ${msg}`,
  );
});

// ---------------------------------------------------------------------------
// Plugin bundles vs. the real catalog.
//
// As each Pro+ plugin mounts (PluginContext) it calls addResourceBundle(lng,
// 'translation', ...) for EVERY language with its own handful of keys.  That
// plants a `<lng>|translation` bundle in the store, and i18next's queueLoad
// then treats the language as already loaded --
//     if (!options.reload && this.store.hasResourceBundle(lng, ns)) ...
// (i18next.js:1436) -- so the real /locales/<lng>/translation.json is NEVER
// fetched: no request, no error, and every app string falls back to English
// until a reload.  Booting in a language works only because i18next fetches
// its catalog before the plugins mount.
//
// Fix: remember which languages the BACKEND actually delivered, and for any
// language we switch to that isn't one of them, force a reload -- reloadResources
// passes options.reload, which is exactly the flag that bypasses the check
// above.  The fetched catalog merges over the plugin keys rather than
// replacing them, so plugin strings keep working.
export const installCatalogGuard = (instance: typeof i18n) => {
  const delivered = new Set<string>();
  instance.on('loaded', (loaded) => {
    Object.keys(loaded || {}).forEach((lng) => delivered.add(lng));
  });

  /** Fetch <lng>'s catalog if the backend never actually delivered it.
   *
   * Catalogs are stored per BASE language (/locales/en/…, /locales/fr/…), but
   * a browser reports a region code -- 'en-US'.  Asking for en-US fetches
   * index.html and fails to parse, which is a wasted request and a console
   * error on every boot, so resolve to the base and treat either form as
   * already delivered. */
  const ensureCatalogFor = async (full: string) => {
    if (!full) return;
    const lng = full.split('-')[0];
    if (delivered.has(full) || delivered.has(lng)) return;
    // Record first: reloadResources emits 'loaded' again, and without this a
    // concurrent call would fetch the same catalog twice.
    delivered.add(lng);
    try {
      await instance.reloadResources([lng], ['translation']);
    } catch {
      // Leave it to the failedLoading handler above to report; falling back to
      // English is the pre-existing behaviour, not a new failure.
      delivered.delete(lng);
    }
  };

  // Backstop for language changes that do NOT go through ensureCatalog --
  // the detector at boot, or any future caller of changeLanguage(). It repairs
  // the language one paint late (a brief English flash), which is why the
  // selector awaits ensureCatalog BEFORE flipping instead of relying on this.
  instance.on('languageChanged', (lng) => {
    void ensureCatalogFor(lng);
  });

  return ensureCatalogFor;
};

export const ensureCatalog = installCatalogGuard(i18n);

// Dev-only handle so a language bug can be interrogated from the console
// instead of guessed at:  i18n.language, i18n.hasResourceBundle('es',
// 'translation'), i18n.getResourceBundle('es','translation'), i18n.t(key).
// Stripped from production builds by the import.meta.env.DEV guard.
if (import.meta.env.DEV) {
  (globalThis as unknown as { i18n?: typeof i18n }).i18n = i18n;
}

export default i18n;