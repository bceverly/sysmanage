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
  });

export default i18n;