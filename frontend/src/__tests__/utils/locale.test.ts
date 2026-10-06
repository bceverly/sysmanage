// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { describe, it, expect, afterEach } from 'vitest';
import i18n from '../../i18n/i18n';
import { appLocale } from '../../utils/locale';
import { formatUTCTimestamp } from '../../utils/dateUtils';

describe('appLocale', () => {
    const original = i18n.language;

    afterEach(async () => {
        await i18n.changeLanguage(original);
    });

    it('follows the language chosen in SysManage, not the browser', async () => {
        await i18n.changeLanguage('de');
        expect(appLocale()).toBe('de');
        // German grouping and date order, whatever the browser's language.
        expect((1234567).toLocaleString(appLocale())).toBe('1.234.567');
        expect(formatUTCTimestamp('2026-10-05T14:30:00')).toMatch(/^5\.10\.2026/);
    });

    it('turns the catalog code into an Intl locale tag', async () => {
        await i18n.changeLanguage('zh_CN');
        expect(appLocale()).toBe('zh-CN');
    });
});
