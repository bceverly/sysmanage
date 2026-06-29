import axios from "axios";

// Same-origin baseURL — every backend route is now under /api, and both
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
    // dodges the circular dep — connectionMonitor itself imports
    // axiosInstance for /api/health pings, so a static top-level
    // import here would deadlock module evaluation.
    import('./connectionMonitor')
      .then((m) => m.connectionMonitor?.markConnectionRestored?.())
      .catch(() => { /* never block a real response on monitor wiring */ });
    return res;
  },
  async (err) => handleResponseError(err)
);

// Network-level failure (backend unreachable / DNS / TLS / etc.) — no
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

// Pro+ license checks and role-based permission denials must not
// redirect — let the calling code show an error toast.  Only redirect
// to login for auth-related 403s (expired refresh token).
function handle403(response) {
  const errorData = response.data;
  const detail = errorData?.detail || '';
  const isProPlusError = errorData?.error === 'pro_plus_required' ||
                         errorData?.detail?.error === 'pro_plus_required';
  const isPermissionDenied = typeof detail === 'string' &&
                             detail.includes('Permission denied');
  if (!isProPlusError && !isPermissionDenied) {
    globalThis.location.href = '/login';
  }
}

// "Normal" expired-access-token path — try the refresh token, retry
// the original request, or fall back to /login.
async function handle401Refresh(originalConfig) {
  originalConfig._retry = true;
  console.log("Calling /refresh to get a new auth token...");
  try {
    const response = await axiosInstance.post("/api/v1/refresh", {});
    console.log('Received response:', response);
    localStorage.setItem("bearer_token", response.data.Authorization);
    return axiosInstance(originalConfig);
  } catch (error) {
    console.log(error);
    localStorage.removeItem("userid");
    localStorage.removeItem("bearer_token");
    globalThis.location.href = '/login';
    throw error;
  }
}

async function handleResponseError(err) {
  if (!err.response) {
    notifyNetworkFailure(err);
    throw err;
  }
  const originalConfig = err.config;
  if (originalConfig.url === "/login") {
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

export default axiosInstance;