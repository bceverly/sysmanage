// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * One action at a time, and visibly so.
 *
 * Buttons that queued agent work gave no sign they had been pressed -- the
 * "Deploy antivirus" button looked idle until the agent reported back
 * minutes later, so a user pressed it again and again (2026-10-17).
 *
 * ``run(key, fn)`` refuses a second call while one is running (a ref, so two
 * clicks in the same tick still send one request) and exposes which action
 * is running, so the button can disable itself and say "Deploying...".
 */
export const useActionInFlight = () => {
    const [busy, setBusy] = useState<string | null>(null);
    const running = useRef<string | null>(null);

    // The slot is claimed BEFORE the handler runs, so two clicks in the same
    // tick still call it once.  Busy is only shown when the handler returns a
    // promise -- a synchronous one (opening a dialog) changes nothing.
    const run = useCallback(<T>(key: string, fn: () => T | Promise<T>): Promise<T | undefined> => {
        if (running.current) return Promise.resolve(undefined);
        running.current = key;
        let result: T | Promise<T>;
        try {
            result = fn();
        } catch (err) {
            running.current = null;
            return Promise.reject(err);
        }
        if (!result || typeof (result as Promise<T>).then !== 'function') {
            running.current = null;
            return Promise.resolve(result as T);
        }
        setBusy(key);
        return (result as Promise<T>).finally(() => {
            running.current = null;
            setBusy(null);
        });
    }, []);

    const isBusy = useCallback((key?: string) => (key ? busy === key : busy !== null), [busy]);

    return { busy, isBusy, run };
};

interface Awaiting<S> {
    key: string;
    done: (status: S | null) => boolean;
}

/** How long to wait for the agent to report a queued change before giving up. */
export const AGENT_CONFIRM_TIMEOUT_MS = 10 * 60 * 1000;

/**
 * After the server accepts a command, keep showing it as in progress until
 * the host's next status report shows the change (``done(status)``), or until
 * ``timeoutMs`` passes -- then ``timedOut`` names the action, so the page can
 * say the agent has not confirmed yet instead of silently going idle.
 */
export const useAgentCommandProgress = <S>(status: S | null, timeoutMs = AGENT_CONFIRM_TIMEOUT_MS) => {
    const [awaiting, setAwaiting] = useState<Awaiting<S> | null>(null);
    const [timedOut, setTimedOut] = useState<string | null>(null);

    const begin = useCallback((key: string, done: (s: S | null) => boolean) => {
        setTimedOut(null);
        setAwaiting({ key, done });
    }, []);

    useEffect(() => {
        if (awaiting?.done(status)) setAwaiting(null);
    }, [awaiting, status]);

    useEffect(() => {
        if (!awaiting) return undefined;
        const timer = setTimeout(() => {
            setTimedOut(awaiting.key);
            setAwaiting(null);
        }, timeoutMs);
        return () => clearTimeout(timer);
    }, [awaiting, timeoutMs]);

    return { awaitingKey: awaiting?.key ?? null, timedOut, begin };
};
