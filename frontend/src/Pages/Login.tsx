import { useState } from "react";
import { useNavigate } from "react-router-dom";

import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Link from "@mui/material/Link";
import Grid from "@mui/material/Grid";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Container from "@mui/material/Container";

import api from "../Services/api"

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
        .then((response: { data: { Authorization: any; }; }) => {
          if (response.data.Authorization) {
            localStorage.setItem("userid", input.userid);
            localStorage.setItem("bearer_token", response.data.Authorization);
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
    <Container component="main" maxWidth="sm">
      <Box
        sx={{
          boxShadow: 3,
          borderRadius: 2,
          px: 4,
          py: 6,
          marginTop: 8,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        <Typography component="h1" variant="h5">
          Log in
        </Typography>
        <Box component="form" onSubmit={handleSubmitEvent} noValidate sx={{ mt: 1 }}>
          <TextField
            margin="normal"
            required
            fullWidth
            id="userid"
            label="Email Address"
            name="userid"
            autoComplete="email"
            autoFocus
            onChange={handleInput}
          />
          <TextField
            margin="normal"
            required
            fullWidth
            name="password"
            label="Password"
            type="password"
            id="password"
            autoComplete="current-password"
            onChange={handleInput}
          />
          <FormControlLabel
            control={<Checkbox value="remember" color="primary" />}
            label="Remember me"
          />
          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2 }}
          >
            Log In
          </Button>
          <Grid container>
            <Grid item xs>
              <Link href="#" variant="body2">
                Forgot password?
              </Link>
            </Grid>
            <Grid item>
              <Link href="#" variant="body2">
                {"Don't have an account? Sign Up"}
              </Link>
            </Grid>
          </Grid>
        </Box>
      </Box>
    </Container>  );
};

export default Login;