import axios from "axios";
import { useNavigate } from "react-router-dom";

// Dynamically determine the backend URL based on current host
const getBackendBaseURL = () => {
  const currentHost = window.location.hostname;
  const backendPort = 8080; // This should match your config file
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
      return Promise.reject(error);
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

      // This is an attempt to log in with an expired refresh token
      if (err.response.status === 403) {
        window.location.href = '/login';
      }

      // This is the "normal" case of an expired auth token where
      // we want to use the refresh token to reauthenticate under
      // the covers.
      if (err.response.status === 401 && !originalConfig._retry) {
        originalConfig._retry = true;

        try {
          console.log("Calling /refresh to get a new auth token...");
          await axiosInstance.post("/refresh", {
          })
          .then((response) => {
            console.log('Received response: ' + response);
            localStorage.setItem("bearer_token", response.data.Authorization);
            return axiosInstance(originalConfig);
          })
          .catch((error) => {
            // Error situation - clear out storage
            console.log(error);
            localStorage.removeItem("userid");
            localStorage.removeItem("bearer_token");

            const navigate = useNavigate();

            navigate("/login")
            return Promise.reject(error);
          });

          return axiosInstance(originalConfig);
        } catch (_error) {
          return Promise.reject(_error);
        }
      }
    }

    return Promise.reject(err);
  }
);

export default axiosInstance;