// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import CommandPalette from '../../Components/CommandPalette';

// Hoisted mutable test state so the vi.mock factories can read it safely.
const h = vi.hoisted(() => ({
  navigate: vi.fn(),
  license: null as null | { active: boolean; modules: string[]; features: string[] },
  perms: {} as Record<string, boolean>,
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => h.navigate };
});
vi.mock('../../Services/license', () => ({
  getCachedLicense: () => h.license,
}));
vi.mock('../../Services/permissions', () => ({
  hasPermissionSync: (name: string) => !!h.perms[name],
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

describe('CommandPalette', () => {
  beforeEach(() => {
    h.navigate.mockClear();
    h.license = {
      active: true,
      modules: ['observability_engine', 'secrets_engine', 'reporting_engine'],
      features: ['reports', 'advisory_management', 'vuln', 'compliance', 'fips_mode', 'alerts', 'os_lifecycle', 'health'],
    };
    h.perms = { 'Manage Custom Metrics': true };
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
    // MUI Dialog fades out on close — wait for the exit transition.
    await waitFor(() =>
      expect(screen.queryByPlaceholderText(/Search pages/i)).toBeNull(),
    );
  });

  it('filters commands by query', () => {
    renderPalette();
    dispatchOpen();
    act(() => fireEvent.change(input(), { target: { value: 'host' } }));
    expect(screen.getByText('Hosts')).toBeInTheDocument();
    expect(screen.queryByText('Settings')).toBeNull();
  });

  it('shows a no-matches message for a non-matching query', () => {
    renderPalette();
    dispatchOpen();
    act(() => fireEvent.change(input(), { target: { value: 'zzznotathing' } }));
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
    act(() => fireEvent.change(input(), { target: { value: 'hosts' } }));
    act(() => fireEvent.keyDown(input(), { key: 'Enter' }));
    expect(h.navigate).toHaveBeenCalledWith('/hosts');
    await waitFor(() =>
      expect(screen.queryByPlaceholderText(/Search pages/i)).toBeNull(),
    );
  });

  it('navigates on click', () => {
    renderPalette();
    dispatchOpen();
    act(() => fireEvent.click(screen.getByText('Dashboard')));
    expect(h.navigate).toHaveBeenCalledWith('/');
  });

  it('ArrowUp/ArrowDown adjust the active row without crashing', () => {
    renderPalette();
    dispatchOpen();
    act(() => fireEvent.keyDown(input(), { key: 'ArrowDown' }));
    act(() => fireEvent.keyDown(input(), { key: 'ArrowUp' }));
    act(() => fireEvent.keyDown(input(), { key: 'Enter' }));
    expect(h.navigate).toHaveBeenCalled();
  });
});
