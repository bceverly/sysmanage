import Axios from "axios";
import styles from './styles/login.css'

const SignIn = () => {
  const handleSubmit = (event) => {
    event.preventDefault();

    const email = event.target.elements.email.value;
    const password = event.target.elements.password.value;

    Axios.post('https://api.sysmanage.org:8443/login', {
        "userid": email,
        "password": password
    })
    .then((response) => {
      console.log(response.data);
    })
    .catch((error) => {
      console.log(error);
    })
  };

  return (
    <div className="form-container">
      <form id='login-form' className="form" onSubmit={handleSubmit}>
        <h2>Login</h2>
        <div>
          <input required id="email" type="text" placeholder="Email" />
        </div>
        <div>
          <input required id="password" type="password" placeholder="Password" />
        </div>
        <button type="submit">Login</button>
      </form>
    </div>
  );
};
  export default SignIn;
  
  