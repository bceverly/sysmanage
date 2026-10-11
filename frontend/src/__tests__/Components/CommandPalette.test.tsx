// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import CommandPalette from '../../Components/CommandPalette';

// Hoisted mutable test state so the vi.mock factories can read it safely.
const h = vi.hoisted(() => ({
  navigate: vi.fn(),
  license: null as null | { active: boolean; modules: string[]; features: string[] },
  perms: {} as Record<string, boolean>,
  getHosts: vi.fn(),
}));

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>();
  return { ...actual, useNavigate: () => h.navigate };
});
vi.mock('../../Services/license', () => ({
  getCachedLicense: () => h.license,
}));
vi.mock('../../Services/permissions', () => ({
  hasPermissionSync: (name: string) => !!h.perms[name],
}));
vi.mock('../../Services/hosts', () => ({
  doGetHosts: () => h.getHosts(),
}));

const renderPalette = () =>
  render(
    <BrowserRouter>
      <CommandPalette />
    </BrowserRouter>,
  );

const dispatchOpen = () =>
  act(() => {
    window.dispatchEvent(new window.Event('open-command-palette'));
  });

const ctrlK = () =>
  act(() => {
    window.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'k', ctrlKey: true }));
  });

const input = () => screen.getByPlaceholderText(/Search pages/i);

// Typing can start the lazy host fetch; let it settle inside act().
const typeQuery = async (value: string) => {
  await act(async () => {
    fireEvent.change(input(), { target: { value } });
  });
};

describe('CommandPalette', () => {
  beforeEach(() => {
    h.navigate.mockClear();
    h.license = {
      active: true,
      modules: ['observability_engine', 'secrets_engine', 'reporting_engine'],
      features: ['reports', 'advisory_management', 'vuln', 'compliance', 'fips_mode', 'alerts', 'os_lifecycle', 'health'],
    };
    h.perms = { 'Manage Custom Metrics': true };
    h.getHosts.mockReset();
    h.getHosts.mockResolvedValue([]);
    localStorage.setItem('bearer_token', 'tok');
  });
  afterEach(() => localStorage.removeItem('bearer_token'));

  it('renders nothing until opened', () => {
    renderPalette();
    expect(screen.queryByPlaceholderText(/Search pages/i)).toBeNull();
  });

  it('opens on the open-command-palette event when authenticated', () => {
    renderPalette();
    dispatchOpen();
    expect(input()).toBeInTheDocument();
    expect(screen.getByText('Hosts')).toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it('does not open when unauthenticated', () => {
    localStorage.removeItem('bearer_token');
    renderPalette();
    dispatchOpen();
    expect(screen.queryByPlaceholderText(/Search pages/i)).toBeNull();
  });

  it('opens on Ctrl+K and toggles closed on a second Ctrl+K', async () => {
    renderPalette();
    ctrlK();
    expect(input()).toBeInTheDocument();
    ctrlK();
    // MUI Dialog fades out on close -- wait for the exit transition.
    await waitFor(() =>
      expect(screen.queryByPlaceholderText(/Search pages/i)).toBeNull(),
    );
  });

  it('filters commands by query', async () => {
    renderPalette();
    dispatchOpen();
    await typeQuery('host');
    expect(screen.getByText('Hosts')).toBeInTheDocument();
    expect(screen.queryByText('Settings')).toBeNull();
  });

  it('shows a no-matches message for a non-matching query', async () => {
    renderPalette();
    dispatchOpen();
    await typeQuery('zzznotathing');
    expect(screen.getByText(/No matches/i)).toBeInTheDocument();
  });

  it('shows a module-gated destination when its module is licensed', () => {
    renderPalette();
    dispatchOpen();
    expect(screen.getByText('Secrets')).toBeInTheDocument();
    expect(screen.getByText('Reports')).toBeInTheDocument();
  });

  it('hides module-gated destinations when the module is unlicensed', () => {
    h.license = { active: true, modules: [], features: [] };
    renderPalette();
    dispatchOpen();
    expect(screen.queryByText('Secrets')).toBeNull();
    expect(screen.queryByText('Reports')).toBeNull();
    expect(screen.getByText('Hosts')).toBeInTheDocument(); // ungated still present
  });

  it('hides Custom Metrics without the Manage Custom Metrics permission', () => {
    h.perms = { 'Manage Custom Metrics': false };
    renderPalette();
    dispatchOpen();
    expect(screen.queryByText('Custom Metrics')).toBeNull();
  });

  it('shows Custom Metrics when the permission is held', () => {
    renderPalette();
    dispatchOpen();
    expect(screen.getByText('Custom Metrics')).toBeInTheDocument();
  });

  it('handles a null license (nothing gated by module shows)', () => {
    h.license = null;
    renderPalette();
    dispatchOpen();
    expect(screen.getByText('Hosts')).toBeInTheDocument();
    expect(screen.queryByText('Secrets')).toBeNull();
  });

  it('navigates and closes on Enter', async () => {
    renderPalette();
    dispatchOpen();
    await typeQuery('hosts');
    act(() => { fireEvent.keyDown(input(), { key: 'Enter' }); });
    expect(h.navigate).toHaveBeenCalledWith('/hosts');
    await waitFor(() =>
      expect(screen.queryByPlaceholderText(/Search pages/i)).toBeNull(),
    );
  });

  it('navigates on click', () => {
    renderPalette();
    dispatchOpen();
    act(() => { fireEvent.click(screen.getByText('Dashboard')); });
    expect(h.navigate).toHaveBeenCalledWith('/');
  });

  it('ArrowUp/ArrowDown adjust the active row without crashing', () => {
    renderPalette();
    dispatchOpen();
    act(() => { fireEvent.keyDown(input(), { key: 'ArrowDown' }); });
    act(() => { fireEvent.keyDown(input(), { key: 'ArrowUp' }); });
    act(() => { fireEvent.keyDown(input(), { key: 'Enter' }); });
    expect(h.navigate).toHaveBeenCalled();
  });

  describe('asset tag search', () => {
    const hosts = [
      { id: 'h1', fqdn: 'linux.example.com', asset_tag: 'GDR-000042', machine_id: 'm1' },
      { id: 'h2', fqdn: 'windows.example.com', asset_tag: 'GDR-000042', machine_id: 'm1' },
      { id: 'h3', fqdn: 'other.example.com', asset_tag: 'GDR-000043', machine_id: 'm2' },
      { id: 'h4', fqdn: 'untagged.example.com', asset_tag: null, machine_id: null },
    ];

    beforeEach(() => {
      h.getHosts.mockResolvedValue(hosts);
    });

    it('finds every host on the tagged machine and shows the tag', async () => {
      renderPalette();
      dispatchOpen();
      await typeQuery('GDR-000042');
      expect(await screen.findByText('linux.example.com')).toBeInTheDocument();
      expect(screen.getByText('windows.example.com')).toBeInTheDocument();
      expect(screen.queryByText('other.example.com')).toBeNull();
      expect(screen.queryByText('untagged.example.com')).toBeNull();
      expect(screen.getAllByText('Asset tag: GDR-000042')).toHaveLength(2);
    });

    it('matches case-insensitively on a partial tag', async () => {
      renderPalette();
      dispatchOpen();
      await typeQuery('gdr-0000');
      expect(await screen.findByText('other.example.com')).toBeInTheDocument();
      expect(screen.getByText('Asset tag: GDR-000043')).toBeInTheDocument();
    });

    it('navigates to the host on click', async () => {
      renderPalette();
      dispatchOpen();
      await typeQuery('GDR-000043');
      act(() => { fireEvent.click(screen.getByText('other.example.com')); });
      expect(h.navigate).toHaveBeenCalledWith('/hosts/h3');
    });

    it('fetches hosts once per opening and not for a one-letter query', async () => {
      renderPalette();
      dispatchOpen();
      await typeQuery('g');
      expect(h.getHosts).not.toHaveBeenCalled();
      await typeQuery('gd');
      await typeQuery('gdr');
      expect(h.getHosts).toHaveBeenCalledTimes(1);
    });

    it('still lists pages when the host fetch fails', async () => {
      const errSpy = vi.spyOn(globalThis.console, 'error').mockImplementation(() => {});
      h.getHosts.mockRejectedValue(new Error('boom'));
      renderPalette();
      dispatchOpen();
      await typeQuery('hosts');
      expect(screen.getByText('Hosts')).toBeInTheDocument();
      expect(errSpy).toHaveBeenCalled();
      errSpy.mockRestore();
    });
  });
});
