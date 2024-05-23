import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../components/AuthContext";
import './styles/login.css'

const Login = () => {
    const { doLogin } = useAuth();
    
    const [input, setInput] = useState({
      userid: "",
      password: "",
    });
    const navigate = useNavigate();
    const handleSubmitEvent = (e) => {
      e.preventDefault();
      if (input.userid !== "" && input.password !== "") {
        doLogin(input)
        .then (() => {
          if (localStorage.getItem("bearer_token")) {
            console.log('navigating to /hosts');
            navigate("/hosts");
          } else {
            alert("Please provide a valid userid/password combination.");
          }
          return;
        })
        .catch ((err) => {
          alert("Error calling login API.  Are you connected to the Internet?");
        });
      }
    };

    const handleInput = (e) => {
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