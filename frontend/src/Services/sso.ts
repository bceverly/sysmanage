// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from "./api";

/**
 * Single sign-on from the login page (OIDC + SAML).
 *
 * The identity provider returns the browser to the server's callback, not to
 * this app; the server then redirects here (/login/sso) holding the session
 * in a short-lived HttpOnly cookie, never in the URL.  takeSession() asks the
 * server for it -- once.
 */

export interface SsoProvider {
    id: string;
    name: string;
    type: "oidc" | "saml";
    start_url: string;
}

export interface SsoSession {
    Authorization: string;
    userid: string;
}

/** Why the server sent the browser back without a session. */
export type SsoFailure = "denied" | "unavailable" | "failed" | "expired";

export const getSsoProviders = async (): Promise<SsoProvider[]> => {
    const response = await axiosInstance.get<SsoProvider[]>("/api/auth/sso/providers");
    return Array.isArray(response.data) ? response.data : [];
};

export const takeSsoSession = async (): Promise<SsoSession> => {
    const response = await axiosInstance.post<SsoSession>("/api/auth/sso/session", {});
    return response.data;
};
