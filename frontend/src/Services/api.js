// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axios from "axios";
import { storeBearerToken } from "./bearerToken";

// Same-origin baseURL -- every backend route is now under /api, and both
// nginx (production) and vite (dev) reverse-proxy /api/* to the backend.
// Keeping requests relative means the browser never has to know what
// host:port the backend bound to.
const axiosInstance = axios.create({
  baseURL: "",
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true
});

axiosInstance.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('bearer_token');
        if (token) {
            config.headers["Authorization"] = "Bearer " + token;
        }
        return config;
    },
    (error) => {
      throw error;
    }
);

axiosInstance.interceptors.response.use(
  (res) => {
    // Successful response → mark connection healthy.  Dynamic import
    // dodges the circular dep -- connectionMonitor itself imports
    // axiosInstance for /api/health pings, so a static top-level
    // import here would deadlock module evaluation.
    import('./connectionMonitor')
      .then((m) => m.connectionMonitor?.markConnectionRestored?.())
      .catch(() => { /* never block a real response on monitor wiring */ });
    return res;
  },
  async (err) => handleResponseError(err)
);

// Network-level failure (backend unreachable / DNS / TLS / etc.) -- no
// response object to branch on, so the only signal is the absence of
// err.response.  Notify connectionMonitor so ServerDownModal renders
// instead of the browser surfacing a raw error.
function notifyNetworkFailure(err) {
  import('./connectionMonitor')
    .then((m) =>
      m.connectionMonitor?.markConnectionFailed?.(
        err.message || 'Network error: Unable to reach server'
      )
    )
    .catch(() => { /* monitor unavailable; bubble the error anyway */ });
}

// Redirect to the login page -- but NEVER when we're already on it.  A protected
// request that 401/403s while /login is open (e.g. a component that fetches before
// the user has authenticated) would otherwise reload /login, remount the
// component, refire the request, and loop forever.  Guarding on the current path
// makes the redirect idempotent and breaks that loop regardless of the caller.
function redirectToLogin() {
  if (!globalThis.location.pathname.startsWith('/login')) {
    globalThis.location.href = '/login';
  }
}

// Only a 403 that says "these credentials are unusable" sends the user to
// /login: the backend marks those with WWW-Authenticate (backend/auth/
// auth_bearer.py AUTH_FAILURE_HEADERS), and FastAPI's own missing-header 403
// says "Not authenticated" (never translated).  Every other 403 -- a role or
// administrator check, a Pro+ license gate -- is the calling code's error to
// show.  This used to redirect unless the detail contained the English words
// "Permission denied", so "Only an administrator can change the threat model"
// (and any denial in another language) logged the user out mid-task.
function handle403(response) {
  const headers = response.headers || {};
  const challenged = Boolean(headers['www-authenticate'] || headers['WWW-Authenticate']);
  const notAuthenticated = response.data?.detail === 'Not authenticated';
  if (challenged || notAuthenticated) {
    redirectToLogin();
  }
}

// "Normal" expired-access-token path -- try the refresh token, retry
// the original request, or fall back to /login.
async function handle401Refresh(originalConfig) {
  originalConfig._retry = true;
  console.log("Calling /refresh to get a new auth token...");
  try {
    const response = await axiosInstance.post("/api/v1/refresh", {});
    console.log('Received response:', response);
    storeBearerToken(response.data.Authorization);
    return axiosInstance(originalConfig);
  } catch (error) {
    console.log(error);
    localStorage.removeItem("userid");
    localStorage.removeItem("bearer_token");
    redirectToLogin();
    throw error;
  }
}

async function handleResponseError(err) {
  if (!err.response) {
    notifyNetworkFailure(err);
    throw err;
  }
  const originalConfig = err.config;
  // The login request itself failing (bad credentials) must short-circuit --
  // don't try the refresh-token path on it.  Match by suffix because the
  // login endpoint is now versioned (``/api/v1/login``), not ``/login``.
  // The single sign-on hand-off is the same kind of request: a 401 there
  // means the hand-off expired, and a refresh must not paper over it.
  if (originalConfig.url?.endsWith("/login") || originalConfig.url?.endsWith("/sso/session")) {
    throw err;
  }
  console.debug('Token expired? err.response = ' + err.response);
  console.debug('retry = ' + originalConfig._retry);
  if (err.response.status === 403) {
    handle403(err.response);
  }
  if (err.response.status === 401 && !originalConfig._retry) {
    return handle401Refresh(originalConfig);
  }
  throw err;
}

// Exported for its tests.
export { handle403 };

export default axiosInstance;