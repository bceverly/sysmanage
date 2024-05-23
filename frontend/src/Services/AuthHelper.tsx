import React, { createContext, useContext, useState } from 'react';
import axios from "axios";

export const useAuth = () => null;

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

const doLogin = (requestData: DoLoginRequest) => {
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

const doLogout = () => {
  localStorage.removeItem("userid");
  localStorage.removeItem("bearer_token");
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

export { doLogin, doLogout, checkValid };