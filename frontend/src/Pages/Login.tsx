import { useState } from "react";
import { useNavigate } from "react-router-dom";

import axios from "axios";
//import { doLogin } from "../Services/AuthHelper";
import './css/Login.css'

const Login = () => {
    const [input, setInput] = useState({
      userid: "",
      password: "",
    });
    const navigate = useNavigate();
    const handleSubmitEvent = (e: { preventDefault: () => void; }) => {
      e.preventDefault();
      if (input.userid !== "" && input.password !== "") {
        axios.post("https://api.sysmanage.org:8443/login", {
          'userid': input.userid,
          'password': input.password
        }, {
          headers: {
            'Content-Type': "application/json"
          }
        })
        .then((response) => {
        // No error - process response
          console.log('Reauthorization = ' + response.data.Reauthorization);
          localStorage.setItem("userid", input.userid);
          localStorage.setItem("bearer_token", response.data.Reauthorization);
          navigate("/");
          window.location.reload();
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
      }
    };

    const handleInput = (e: { target: { name: any; value: any; }; }) => {
      const { name, value } = e.target;
      setInput((prev) => ({
        ...prev,
        [name]: value,
      }));
    };

  return (
    <div className="form-container">
      <form id='login-form' className="form" onSubmit={handleSubmitEvent}>
        <h2>Login</h2>
        <div>
          <input required name="userid" id="userid" type="text" placeholder="Email" onChange={handleInput} />
        </div>
        <div>
          <input required name="password" id="password" type="password" placeholder="Password" onChange={handleInput} />
        </div>
        <button type="submit">Login</button>
      </form>
    </div>
  );
};

export default Login;