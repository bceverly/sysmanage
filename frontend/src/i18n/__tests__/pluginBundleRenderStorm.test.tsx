// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * What mounting the Pro+ plugin bundles actually costs in re-renders.
 *
 * WRITTEN AS A NEGATIVE RESULT, ON PURPOSE
 * ----------------------------------------
 * On 2026-08-29 the documentation screenshots failed in a suggestive pattern:
 * every capture that CLICKED something ("no rail button or tab named X became
 * clickable within 30s", "never became stably clickable") failed, while every
 * capture that merely navigated to a URL hash succeeded. Playwright will not
 * click an element until it holds the same position across consecutive frames,
 * so "the page never stops re-rendering" was an attractive explanation --
 * especially since each plugin calls ``addResourceBundle`` once per language
 * (en + 13), and 20 bundles ship.
 *
 * MEASURED, and it is not that:
 *
 *   * 20 plugins x 14 languages, each language on its own tick  -> 280 renders
 *   * 20 plugins, each registering all 14 languages synchronously ->  20 renders
 *   * no i18next calls at all (control)                           ->   0 renders
 *
 * The real ``registerPluginI18n`` takes the SECOND shape: its per-language loop
 * is synchronous inside one function call, so React batches it and each plugin
 * costs a single render. Twenty renders spread over plugin load is ordinary and
 * cannot defeat an actionability check.
 *
 * Also measured, because it was the other half of the theory: ``bindI18nStore:
 * 'added'`` makes NO difference to any of these numbers -- react-i18next
 * re-renders on a resource-bundle add either way. Any future work aimed at that
 * setting is aimed at the wrong thing.
 *
 * So these tests do not guard a bug that exists. They pin the cheap shape in
 * place (so a future refactor that made registration asynchronous per language
 * would be caught at 280 rather than 20), and they close this line of enquiry
 * for whoever looks at the screenshot flake next.
 */

import React from 'react';
import { act, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createInstance, i18n as I18nInstance } from 'i18next';
import { I18nextProvider, initReactI18next, useTranslation } from 'react-i18next';

/** Every language the app ships, as a plugin sees them. */
const LANGUAGES = [
    'en',
    'ar',
    'de',
    'es',
    'fr',
    'hi',
    'it',
    'ja',
    'ko',
    'nl',
    'pt',
    'ru',
    'zh_CN',
    'zh_TW',
];

const PLUGIN_COUNT = 20;

const makeInstance = async (bindI18nStore: string | false) => {
    const instance = createInstance();
    await instance.use(initReactI18next).init({
        lng: 'en',
        fallbackLng: 'en',
        resources: { en: { translation: {} } },
        interpolation: { escapeValue: false },
        react: bindI18nStore === false ? {} : { bindI18nStore },
    });
    return instance;
};

/** Count renders of a component that consumes translations. */
const renderCounter = (instance: I18nInstance) => {
    const renders = { count: 0 };
    const Consumer: React.FC = () => {
        useTranslation();
        renders.count += 1;
        return <div>consumer</div>;
    };
    render(
        <I18nextProvider i18n={instance}>
            <Consumer />
        </I18nextProvider>,
    );
    return renders;
};

/**
 * Mount plugins the way the product does: each bundle's script loads on its own
 * tick, and inside it ``registerPluginI18n`` adds every language synchronously.
 */
const mountPluginsRealistically = async (instance: I18nInstance, count: number) => {
    for (let plugin = 0; plugin < count; plugin += 1) {
        await act(async () => {
            for (const lang of LANGUAGES) {
                instance.addResourceBundle(
                    lang,
                    'translation',
                    { [`plugin${plugin}Key`]: 'x' },
                    true,
                    true,
                );
            }
            await Promise.resolve();
        });
    }
};

describe('cost of mounting the Pro+ plugin bundles', () => {
    it('costs one render per plugin, not one per language', async () => {
        const instance = await makeInstance('added');
        const renders = renderCounter(instance);
        const baseline = renders.count;

        await mountPluginsRealistically(instance, PLUGIN_COUNT);

        // If registration ever became asynchronous per language this would
        // jump to plugins x languages (measured at 280), which is the shape
        // that WOULD keep a page from holding still.
        expect(renders.count - baseline).toBeLessThanOrEqual(PLUGIN_COUNT + 2);
    });

    it('a synchronous burst of every language is batched into one render', async () => {
        const instance = await makeInstance('added');
        const renders = renderCounter(instance);
        const baseline = renders.count;

        await act(async () => {
            for (const lang of LANGUAGES) {
                instance.addResourceBundle(lang, 'translation', { k: 'x' }, true, true);
            }
        });

        expect(renders.count - baseline).toBeLessThanOrEqual(2);
    });

    it('bindI18nStore does not change the cost either way', async () => {
        // Recorded so nobody re-derives the wrong lever. react-i18next
        // re-renders on a bundle add with or without it; the setting exists so
        // a catalog arriving late actually paints, which is a different
        // concern from render volume.
        const counts: number[] = [];
        for (const bind of ['added', false] as const) {
            const instance = await makeInstance(bind);
            const renders = renderCounter(instance);
            const baseline = renders.count;
            await mountPluginsRealistically(instance, 3);
            counts.push(renders.count - baseline);
        }
        expect(counts[0]).toBe(counts[1]);
    });

    it('touching nothing costs nothing (control)', async () => {
        // The control that made the other numbers trustworthy: without it, a
        // harness that re-rendered on its own would have looked like a finding.
        const instance = await makeInstance('added');
        const renders = renderCounter(instance);
        const baseline = renders.count;

        for (let i = 0; i < PLUGIN_COUNT; i += 1) {
            await act(async () => {
                await Promise.resolve();
            });
        }

        expect(renders.count - baseline).toBe(0);
    });
});
