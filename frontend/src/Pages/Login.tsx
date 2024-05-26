import { useState } from "react";
import { useNavigate } from "react-router-dom";

import api from "../Services/api"
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
        api.post("/login", {
          userid: input.userid,
          password: input.password
        })
        .then((response: { data: { Reauthorization: any; }; }) => {
          if (response.data.Reauthorization) {
            localStorage.setItem("userid", input.userid);
            localStorage.setItem("bearer_token", response.data.Reauthorization);
          }

          navigate("/");
          window.location.reload();
          return response.data;
        })
        .catch((error) => {
          // Error situation - clear out storage
          localStorage.removeItem("userid");
          localStorage.removeItem("bearer_token");
          alert('Invalid userid/password combination.');
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