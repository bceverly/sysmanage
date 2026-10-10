// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, act } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router';
import { vi } from 'vitest';
import Login from '../../Pages/Login';
import api from '../../Services/api';
import { discoverLoginMethods } from '../../Services/sso';

vi.mock('../../Services/api', () => ({ default: { post: vi.fn() } }));
vi.mock('../../Services/sso', () => ({ discoverLoginMethods: vi.fn() }));
vi.mock('../../utils/cookieUtils', () => ({
  saveRememberedEmail: vi.fn(),
  getRememberedEmail: vi.fn(),
  clearRememberedEmail: vi.fn(),
}));
vi.mock('../../Services/permissions', () => ({ clearPermissionsCache: vi.fn() }));

import {
  saveRememberedEmail,
  getRememberedEmail,
  clearRememberedEmail,
} from '../../utils/cookieUtils';
import { clearPermissionsCache } from '../../Services/permissions';

const renderLogin = async () => {
  await act(async () => {
    render(<BrowserRouter><Login /></BrowserRouter>);
  });
};

const enterEmail = async (email: string) => {
  fireEvent.change(screen.getByLabelText(/email/i), { target: { value: email } });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  });
};

const okta = { id: 'p1', name: 'Okta', type: 'oidc' as const, start_url: '/api/auth/oidc/p1/start' };

describe('Login page (email first, then password or single sign-on)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('step one asks only for the email', async () => {
    await renderLogin();
    expect(screen.getByText('Login to SysManage')).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  test('step two offers the password and the domain\'s providers', async () => {
    vi.mocked(discoverLoginMethods).mockResolvedValue({ password: true, providers: [okta] });
    await renderLogin();
    await enterEmail('bryan@acme.com');
    expect(discoverLoginMethods).toHaveBeenCalledWith('bryan@acme.com');
    expect(screen.getByTestId('login-identity')).toHaveTextContent('bryan@acme.com');
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in with Okta' })).toBeInTheDocument();
  });

  test('"use a different email" returns to step one', async () => {
    vi.mocked(discoverLoginMethods).mockResolvedValue({ password: true, providers: [] });
    await renderLogin();
    await enterEmail('bryan@acme.com');
    fireEvent.click(screen.getByRole('button', { name: 'Use a different email' }));
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toHaveValue('bryan@acme.com');
  });

  test('a failed lookup still offers the password', async () => {
    vi.mocked(discoverLoginMethods).mockRejectedValue(new Error('500'));
    await renderLogin();
    await enterEmail('bryan@acme.com');
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  test('the password step logs in as before', async () => {
    vi.mocked(discoverLoginMethods).mockResolvedValue({ password: true, providers: [] });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    await renderLogin();
    await enterEmail('bryan@acme.com');
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /login/i }));
    });
    expect(api.post).toHaveBeenCalledWith('/api/v1/login', { userid: 'bryan@acme.com', password: 'secret' });
  });
});

// The rest drive the password / MFA flow end to end.  MemoryRouter keeps the
// router off window.location so the post-login reload can be stubbed.
describe('Login page (password and two-factor flow)', () => {
  let reload: ReturnType<typeof vi.fn>;

  const renderMemory = async () => {
    await act(async () => {
      render(<MemoryRouter><Login /></MemoryRouter>);
    });
  };

  const toPasswordStep = async (email = 'bryan@acme.com') => {
    await renderMemory();
    await enterEmail(email);
  };

  const submitPassword = async (password = 'secret') => {
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: password } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /login/i }));
    });
  };

  const submitCode = async (code: string) => {
    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: code } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
    });
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    reload = vi.fn();
    vi.stubGlobal('location', { reload });
    vi.mocked(discoverLoginMethods).mockResolvedValue({ password: true, providers: [] });
    vi.mocked(getRememberedEmail).mockReturnValue(null as never);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test('a successful login stores the token, forgets the email and reloads', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { Authorization: 'h.tok-1.s' } });
    await toPasswordStep();
    await submitPassword();
    expect(clearPermissionsCache).toHaveBeenCalled();
    expect(localStorage.getItem('userid')).toBe('bryan@acme.com');
    expect(localStorage.getItem('bearer_token')).toBe('h.tok-1.s');
    expect(clearRememberedEmail).toHaveBeenCalled();
    expect(saveRememberedEmail).not.toHaveBeenCalled();
    expect(reload).toHaveBeenCalled();
  });

  test('a remembered email is prefilled and saved again after login', async () => {
    vi.mocked(getRememberedEmail).mockReturnValue('kept@acme.com' as never);
    vi.mocked(api.post).mockResolvedValue({ data: { Authorization: 'h.tok-2.s' } });
    await renderMemory();
    expect(screen.getByLabelText(/email/i)).toHaveValue('kept@acme.com');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    });
    expect(screen.getByRole('checkbox')).toBeChecked();
    await submitPassword();
    expect(saveRememberedEmail).toHaveBeenCalledWith('kept@acme.com');
  });

  test('ticking remember me saves the email', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { Authorization: 'h.tok-3.s' } });
    await toPasswordStep();
    fireEvent.click(screen.getByRole('checkbox'));
    await submitPassword();
    expect(saveRememberedEmail).toHaveBeenCalledWith('bryan@acme.com');
  });

  test('an empty password does not call the server', async () => {
    await toPasswordStep();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /login/i }));
    });
    expect(api.post).not.toHaveBeenCalled();
  });

  test('a rejected login clears stored credentials and re-enables the form', async () => {
    localStorage.setItem('userid', 'old');
    localStorage.setItem('bearer_token', 'old-token');
    vi.mocked(api.post).mockRejectedValue(new Error('401'));
    await toPasswordStep();
    await submitPassword();
    expect(localStorage.getItem('userid')).toBeNull();
    expect(localStorage.getItem('bearer_token')).toBeNull();
    expect(screen.getByRole('button', { name: /login/i })).toBeEnabled();
    expect(reload).not.toHaveBeenCalled();
  });

  test('a password-less provider list shows no password form', async () => {
    vi.mocked(discoverLoginMethods).mockResolvedValue({ password: false, providers: [okta] });
    await toPasswordStep();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in with Okta' })).toBeInTheDocument();
  });

  test('forgot password opens the reset dialog', async () => {
    await toPasswordStep();
    fireEvent.click(screen.getByRole('button', { name: 'Forgot password?' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  describe('two-factor challenge', () => {
    const toChallenge = async () => {
      vi.mocked(api.post).mockResolvedValueOnce({
        data: { mfa_required: true, pending_token: 'pend-1' },
      });
      await toPasswordStep();
      await submitPassword();
    };

    test('switches to the challenge and completes with a valid code', async () => {
      await toChallenge();
      expect(screen.getByText('Two-Factor Authentication')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Verify' })).toBeDisabled();
      vi.mocked(api.post).mockResolvedValueOnce({ data: { Authorization: 'h.tok-mfa.s' } });
      await submitCode(' 123456 ');
      expect(api.post).toHaveBeenLastCalledWith('/api/v1/auth/mfa/verify', {
        pending_token: 'pend-1',
        code: '123456',
      });
      expect(localStorage.getItem('bearer_token')).toBe('h.tok-mfa.s');
      expect(reload).toHaveBeenCalled();
    });

    test('a verify response without a token does nothing', async () => {
      await toChallenge();
      vi.mocked(api.post).mockResolvedValueOnce({ data: {} });
      await submitCode('123456');
      expect(localStorage.getItem('bearer_token')).toBeNull();
      expect(screen.getByText('Two-Factor Authentication')).toBeInTheDocument();
    });

    test('a wrong code lets the user retry', async () => {
      await toChallenge();
      vi.mocked(api.post).mockRejectedValueOnce({
        response: { status: 401, data: { detail: 'Invalid code' } },
      });
      await submitCode('000000');
      expect(
        screen.getByText('Invalid code. Try again or use a backup code.'),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Verify' })).toBeEnabled();
    });

    test('a 401 without detail is treated as a wrong code', async () => {
      await toChallenge();
      vi.mocked(api.post).mockRejectedValueOnce({ response: { status: 401 } });
      await submitCode('000000');
      expect(
        screen.getByText('Invalid code. Try again or use a backup code.'),
      ).toBeInTheDocument();
    });

    test('an expired challenge returns to the password step', async () => {
      await toChallenge();
      vi.mocked(api.post).mockRejectedValueOnce({
        response: { status: 401, data: { detail: 'Pending token EXPIRED' } },
      });
      await submitCode('123456');
      expect(screen.queryByText('Two-Factor Authentication')).not.toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });

    test('other failures show a generic error', async () => {
      await toChallenge();
      vi.mocked(api.post).mockRejectedValueOnce(new Error('network'));
      await submitCode('123456');
      expect(
        screen.getByText('Verification failed. Please try again.'),
      ).toBeInTheDocument();
    });

    test('submitting a blank code is ignored', async () => {
      await toChallenge();
      vi.mocked(api.post).mockClear();
      fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: '   ' } });
      await act(async () => {
        fireEvent.submit(screen.getByLabelText(/verification code/i).closest('form') as HTMLFormElement);
      });
      expect(api.post).not.toHaveBeenCalled();
    });

    test('cancel returns to the password step', async () => {
      await toChallenge();
      fireEvent.click(screen.getByRole('button', { name: 'Cancel and sign in again' }));
      expect(screen.queryByText('Two-Factor Authentication')).not.toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });
  });
});
