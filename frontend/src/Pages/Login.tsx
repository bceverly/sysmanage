import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from 'react-i18next';

import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import InputAdornment from '@mui/material/InputAdornment';
import AccountCircle from '@mui/icons-material/AccountCircle';
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Link from "@mui/material/Link";
import Grid from "@mui/material/Grid";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Container from "@mui/material/Container";

import api from "../Services/api"
import LanguageSelector from "../Components/LanguageSelector"

const Login = () => {
    const [input, setInput] = useState({
      userid: "",
      password: "",
    });
    const navigate = useNavigate();
    const { t } = useTranslation();
    const handleSubmitEvent = (e: { preventDefault: () => void; }) => {
      e.preventDefault();
      if (input.userid !== "" && input.password !== "") {
        api.post("/login", {
          userid: input.userid,
          password: input.password
        })
        .then((response: { data: { Authorization: string; }; }) => {
          if (response.data.Authorization) {
            localStorage.setItem("userid", input.userid);
            localStorage.setItem("bearer_token", response.data.Authorization);
          }

          navigate("/");
          window.location.reload();
          return response.data;
        })
        .catch((_error) => {
          // Error situation - clear out storage
          localStorage.removeItem("userid");
          localStorage.removeItem("bearer_token");
          alert(t('login.error'));
        });
      }
    };

    const handleInput = (e: { target: { name: string; value: string; }; }) => {
      const { name, value } = e.target;
      setInput((prev) => ({
        ...prev,
        [name]: value,
      }));
    };

  return (
    <>
      <Box
        sx={{
          position: "fixed",
          top: 20,
          right: 20,
          zIndex: 1000,
        }}
      >
        <LanguageSelector theme="light" />
      </Box>
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
          <Typography component="h1" variant="h5" sx={{ mb: 2 }}>
            {t('login.title')}
          </Typography>
        <Box component="form" onSubmit={handleSubmitEvent} noValidate sx={{ mt: 1 }}>
          <TextField
            margin="normal"
            required
            fullWidth
            id="userid"
            label={t('login.username')}
            name="userid"
            autoComplete="email"
            autoFocus
            onChange={handleInput}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <AccountCircle />
                </InputAdornment>
              ),
            }}
          />
          <TextField
            margin="normal"
            required
            fullWidth
            name="password"
            label={t('login.password')}
            type="password"
            id="password"
            autoComplete="current-password"
            onChange={handleInput}
          />
          <FormControlLabel
            control={<Checkbox value="remember" color="primary" />}
            label={t('login.remember', { defaultValue: 'Remember me' })}
          />
          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2 }}
          >
            {t('login.submit')}
          </Button>
          <Grid container>
            <Grid item xs>
              <Link href="#" variant="body2">
                {t('login.forgotPassword', { defaultValue: 'Forgot password?' })}
              </Link>
            </Grid>
            <Grid item>
              <Link href="#" variant="body2">
                {t('login.signUp', { defaultValue: "Don't have an account? Sign Up" })}
              </Link>
            </Grid>
          </Grid>
        </Box>
      </Box>
    </Container>
    </>
  );
};

export default Login;