// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/* global Event */
// Snackbar state for the Host Detail page.  Kept in its own hook so the many
// action hooks can share the same feedback surface by receiving the setters.

import React, { useState } from 'react';

export type SnackbarSeverity = 'success' | 'error' | 'warning';

export interface HostSnackbar {
    snackbarOpen: boolean;
    snackbarMessage: string;
    snackbarSeverity: SnackbarSeverity;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    handleCloseSnackbar: (event: React.SyntheticEvent | Event, reason?: string) => void;
}

export const useHostSnackbar = (): HostSnackbar => {
    const [snackbarOpen, setSnackbarOpen] = useState<boolean>(false);
    const [snackbarMessage, setSnackbarMessage] = useState<string>('');
    const [snackbarSeverity, setSnackbarSeverity] = useState<SnackbarSeverity>('success');

    const handleCloseSnackbar = (_event: React.SyntheticEvent | Event, reason?: string) => {
        if (reason === 'clickaway') {
            return;
        }
        setSnackbarOpen(false);
    };

    return {
        snackbarOpen,
        snackbarMessage,
        snackbarSeverity,
        setSnackbarOpen,
        setSnackbarMessage,
        setSnackbarSeverity,
        handleCloseSnackbar,
    };
};
