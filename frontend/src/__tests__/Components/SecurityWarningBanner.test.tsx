// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The default-admin banner lists only the steps this server still needs.
 * Written after a fresh Ubuntu 24.04 install (2026-11-05): the package had
 * already generated jwt_secret and password_salt, and the banner still told
 * the operator to change both.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SecurityWarningBanner from '../../Components/SecurityWarningBanner';
import api from '../../Services/api';

vi.mock('react-i18next', () => {
  const t = (key: string, opts?: unknown) => (typeof opts === 'string' ? opts : key);
  return { useTranslation: () => ({ t }) };
});

vi.mock('../../Services/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const get = api.get as unknown as ReturnType<typeof vi.fn>;
const post = api.post as unknown as ReturnType<typeof vi.fn>;

function status(defaults: { jwt: boolean; salt: boolean; first?: boolean }) {
  get.mockResolvedValue({
    data: {
      hasDefaultCredentials: true,
      isLoggedInAsDefault: true,
      defaultUserId: 'admin@example.com',
      securityWarnings: [],
      hasDefaultJwtSecret: defaults.jwt,
      hasDefaultPasswordSalt: defaults.salt,
      jwtCommand: 'migrate --jwt-only',
      saltCommand: 'migrate --salt-only',
      restartCommand: 'systemctl restart sysmanage',
      needsFirstAdmin: defaults.first ?? false,
    },
  });
}

describe('SecurityWarningBanner', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    localStorage.setItem('bearer_token', 'token');
    localStorage.setItem('userid', 'admin@example.com');
  });

  it('leaves out the secret steps when the installer already generated them', async () => {
    status({ jwt: false, salt: false });
    render(<SecurityWarningBanner />);
    expect(await screen.findByText(/Create a new admin user/)).toBeInTheDocument();
    expect(screen.queryByText(/Change JWT secret/)).toBeNull();
    expect(screen.queryByText(/Change password salt/)).toBeNull();
    // The remaining steps are numbered from 1.
    expect(screen.getByText(/^1\. Create a new admin user/)).toBeInTheDocument();
  });

  it('asks for the secret steps while they still hold shipped defaults', async () => {
    status({ jwt: true, salt: true });
    render(<SecurityWarningBanner />);
    expect(await screen.findByText(/Change JWT secret/)).toBeInTheDocument();
    expect(screen.getByText(/Change password salt/)).toBeInTheDocument();
    expect(screen.getByText(/^3\. Create a new admin user/)).toBeInTheDocument();
  });

  it('offers to create the first administrator while none exists', async () => {
    status({ jwt: false, salt: false, first: true });
    post.mockResolvedValue({ data: { id: 'x', userid: 'ops@example.com', roles: 108 } });
    const user = userEvent.setup();
    render(<SecurityWarningBanner />);
    await user.click(await screen.findByRole('button', { name: 'Create your administrator' }));
    await user.type(screen.getByLabelText(/Email address/), 'ops@example.com');
    await user.type(screen.getByLabelText(/^Password/), 'Correct-Horse-9-Battery');
    await user.type(screen.getByLabelText(/Confirm password/), 'Correct-Horse-9-Battery');
    await user.click(screen.getByRole('button', { name: 'Create administrator' }));
    expect(post).toHaveBeenCalledWith('/api/v1/security/first-admin', expect.objectContaining({
      userid: 'ops@example.com',
      password: 'Correct-Horse-9-Battery',
      confirm_password: 'Correct-Horse-9-Battery',
    }));
    expect(await screen.findByRole('button', { name: 'Sign out' })).toBeInTheDocument();
  });

  it('does not offer it once an administrator exists', async () => {
    status({ jwt: false, salt: false, first: false });
    render(<SecurityWarningBanner />);
    expect(await screen.findByText(/Create a new admin user/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create your administrator' })).toBeNull();
  });
});
