import axios from "axios";

// Dynamically determine the backend URL based on current host
const getBackendBaseURL = () => {
  const currentHost = globalThis.location.hostname;
  // Use environment variable if available, otherwise default to 8080
  const backendPort = import.meta.env.VITE_BACKEND_PORT || 8080;
  return `http://${currentHost}:${backendPort}`;
};

const axiosInstance = axios.create({
  baseURL: getBackendBaseURL(),
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
    return res;
  },
  async (err) => {
    const originalConfig = err.config;

    if (originalConfig.url !== "/login" && err.response) {
      // Access Token was expired
      console.debug('Token expired? err.response = ' + err.response);
      console.debug('retry = ' + originalConfig._retry);

      // Handle 403 Forbidden responses:
      // - Role-based permission denials (e.g. "Permission denied: ... role required")
      //   should NOT redirect — let the calling code show an error toast
      // - Pro+ license checks should NOT redirect
      // - Only redirect to login for auth-related 403s (expired refresh token)
      if (err.response.status === 403) {
        const errorData = err.response.data;
        const detail = errorData?.detail || '';
        const isProPlusError = errorData?.error === 'pro_plus_required' ||
                               errorData?.detail?.error === 'pro_plus_required';
        const isPermissionDenied = typeof detail === 'string' &&
                                   detail.includes('Permission denied');
        if (!isProPlusError && !isPermissionDenied) {
          globalThis.location.href = '/login';
        }
      }

      // This is the "normal" case of an expired auth token where
      // we want to use the refresh token to reauthenticate under
      // the covers.
      if (err.response.status === 401 && !originalConfig._retry) {
        originalConfig._retry = true;

        console.log("Calling /refresh to get a new auth token...");
        try {
          const response = await axiosInstance.post("/refresh", {});
          console.log('Received response:', response);
          localStorage.setItem("bearer_token", response.data.Authorization);
          return axiosInstance(originalConfig);
        } catch (error) {
          // Refresh failed — clear storage and redirect to login
          console.log(error);
          localStorage.removeItem("userid");
          localStorage.removeItem("bearer_token");
          globalThis.location.href = '/login';
          throw error;
        }
      }
    }

    throw err;
  }
);

export default axiosInstance;