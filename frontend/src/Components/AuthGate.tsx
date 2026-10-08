// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Decides, BEFORE a page renders, whether there is a session to render it
// for.  Every page used to check for itself in a useEffect -- after its first
// paint -- so a signed-out visitor saw the dashboard flash before the login
// screen (and with an expired token, the dashboard sat there until its API
// calls failed and the refresh failed).

import React, { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router';
import axiosInstance from '../Services/api';

/** Pages reachable without a session. */
export const PUBLIC_PATHS = ['/login', '/login/sso', '/reset-password', '/accept-invitation'];

/** True when the access token's ``exp`` has passed (false if it cannot tell). */
export function tokenExpired(token: string): boolean {
    try {
        const part = token.split('.')[1].replaceAll('-', '+').replaceAll('_', '/');
        const payload = JSON.parse(globalThis.atob(part)) as { exp?: unknown };
        return typeof payload.exp === 'number' && payload.exp * 1000 <= Date.now();
    } catch {
        return false;
    }
}

const AuthGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const location = useLocation();
    const isPublic = PUBLIC_PATHS.includes(location.pathname);
    const token = localStorage.getItem('bearer_token');
    const expired = token ? tokenExpired(token) : false;
    const [refreshing, setRefreshing] = useState(false);

    useEffect(() => {
        if (isPublic || !token || !expired || refreshing) return;
        // An expired access token may still have a good refresh cookie: try
        // it (showing nothing meanwhile) before sending the user to sign in.
        setRefreshing(true);
        axiosInstance
            .post('/api/v1/refresh', {})
            .then((response) => {
                localStorage.setItem('bearer_token', response.data.Authorization);
            })
            .catch(() => {
                localStorage.removeItem('bearer_token');
                localStorage.removeItem('userid');
            })
            .finally(() => setRefreshing(false));
    }, [isPublic, token, expired, refreshing]);

    if (isPublic) return <>{children}</>;
    if (!token) return <Navigate to="/login" replace />;
    if (expired) return null;
    return <>{children}</>;
};

export default AuthGate;
