// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Regression test: a plugin must not be able to suppress the real catalog.
 *
 * Pro+ plugins call addResourceBundle(lng, 'translation', ...) for EVERY
 * language as they mount.  That plants a `<lng>|translation` bundle, and
 * i18next's queueLoad then skips the fetch entirely --
 *     if (!options.reload && this.store.hasResourceBundle(lng, ns)) ...
 * (i18next.js:1436) -- so switching to that language showed English with no
 * request and no error, until a full page reload.
 *
 * Reproduced literally: plant the plugin bundle first, then switch.
 */

import { describe, expect, it } from 'vitest';
import { createInstance } from 'i18next';
import { installCatalogGuard } from '../i18n';

const CATALOGS: Record<string, Record<string, unknown>> = {
    en: { hosts: { approveSelected: 'Approve Selected' } },
    fr: { hosts: { approveSelected: 'Approuver la sélection' } },
};

const backend = {
    type: 'backend' as const,
    init: () => undefined,
    // eslint-disable-next-line no-unused-vars
    read(lng: string, _ns: string, cb: (e: unknown, d?: unknown) => void) {
        setTimeout(() => cb(null, CATALOGS[lng] ?? {}), 10);
    },
};

const makeInstance = async () => {
    const instance = createInstance();
    await instance.use(backend).init({
        lng: 'en',
        fallbackLng: 'en',
        interpolation: { escapeValue: false },
    });
    return instance;
};

describe('a plugin bundle must not shadow the real catalog', () => {
    it('still fetches the catalog for a language a plugin already touched', async () => {
        const i18n = await makeInstance();
        installCatalogGuard(i18n as unknown as Parameters<typeof installCatalogGuard>[0]);

        // What every plugin does on mount, for all 14 languages.
        i18n.addResourceBundle('fr', 'translation', { pluginOnlyKey: 'x' });
        expect(i18n.hasResourceBundle('fr', 'translation')).toBe(true);

        await i18n.changeLanguage('fr');
        await new Promise((r) => setTimeout(r, 60));

        expect(i18n.t('hosts.approveSelected')).toBe('Approuver la sélection');
        // ...and the plugin's own strings survive the merge.
        expect(i18n.t('pluginOnlyKey')).toBe('x');
    });

    it('has the catalog ready BEFORE the language flips, so nothing paints English', async () => {
        // The backstop repairs the language one paint late, which is visible as
        // a flash of English.  The selector pre-fetches instead, so the very
        // first render after the switch is already translated.
        const i18n = await makeInstance();
        const ensure = installCatalogGuard(
            i18n as unknown as Parameters<typeof installCatalogGuard>[0],
        );
        i18n.addResourceBundle('fr', 'translation', { pluginOnlyKey: 'x' });

        await ensure('fr');
        await i18n.changeLanguage('fr');

        // No settling delay here on purpose: that is the whole point.
        expect(i18n.t('hosts.approveSelected')).toBe('Approuver la sélection');
    });
});
