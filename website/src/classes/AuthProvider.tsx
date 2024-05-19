import {useContext, createContext } from "react";
import axios from "axios";

class AuthProvider {
  doLogin(data) {
    return axios
      .post("https://api.sysmanage.org:8443/login", data, {
        headers: {
          'Content-Type': "application/json"
        }
      })
      .then((response) => {
        localStorage.setItem("userid", data.userid);
        localStorage.setItem("bearer_token", response.data.X_Reauthorization);

      return response.data;
    });
  }

  doLogout() {
    localStorage.removeItem("userid");
    localStorage.removeItem("bearer_token");
  }
}

export default new AuthProvider();