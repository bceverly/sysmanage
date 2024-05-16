import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AuthProvider from "../classes/AuthProvider";

import styles from './styles/login.css'

const Login = () => {
    const [input, setInput] = useState({
      userid: "",
      password: "",
    });
    const navigate = useNavigate();
    const handleSubmitEvent = (e) => {
      e.preventDefault();
      if (input.userid !== "" && input.password !== "") {
        console.log(input);
        AuthProvider.doLogin(input);
        if (localStorage.getItem("bearer_token")) {
          navigate("/");
        }
        return;
      }
      alert("please provide a valid input");
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