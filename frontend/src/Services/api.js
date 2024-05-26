import axios from "axios";

const axiosInstance = axios.create({
  baseURL: "https://api.sysmanage.org:6443",
  headers: {
    "Content-Type": "application/json",
  },
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
      if (err.response.status === 401 && !originalConfig._retry) {
        originalConfig._retry = true;

        try {
/*          const rs = await axiosInstance.post("/auth/refreshtoken", {
            refreshToken: TokenService.getLocalRefreshToken(),
          });*/

/*          const { accessToken } = rs.data;
          TokenService.updateLocalAccessToken(accessToken);*/

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