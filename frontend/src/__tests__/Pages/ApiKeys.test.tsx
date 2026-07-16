// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, act, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import ApiKeys from '../../Pages/ApiKeys';

// Mock the apiKeys service so the page can render without a backend.
vi.mock('../../Services/apiKeys', () => ({
  listApiKeys: vi.fn(() =>
    Promise.resolve([
      {
        id: 'k1',
        user_id: 'u1',
        name: 'ci-pipeline',
        key_prefix: 'smk_abcd1234',
        is_active: true,
        created_at: '2026-06-28T00:00:00Z',
      },
    ]),
  ),
  createApiKey: vi.fn(),
  getApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
}));

const ApiKeysWithRouter = () => (
  <BrowserRouter>
    <ApiKeys />
  </BrowserRouter>
);

describe('ApiKeys Page', () => {
  test('renders the heading and loads keys', async () => {
    await act(async () => {
      render(<ApiKeysWithRouter />);
    });
    // The i18n fallback text is used in tests (no i18n provider configured).
    await waitFor(() => {
      expect(screen.getAllByText('API Keys').length).toBeGreaterThan(0);
    });
  });
});
