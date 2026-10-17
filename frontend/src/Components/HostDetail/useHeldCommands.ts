// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Commands a maintenance window is holding for this host.
//
// A held command used to look like a broken button: Ubuntu Pro "Attach" said
// "attach requested" and then nothing happened until the 02:00 window opened
// (production, 2026-10-16).  Two pieces fix that:
//   * useHeldCommands -- the host's hold status, polled, for the banner;
//   * useHeldAwareNotices -- wraps the snackbar setters the command-queuing
//     hooks receive, so a "requested" toast becomes "Pending the next
//     maintenance window (...)" while the host cannot receive changes.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TFunction } from 'i18next';

import { HostWindowStatus, maintenanceWindowsService } from '../../Services/maintenanceWindows';
import { formatUTCTimestamp } from '../../utils/dateUtils';
import type { SnackbarSeverity } from './useHostSnackbar';

const POLL_MS = 30000;

/** True when a command queued now would be held (not released at once). */
export const isHolding = (status: HostWindowStatus | null): boolean =>
    status?.state === 'blocked';

/** The toast for an action queued while the host is held, or null. */
export const pendingNotice = (status: HostWindowStatus | null, t: TFunction): string | null => {
    if (!isHolding(status)) {
        return null;
    }
    if (status?.next_window) {
        return t(
            'maintenanceWindows.pendingNextWindow',
            "Pending the next maintenance window ('{{name}}', opens {{time}}).",
            {
                name: status.next_window.name,
                time: formatUTCTimestamp(status.next_window.starts_at ?? ''),
            },
        );
    }
    return t('maintenanceWindows.pendingBlackout', "Pending: the '{{name}}' blackout is in effect.", {
        name: status?.active_blackout ?? '',
    });
};

export const useHeldCommands = (hostId: string | undefined) => {
    const [status, setStatus] = useState<HostWindowStatus | null>(null);

    const refresh = useCallback(async (): Promise<HostWindowStatus | null> => {
        if (!hostId) {
            return null;
        }
        try {
            const next = await maintenanceWindowsService.hostStatus(hostId);
            setStatus(next);
            return next;
        } catch {
            // No banner rather than a wrong one (e.g. a viewer without rights).
            return null;
        }
    }, [hostId]);

    useEffect(() => {
        void refresh();
        const timer = setInterval(() => { void refresh(); }, POLL_MS);
        return () => clearInterval(timer);
    }, [refresh]);

    return { status, refresh };
};

interface NoticeSetters {
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
    refresh: () => Promise<HostWindowStatus | null>;
}

/**
 * Snackbar setters for hooks whose actions QUEUE A COMMAND.  They buffer the
 * message and severity; when a success toast opens they re-read the host's
 * hold state and, if a window is holding changes, show the pending notice
 * instead.  Errors and warnings pass straight through.  If the status cannot
 * be read, today's message is shown unchanged.
 */
export const useHeldAwareNotices = ({
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
    refresh,
}: NoticeSetters) => {
    const message = useRef('');
    const severity = useRef<SnackbarSeverity>('success');

    return useMemo(() => {
        const wrappedMessage: React.Dispatch<React.SetStateAction<string>> = (value) => {
            message.current = typeof value === 'function' ? value(message.current) : value;
            setSnackbarMessage(value);
        };
        const wrappedSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>> = (value) => {
            severity.current = typeof value === 'function' ? value(severity.current) : value;
            setSnackbarSeverity(value);
        };
        const wrappedOpen: React.Dispatch<React.SetStateAction<boolean>> = (value) => {
            const opening = typeof value === 'function' ? value(false) : value;
            if (!opening || severity.current !== 'success') {
                setSnackbarOpen(value);
                return;
            }
            void refresh().then((status) => {
                const notice = pendingNotice(status, t);
                if (notice) {
                    setSnackbarMessage(notice);
                    setSnackbarSeverity('warning');
                }
                setSnackbarOpen(true);
            });
        };
        return {
            setSnackbarMessage: wrappedMessage,
            setSnackbarSeverity: wrappedSeverity,
            setSnackbarOpen: wrappedOpen,
        };
    }, [t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen, refresh]);
};
