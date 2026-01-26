import api from "./api";

type DoLoginRequest = {
  'userid': string;
  'password': string;
}


const doLogin = async (requestData: DoLoginRequest) => {
  await api.post("/login", {
    'userid': requestData.userid,
    'password': requestData.password
  })
  .then((response) => {
    // No error - process response
    localStorage.setItem("userid", requestData.userid);
    localStorage.setItem("bearer_token", response.data.Authorization);
    return response;
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

    throw error;
  });
};

const doLogout = () => {
  localStorage.removeItem("userid");
  localStorage.removeItem("bearer_token");
};

export { doLogin, doLogout };