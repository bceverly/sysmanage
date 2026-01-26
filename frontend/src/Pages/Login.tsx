import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from 'react-i18next';

import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import InputAdornment from '@mui/material/InputAdornment';
import AccountCircle from '@mui/icons-material/AccountCircle';
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Link from "@mui/material/Link";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Container from "@mui/material/Container";
import CircularProgress from "@mui/material/CircularProgress";

import api from "../Services/api"
import LanguageSelector from "../Components/LanguageSelector"
import ForgotPasswordDialog from "../Components/ForgotPasswordDialog"
import { saveRememberedEmail, getRememberedEmail, clearRememberedEmail } from "../utils/cookieUtils"
import { clearPermissionsCache } from "../Services/permissions"

const Login = () => {
    const [input, setInput] = useState({
      userid: "",
      password: "",
    });
    const [rememberMe, setRememberMe] = useState(false);
    const [forgotPasswordOpen, setForgotPasswordOpen] = useState(false);
    const [isLoggingIn, setIsLoggingIn] = useState(false);
    const navigate = useNavigate();
    const { t } = useTranslation();

    // Load remembered email on component mount
    useEffect(() => {
      const rememberedEmail = getRememberedEmail();
      if (rememberedEmail) {
        setInput(prev => ({ ...prev, userid: rememberedEmail }));
        setRememberMe(true);
      }
    }, []);

    const handleSubmitEvent = (e: { preventDefault: () => void; }) => {
      e.preventDefault();
      if (input.userid !== "" && input.password !== "") {
        setIsLoggingIn(true);
        api.post("/login", {
          userid: input.userid,
          password: input.password
        })
        .then((response: { data: { Authorization: string; }; }) => {
          if (response.data.Authorization) {
            // Clear permissions cache before setting new credentials
            clearPermissionsCache();

            localStorage.setItem("userid", input.userid);
            localStorage.setItem("bearer_token", response.data.Authorization);

            // Handle Remember Me functionality
            if (rememberMe) {
              saveRememberedEmail(input.userid);
            } else {
              clearRememberedEmail();
            }
          }

          navigate("/");
          globalThis.location.reload();
          return response.data;
        })
        .catch(() => {
          // Error situation - clear out storage
          localStorage.removeItem("userid");
          localStorage.removeItem("bearer_token");
          setIsLoggingIn(false);
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
            value={input.userid}
            autoComplete="email"
            autoFocus
            onChange={handleInput}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <AccountCircle />
                  </InputAdornment>
                ),
              },
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
            value={input.password}
            autoComplete="current-password"
            onChange={handleInput}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                color="primary"
              />
            }
            label={t('login.remember', { defaultValue: 'Remember me' })}
          />
          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2 }}
            disabled={isLoggingIn}
            startIcon={isLoggingIn ? <CircularProgress size={20} color="inherit" /> : undefined}
          >
            {isLoggingIn ? t('login.loggingIn', 'Logging in...') : t('login.submit')}
          </Button>
          <Box sx={{ textAlign: 'center', mt: 2 }}>
            <Link
              component="button"
              variant="body2"
              onClick={(e) => {
                e.preventDefault();
                setForgotPasswordOpen(true);
              }}
            >
              {t('login.forgotPassword', { defaultValue: 'Forgot password?' })}
            </Link>
          </Box>
        </Box>
      </Box>
    </Container>

    <ForgotPasswordDialog
      open={forgotPasswordOpen}
      onClose={() => setForgotPasswordOpen(false)}
    />
    </>
  );
};

export default Login;