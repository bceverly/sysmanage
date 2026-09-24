// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The email "Test Configuration" button, moved into Settings -> Configuration.
 * It sat in EmailConfigCard, which nothing rendered once email settings left
 * sysmanage.yaml -- so email could not be tested from the UI at all.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SendTestEmailButton from '../SendTestEmailButton';
import { emailService } from '../../Services/emailService';

vi.mock('react-i18next', () => {
  const t = (key: string, opts?: unknown) => (typeof opts === 'string' ? opts : key);
  return { useTranslation: () => ({ t }) };
});

vi.mock('../../Services/emailService', () => ({
  emailService: { sendTestEmail: vi.fn(), getConfig: vi.fn() },
}));

const send = emailService.sendTestEmail as unknown as ReturnType<typeof vi.fn>;

async function openAndSend(address: string) {
  const user = userEvent.setup();
  render(<SendTestEmailButton />);
  await user.click(screen.getByRole('button', { name: 'Test Configuration' }));
  await user.type(screen.getByLabelText('Email Address'), address);
  await user.click(screen.getByRole('button', { name: 'Send Test Email' }));
}

describe('SendTestEmailButton', () => {
  beforeEach(() => {
    send.mockReset();
  });

  it('sends to the address typed and shows the server result', async () => {
    send.mockResolvedValue({ success: true, message: 'Test email sent' });
    await openAndSend('ops@example.com');
    expect(send).toHaveBeenCalledWith('ops@example.com');
    expect(await screen.findByText('Test email sent')).toBeInTheDocument();
  });

  it('shows what the server says went wrong', async () => {
    send.mockResolvedValue({ success: false, message: 'Email service is disabled' });
    await openAndSend('ops@example.com');
    expect(await screen.findByText('Email service is disabled')).toBeInTheDocument();
  });

  it('reports a failed request instead of failing silently', async () => {
    send.mockRejectedValue(new Error('network'));
    await openAndSend('ops@example.com');
    await waitFor(() =>
      expect(
        screen.getByText('Failed to send test email. Please check your configuration.'),
      ).toBeInTheDocument(),
    );
  });

  it('cannot send without an address', async () => {
    const user = userEvent.setup();
    render(<SendTestEmailButton />);
    await user.click(screen.getByRole('button', { name: 'Test Configuration' }));
    expect(screen.getByRole('button', { name: 'Send Test Email' })).toBeDisabled();
  });
});
