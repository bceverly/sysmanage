// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Does the desktop menubar fit between the logo and the toolbar?
 *
 * A fixed breakpoint cannot answer it: the menu's width depends on the
 * language (Russian labels are about half again as wide as English) and on
 * the chips beside the logo.  At 1280 px in English the search button sat on
 * top of "Administration" (2026-11-21).  So the navbar measures: the menubar
 * stays laid out (hidden when it does not fit, so it can still be measured),
 * and the compact menu button takes over until there is room again.
 *
 * Without ResizeObserver (tests, very old browsers) it always fits, as before.
 */

import { RefObject, useLayoutEffect, useState } from 'react';

// Spacing the measurement must leave: the menubar's own left margin (1.5rem)
// and the nav's gaps around it (1rem each), plus a little slack.
const SPARE_PX = 24 + 32 + 16;

export interface MenubarRefs {
    nav: RefObject<HTMLElement | null>;
    logo: RefObject<HTMLElement | null>;
    menubar: RefObject<HTMLElement | null>;
    toolbar: RefObject<HTMLElement | null>;
}

/** The menubar's natural width: its triggers side by side, never wrapped. */
export const neededWidth = (menubar: HTMLElement): number => {
    const items = Array.from(menubar.children) as HTMLElement[];
    const gap = Number.parseFloat(globalThis.getComputedStyle(menubar).columnGap || '0') || 0;
    const widths = items.reduce((sum, el) => sum + el.getBoundingClientRect().width, 0);
    return widths + gap * Math.max(0, items.length - 1);
};

export const menubarFits = (
    navWidth: number, logoWidth: number, toolbarWidth: number, needed: number,
): boolean => needed <= navWidth - logoWidth - toolbarWidth - SPARE_PX;

export const useMenubarFits = (refs: MenubarRefs, deps: unknown[]): boolean => {
    const [fits, setFits] = useState(true);
    useLayoutEffect(() => {
        const { nav, logo, menubar, toolbar } = refs;
        if (typeof ResizeObserver === 'undefined' || !nav.current) return undefined;
        const measure = () => {
            if (!nav.current || !menubar.current) return;
            setFits(menubarFits(
                nav.current.clientWidth,
                logo.current?.getBoundingClientRect().width ?? 0,
                toolbar.current?.getBoundingClientRect().width ?? 0,
                neededWidth(menubar.current),
            ));
        };
        const observer = new ResizeObserver(measure);
        for (const ref of [nav, logo, menubar, toolbar]) {
            if (ref.current) observer.observe(ref.current);
        }
        measure();
        return () => observer.disconnect();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps);
    return fits;
};
