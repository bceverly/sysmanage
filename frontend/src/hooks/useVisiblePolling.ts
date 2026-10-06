// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { useEffect, useRef } from 'react';

const isHidden = (): boolean =>
    typeof document !== 'undefined' && document.visibilityState === 'hidden';

/**
 * Call ``poll`` every ``intervalMs`` while the page is visible (Phase 22.7).
 *
 * Every open console tab polled the server on its timers whether anyone was
 * looking or not; a dashboard left open in a background tab cost the server
 * as much as one in use.  While the tab is hidden no poll is made; when it
 * becomes visible again and a poll is due, one is made at once, so the page
 * is current the moment it is looked at.  The first load is the caller's:
 * this only repeats.  ``enabled`` false stops polling (e.g. signed out).
 */
export const useVisiblePolling = (
    poll: () => void | Promise<void>,
    intervalMs: number,
    enabled = true,
): void => {
    const pollRef = useRef(poll);
    useEffect(() => {
        pollRef.current = poll;
    }, [poll]);

    useEffect(() => {
        if (!enabled) return undefined;
        let last = Date.now();
        const run = () => {
            last = Date.now();
            void pollRef.current();
        };
        const tick = () => {
            if (!isHidden()) run();
        };
        const onVisibility = () => {
            if (!isHidden() && Date.now() - last >= intervalMs) run();
        };
        const id = globalThis.setInterval(tick, intervalMs);
        document.addEventListener('visibilitychange', onVisibility);
        return () => {
            globalThis.clearInterval(id);
            document.removeEventListener('visibilitychange', onVisibility);
        };
    }, [intervalMs, enabled]);
};
