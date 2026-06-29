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
import Alert from "@mui/material/Alert";

import api from "../Services/api"
import LanguageSelector from "../Components/LanguageSelector"
import ForgotPasswordDialog from "../Components/ForgotPasswordDialog"
import { saveRememberedEmail, getRememberedEmail, clearRememberedEmail } from "../utils/cookieUtils"
import { clearPermissionsCache } from "../Services/permissions"

interface LoginResponse {
  Authorization?: string;
  mfa_required?: boolean;
  pending_token?: string;
}

const Login = () => {
    const [input, setInput] = useState({
      userid: "",
      password: "",
    });
    const [rememberMe, setRememberMe] = useState(false);
    const [forgotPasswordOpen, setForgotPasswordOpen] = useState(false);
    const [isLoggingIn, setIsLoggingIn] = useState(false);
    // Phase 10.3 — MFA challenge state.  When the password login succeeds
    // but the user has a second factor, the server returns
    // ``{mfa_required: true, pending_token: "..."}``.  We store the
    // pending token + user id and swap the form into the challenge view;
    // /api/auth/mfa/verify exchanges the pending token + TOTP code for a
    // real session token.
    const [mfaPendingToken, setMfaPendingToken] = useState<string | null>(null);
    const [mfaCode, setMfaCode] = useState("");
    const [mfaError, setMfaError] = useState<string | null>(null);
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

    const finishLogin = (token: string) => {
      // Clear permissions cache before setting new credentials
      clearPermissionsCache();
      localStorage.setItem("userid", input.userid);
      localStorage.setItem("bearer_token", token);
      if (rememberMe) {
        saveRememberedEmail(input.userid);
      } else {
        clearRememberedEmail();
      }
      navigate("/");
      globalThis.location.reload();
    };

    const handleSubmitEvent = (e: { preventDefault: () => void; }) => {
      e.preventDefault();
      if (input.userid !== "" && input.password !== "") {
        setIsLoggingIn(true);
        api.post<LoginResponse>("/api/v1/login", {
          userid: input.userid,
          password: input.password
        })
        .then((response) => {
          if (response.data.mfa_required && response.data.pending_token) {
            // Step 2 of login: ask for TOTP / backup code.
            setMfaPendingToken(response.data.pending_token);
            setIsLoggingIn(false);
            return;
          }
          if (response.data.Authorization) {
            finishLogin(response.data.Authorization);
          }
        })
        .catch(() => {
          // Error situation - clear out storage
          localStorage.removeItem("userid");
          localStorage.removeItem("bearer_token");
          setIsLoggingIn(false);
        });
      }
    };

    const handleMfaSubmit = (e: { preventDefault: () => void }) => {
      e.preventDefault();
      if (!mfaPendingToken || mfaCode.trim() === "") return;
      setIsLoggingIn(true);
      setMfaError(null);
      api.post<LoginResponse>("/api/auth/mfa/verify", {
        pending_token: mfaPendingToken,
        code: mfaCode.trim(),
      })
        .then((response) => {
          if (response.data.Authorization) {
            finishLogin(response.data.Authorization);
          }
        })
        .catch((err) => {
          const status = err?.response?.status;
          if (status === 401) {
            // 401 from /verify means either the pending token expired
            // (kick user back to password step) or the TOTP / backup
            // code was wrong (let them retry).
            const detail = err?.response?.data?.detail || "";
            if (detail.toLowerCase().includes("expired")) {
              setMfaPendingToken(null);
              setMfaCode("");
              setMfaError(t('login.mfaExpired', 'Challenge expired — please log in again.'));
            } else {
              setMfaError(t('login.mfaInvalidCode', 'Invalid code. Try again or use a backup code.'));
            }
          } else {
            setMfaError(t('login.mfaError', 'Verification failed. Please try again.'));
          }
          setIsLoggingIn(false);
        });
    };

    const handleInput = (e: { target: { name: string; value: string; }; }) => {
      const { name, value } = e.target;
      setInput((prev) => ({
        ...prev,
        [name]: value,
      }));
    };

  // ------------------------------------------------------------------
  // MFA challenge view — shown when the password step returned an
  // mfa_required response.  Rendered in place of the login form so the
  // user has nowhere to navigate until they finish the second factor.
  // ------------------------------------------------------------------
  if (mfaPendingToken) {
    return (
      <>
        <Box sx={{ position: "fixed", top: 20, right: 20, zIndex: 1000 }}>
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
            <Typography component="h1" variant="h5" sx={{ mb: 1 }}>
              {t('login.mfaTitle', 'Two-Factor Authentication')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2, textAlign: 'center' }}>
              {t('login.mfaPrompt', 'Enter the 6-digit code from your authenticator app, or one of your backup codes.')}
            </Typography>
            {mfaError && (
              <Alert severity="error" sx={{ width: '100%', mb: 2 }}>
                {mfaError}
              </Alert>
            )}
            <Box component="form" onSubmit={handleMfaSubmit} noValidate sx={{ mt: 1, width: '100%' }}>
              <TextField
                margin="normal"
                required
                fullWidth
                id="mfa-code"
                label={t('login.mfaCode', 'Verification code')}
                name="mfa-code"
                value={mfaCode}
                autoComplete="one-time-code"
                autoFocus
                slotProps={{ htmlInput: { inputMode: 'text', autoCapitalize: 'characters' } }}
                onChange={(e) => setMfaCode(e.target.value)}
              />
              <Button
                type="submit"
                fullWidth
                variant="contained"
                sx={{ mt: 3, mb: 2 }}
                disabled={isLoggingIn || mfaCode.trim() === ""}
                startIcon={isLoggingIn ? <CircularProgress size={20} color="inherit" /> : undefined}
              >
                {isLoggingIn ? t('login.verifying', 'Verifying...') : t('login.mfaVerify', 'Verify')}
              </Button>
              <Box sx={{ textAlign: 'center', mt: 2 }}>
                <Link
                  component="button"
                  variant="body2"
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    setMfaPendingToken(null);
                    setMfaCode("");
                    setMfaError(null);
                  }}
                >
                  {t('login.mfaCancel', 'Cancel and sign in again')}
                </Link>
              </Box>
            </Box>
          </Box>
        </Container>
      </>
    );
  }

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
