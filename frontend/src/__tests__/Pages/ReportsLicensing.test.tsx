// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The Automatic Updates report is the Enterprise automation_engine's
// (ROADMAP 26.7): reporting is Professional, so a Professional user is not
// offered a report that could only ever be empty.

import React from 'react';
import { describe, expect, test, vi, beforeEach, type Mock } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router';

vi.mock('../../Services/api', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback || key }),
}));
vi.mock('../../Services/license', async () => {
  const actual = await vi.importActual<typeof import('../../Services/license')>(
    '../../Services/license',
  );
  return { ...actual, refreshLicenseCache: vi.fn(), isModuleLicensed: vi.fn() };
});

import api from '../../Services/api';
import { isModuleLicensed, refreshLicenseCache } from '../../Services/license';
import { clearPermissionsCache } from '../../Services/permissions';
import Reports from '../../Pages/Reports';

const licensed = isModuleLicensed as Mock;

async function renderWith(modules: string[]) {
  licensed.mockImplementation((code: string) => modules.includes(code));
  await act(async () => {
    render(
      <BrowserRouter>
        <Reports />
      </BrowserRouter>,
    );
  });
}

describe('Reports licensing (26.7)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearPermissionsCache();
    window.location.hash = '';
    (refreshLicenseCache as Mock).mockResolvedValue({ licensed: true });
    (api.get as Mock).mockResolvedValue({
      data: { is_admin: true, permissions: { 'View Report': true, 'Generate PDF Report': true } },
    });
  });

  test('a Professional server is not offered the Automatic Updates report', async () => {
    await renderWith(['reporting_engine']);
    expect(screen.getByText('Registered Hosts')).toBeTruthy();
    expect(screen.queryByText('Automatic Updates')).toBeNull();
  });

  test('an Enterprise server is', async () => {
    await renderWith(['reporting_engine', 'automation_engine']);
    expect(await screen.findByText('Automatic Updates')).toBeTruthy();
  });
});
