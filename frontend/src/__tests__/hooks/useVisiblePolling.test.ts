// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useVisiblePolling } from '../../hooks/useVisiblePolling';

let visibility: DocumentVisibilityState = 'visible';

const setVisibility = (state: DocumentVisibilityState) => {
    visibility = state;
    document.dispatchEvent(new Event('visibilitychange'));
};

describe('useVisiblePolling', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        visibility = 'visible';
        vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    it('polls on its interval while the page is visible', () => {
        const poll = vi.fn();
        renderHook(() => useVisiblePolling(poll, 1000));
        expect(poll).not.toHaveBeenCalled(); // the first load is the caller's
        vi.advanceTimersByTime(3000);
        expect(poll).toHaveBeenCalledTimes(3);
    });

    it('makes no poll while the tab is hidden, and one when it is shown again', () => {
        const poll = vi.fn();
        renderHook(() => useVisiblePolling(poll, 1000));
        setVisibility('hidden');
        vi.advanceTimersByTime(10_000);
        expect(poll).not.toHaveBeenCalled();
        setVisibility('visible');
        expect(poll).toHaveBeenCalledTimes(1);
    });

    it('does not poll on becoming visible when a poll is not due', () => {
        const poll = vi.fn();
        renderHook(() => useVisiblePolling(poll, 1000));
        setVisibility('hidden');
        vi.advanceTimersByTime(500);
        setVisibility('visible');
        expect(poll).not.toHaveBeenCalled();
    });

    it('does nothing when disabled, and stops on unmount', () => {
        const poll = vi.fn();
        const { unmount } = renderHook(() => useVisiblePolling(poll, 1000, false));
        vi.advanceTimersByTime(5000);
        expect(poll).not.toHaveBeenCalled();
        unmount();

        const poll2 = vi.fn();
        const second = renderHook(() => useVisiblePolling(poll2, 1000));
        second.unmount();
        vi.advanceTimersByTime(5000);
        setVisibility('hidden');
        setVisibility('visible');
        expect(poll2).not.toHaveBeenCalled();
    });

    it('uses the latest callback without restarting the timer', () => {
        const first = vi.fn();
        const second = vi.fn();
        const { rerender } = renderHook(({ cb }) => useVisiblePolling(cb, 1000), {
            initialProps: { cb: first },
        });
        vi.advanceTimersByTime(500);
        rerender({ cb: second });
        vi.advanceTimersByTime(500);
        expect(first).not.toHaveBeenCalled();
        expect(second).toHaveBeenCalledTimes(1);
    });
});
