import styles from './styles/login.css'

const SignIn = () => {
  const handleSubmit = (event) => {
    event.preventDefault();

    const email = event.target.elements.email.value;
    const password = event.target.elements.password.value;
    
    fetch('https://api.sysmanage.org:8443/login', {
      method: 'POST',
      body: JSON.stringify({
        "userid": email,
        "password": password
      }),
      headers: {
        'Content-type': 'application/json; charset=UTF-8',
      },
    })
       .then((response) => response.json())
       .then((data) => {
          console.log(data);
          // Handle data
       })
       .catch((err) => {
          console.log(err.message);
       });
  };

  return (
    <div className={styles["form-container"]}>
      <form id='login-form' className={styles["form"]} onSubmit={handleSubmit}>
        <div>
          <input id="email" type="text" placeholder="Email" />
        </div>
        <div>
          <input id="password" type="password" placeholder="Password" />
        </div>
        <button type="submit">Login</button>
      </form>
    </div>
  );
};
  export default SignIn;
  
  