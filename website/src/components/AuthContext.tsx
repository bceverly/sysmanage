import React, { createContext, useContext, useState } from 'react';
import axios from "axios";

const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

type DoLoginRequest = {
  'userid': string;
  'password': string;
}

type DoLoginResponse = {
  "Reauthorization": string;
}

type CheckValidResponse = {
  'result': string;
}

export const AuthProvider = ({ children }) => {
  const [isLoggedIn, setIsLoggedIn] = useState(!!localStorage.getItem('bearer_token'));

  const login = (requestData: DoLoginRequest) => {
    console.log('Calling /login...');
    axios.post("https://api.sysmanage.org:8443/login", {
      'userid': requestData.userid,
      'password': requestData.password
    }, {
      headers: {
        'Content-Type': "application/json"
      }
    })
    .then((response) => {
    // No error - process response
      console.log('Reauthorization = ' + response.data.Reauthorization);
      localStorage.setItem("userid", requestData.userid);
      localStorage.setItem("bearer_token", response.data.Reauthorization);
    })
    .catch((error) => {
      // Error situation - clear out storage
      localStorage.removeItem("userid");
      localStorage.removeItem("bearer_token");
  
      if (error.response) {
        // Error response returned by server
        console.log('Error returned by server: ' + error);
      } else if (error.request) {
        // Error was in the request, no response sent by server
        console.log('Error - no response from server: ' + error);
      } else {
        // Some other error
        console.log('Unknown error: ' + error);
      }
    });
  };
  
  const logout = () => {
    console.log('Removing local storage...');
    localStorage.removeItem("userid");
    localStorage.removeItem("bearer_token");
    console.log("local storage removed");
  };
  
  const checkValid = () => {
    console.log('Calling /validate...');
    axios.post<CheckValidResponse>("https://api.sysmanage.org:8443/validate", {},
    {
      headers: {
        'Content-Type': "application/json",
        'Authorization': "Bearer "+localStorage.getItem("bearer_token")
      }
    })
    .then ((res) => {
      // No error - process response
      localStorage.setItem("bearer_token", res.headers["reauthorization"]);
      console.log('checkValid() token = ' + res.headers["reauthorization"]);
    })
    .catch ((err) => {
      // Error situation - clear out storage
      localStorage.removeItem("userid");
      localStorage.removeItem("bearer_token");
  
      if (err.response) {
        // Error response returned by server
        console.log('Error returned by server: ' + err);
      } else if (err.request) {
        // Error was in the request, no response sent by server
        console.log('Error - no response from server: ' + err);
      } else {
        // Some other error
        console.log('Unknown error: ' + err);
      }
    });  
  };

  return (
    <AuthContext.Provider value={{ isLoggedIn, login, logout, checkValid }}>
      const AuthContext: React.Context<any>
    </AuthContext.Provider>
  );
};

export default AuthContext;