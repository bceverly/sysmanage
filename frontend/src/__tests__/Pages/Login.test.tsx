// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { vi } from 'vitest';
import Login from '../../Pages/Login';
import api from '../../Services/api';
import { discoverLoginMethods } from '../../Services/sso';

vi.mock('../../Services/api', () => ({ default: { post: vi.fn() } }));
vi.mock('../../Services/sso', () => ({ discoverLoginMethods: vi.fn() }));

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
