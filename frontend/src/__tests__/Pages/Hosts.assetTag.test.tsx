// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { render, screen, fireEvent, within, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, beforeEach, describe, it, expect } from 'vitest';

// Stable t (see FederationHosts.test.tsx for why it must not change per render).
vi.mock('react-i18next', () => {
  const t = (key: string, fallback?: unknown) => (typeof fallback === 'string' ? fallback : key);
  const value = { t, i18n: { language: 'en' } };
  return { useTranslation: () => value };
});

const h = vi.hoisted(() => ({ hosts: [] as Array<Record<string, unknown>> }));

vi.mock('../../Services/hosts', () => ({
  doGetHosts: vi.fn(() => Promise.resolve(h.hosts)),
  doDeleteHost: vi.fn(),
  doApproveHost: vi.fn(),
  doRefreshAllHostData: vi.fn(),
  doRebootHost: vi.fn(),
  doShutdownHost: vi.fn(),
  doUpdateAgent: vi.fn(),
  doRequestHostDiagnostics: vi.fn(),
}));
vi.mock('../../Services/opentelemetry', () => ({ doDeployOpenTelemetry: vi.fn() }));
vi.mock('../../Services/license', () => ({
  getLicenseInfo: vi.fn(() => Promise.resolve({ modules: [] })),
}));
vi.mock('../../Services/permissions', () => ({
  hasPermission: vi.fn(() => Promise.resolve(true)),
  SecurityRoles: {},
}));
vi.mock('../../Services/broadcast', () => ({ broadcastService: { send: vi.fn() } }));
vi.mock('../../Services/api', () => ({
  default: { get: vi.fn(() => Promise.resolve({ data: [] })), post: vi.fn() },
}));
vi.mock('../../Services/columnPreferencesService', () => ({
  getColumnPreferences: vi.fn(() => Promise.resolve(null)),
  updateColumnPreferences: vi.fn(),
  deleteColumnPreferences: vi.fn(),
}));
vi.mock('../../hooks/useVisiblePolling', () => ({ useVisiblePolling: () => {} }));
vi.mock('../../Components/HostsActionBar', () => ({ default: () => null }));
vi.mock('../../Components/ColumnVisibilityButton', () => ({
  default: ({ columns }: { columns: Array<{ field: string; headerName: string }> }) => (
    <div data-testid="column-chooser">{columns.map(c => c.headerName).join('|')}</div>
  ),
}));

type MockCol = {
  field: string;
  valueGetter?: (_v: unknown, _r: Record<string, unknown>) => unknown;
  renderCell?: (_p: { row: Record<string, unknown>; value: unknown }) => React.ReactNode;
};
vi.mock('@mui/x-data-grid', () => ({
  DataGrid: ({ rows, columns }: { rows: Array<Record<string, unknown>>; columns: MockCol[] }) => (
    <div data-testid="grid">
      {rows.map(r => (
        <div key={String(r.id)} data-testid={`row-${String(r.id)}`}>
          {columns
            .filter(c => c.field === 'fqdn' || c.field === 'asset_tag')
            .map(c => {
              const value = c.valueGetter ? c.valueGetter(r[c.field], r) : r[c.field];
              return (
                <span key={c.field} data-testid={`${String(r.id)}-${c.field}`}>
                  {c.renderCell ? c.renderCell({ row: r, value }) : String(value ?? '')}
                </span>
              );
            })}
        </div>
      ))}
    </div>
  ),
}));

import Hosts from '../../Pages/Hosts';

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <Hosts />
      </MemoryRouter>,
    );
  });
};

const rowIds = () =>
  within(screen.getByTestId('grid'))
    .queryAllByTestId(/^row-/)
    .map(el => el.dataset.testid?.replace('row-', ''));

describe('Hosts grid asset tags', () => {
  beforeEach(() => {
    localStorage.setItem('bearer_token', 'tok');
    h.hosts = [
      { id: 'h1', fqdn: 'linux.example.com', asset_tag: 'GDR-000042', machine_id: 'm1', tags: [] },
      { id: 'h2', fqdn: 'windows.example.com', asset_tag: 'GDR-000042', machine_id: 'm1', tags: [] },
      { id: 'h3', fqdn: 'other.example.com', asset_tag: 'GDR-000043', machine_id: 'm2', tags: [] },
      { id: 'h4', fqdn: 'untagged.example.com', asset_tag: null, machine_id: null, tags: [] },
    ];
  });

  it('shows the tag in the Asset Tag column, the same on every OS of a machine', async () => {
    await renderPage();
    expect(screen.getByTestId('h1-asset_tag')).toHaveTextContent('GDR-000042');
    expect(screen.getByTestId('h2-asset_tag')).toHaveTextContent('GDR-000042');
    expect(screen.getByTestId('h4-asset_tag')).toHaveTextContent('-');
  });

  it('offers the column in the column chooser so it can be hidden', async () => {
    await renderPage();
    expect(screen.getByTestId('column-chooser').textContent).toContain('Asset Tag');
  });

  it('search box finds hosts by asset tag', async () => {
    await renderPage();
    // Pick "Asset Tag" in the search box's column selector.
    const columnSelect = screen
      .getAllByRole('combobox')
      .find(el => el.textContent === 'hosts.fqdn') as HTMLElement;
    fireEvent.mouseDown(columnSelect);
    fireEvent.click(await screen.findByRole('option', { name: 'Asset Tag' }));
    fireEvent.change(screen.getByLabelText('Search hosts'), { target: { value: 'gdr-000042' } });
    expect(rowIds()).toEqual(expect.arrayContaining(['h1', 'h2']));
    expect(rowIds()).toHaveLength(2);
  });

  it('untagged-only toggle keeps only hosts whose machine has no tag', async () => {
    await renderPage();
    expect(rowIds()).toHaveLength(4);
    fireEvent.click(screen.getByRole('switch', { name: 'Untagged only' }));
    expect(rowIds()).toEqual(['h4']);
    fireEvent.click(screen.getByRole('switch', { name: 'Untagged only' }));
    expect(rowIds()).toHaveLength(4);
  });
});
