// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Regression test for "switching language shows English until you refresh".
 *
 * Catalogs are fetched over HTTP on demand, so ``changeLanguage`` resolves
 * BEFORE the new catalog exists.  react-i18next re-renders on
 * 'languageChanged', every lookup misses, and fallbackLng paints English.  The
 * bundle lands a moment later and i18next emits a STORE event -- which
 * react-i18next ignores unless ``bindI18nStore`` is set, so the English render
 * stands until a reload.
 *
 * This reproduces the exact sequence with a deliberately slow backend rather
 * than asserting the config value, because the config value is not the
 * behaviour anyone cares about.
 */

import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createInstance } from 'i18next';
import { I18nextProvider, initReactI18next, useTranslation } from 'react-i18next';

const CATALOGS: Record<string, Record<string, string>> = {
    en: { greeting: 'Hosts' },
    nl: { greeting: 'Hosts (nl)' },
};

/** A backend that answers on a later tick, like a real network fetch. */
const slowBackend = {
    type: 'backend' as const,
    init: () => undefined,
    // eslint-disable-next-line no-unused-vars
    read(language: string, _ns: string, callback: (e: unknown, d?: unknown) => void) {
        setTimeout(() => callback(null, CATALOGS[language] ?? {}), 20);
    },
};

const Probe = () => {
    const { t } = useTranslation();
    return <span data-testid="greeting">{t('greeting')}</span>;
};

const makeInstance = (react?: Record<string, unknown>) => {
    const instance = createInstance();
    instance.use(slowBackend).use(initReactI18next).init({
        lng: 'en',
        fallbackLng: 'en',
        interpolation: { escapeValue: false },
        react: { useSuspense: false, ...(react || {}) },
    });
    return instance;
};

describe('language switching with lazily fetched catalogs', () => {
    it('shows the new language without a page reload', async () => {
        const i18n = makeInstance({ bindI18nStore: 'added' });
        await waitFor(() => expect(screen.queryByTestId('greeting')).toBeNull());

        render(
            <I18nextProvider i18n={i18n}>
                <Probe />
            </I18nextProvider>,
        );
        await waitFor(() =>
            expect(screen.getByTestId('greeting').textContent).toBe('Hosts'),
        );

        // changeLanguage re-renders every subscribed component, so it has to
        // happen inside act() -- otherwise React warns that the update escaped
        // the test's control.
        await act(async () => {
            await i18n.changeLanguage('nl');
        });

        // The catalog is still in flight here; what matters is that the UI
        // catches up on its own once it lands.
        await waitFor(() =>
            expect(screen.getByTestId('greeting').textContent).toBe('Hosts (nl)'),
        );
    });
});
