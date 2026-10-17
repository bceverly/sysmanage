// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { Button, ButtonProps, CircularProgress } from '@mui/material';
import { useActionInFlight } from '../hooks/useActionInFlight';

type AsyncButtonProps = Omit<ButtonProps, 'onClick'> & {
    /** May return a promise; the button stays disabled with a spinner until it settles. */
    onClick?: () => void | Promise<unknown>;
    /** Optional label shown while busy (e.g. "Rebooting..."); defaults to the children. */
    busyLabel?: React.ReactNode;
};

/**
 * A Button that cannot be pressed twice while its action is running.
 *
 * Confirm buttons that queued agent work ("Reboot", "Uninstall", "Deploy")
 * stayed live during the request, so a second press sent a second command
 * (2026-10-17).  Drop-in for MUI Button; a synchronous handler behaves as
 * before.
 */
const AsyncButton: React.FC<AsyncButtonProps> = ({
    onClick,
    busyLabel,
    disabled,
    startIcon,
    children,
    ...rest
}) => {
    const { busy, run } = useActionInFlight();
    const isBusy = busy !== null;
    return (
        <Button
            {...rest}
            disabled={disabled || isBusy}
            aria-busy={isBusy}
            startIcon={isBusy ? <CircularProgress size={16} color="inherit" /> : startIcon}
            onClick={() => {
                if (onClick) void run('click', onClick);
            }}
        >
            {isBusy && busyLabel ? busyLabel : children}
        </Button>
    );
};

export default AsyncButton;
