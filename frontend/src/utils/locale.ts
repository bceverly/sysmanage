// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The default i18next instance (the one src/i18n/i18n.ts initializes), not
// that module itself: importing it would pull initReactI18next into every
// test that mocks react-i18next.
import i18n from 'i18next';

/**
 * The locale to format dates and numbers in: the language the user chose in
 * SysManage, not the browser's.  ``toLocaleString()`` with no argument used
 * the browser's language, so a user who picked German on an English browser
 * saw English dates and "1,234" counts.  i18n codes are "zh_CN"; Intl wants
 * "zh-CN".  ``undefined`` (the browser default) before i18n has a language.
 */
export const appLocale = (): string | undefined => {
    const language = i18n.language || i18n.resolvedLanguage;
    if (!language || language === 'cimode') return undefined;
    return language.replace('_', '-');
};
