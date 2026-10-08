// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Page-level tests for Pages/HostDetail.tsx.  The page is a coordinator: it
 * wires ~15 hooks into the header / nav rail / tab content / dialog
 * components.  Every hook and child component is mocked here so the tests
 * exercise only the page's own logic: loading / error states, the tab
 * definition list (platform + license gating, plugin tab filtering), tab
 * switching, and the add-user / add-group refresh callbacks.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface Scenario {
    host: Record<string, unknown> | null;
    error?: string | null;
    loading?: boolean;
    modules?: string[];
    features?: string[];
    ubuntuPro?: Record<string, unknown> | null;
}

const state: { scenario: Scenario; pluginTabs: unknown[] } = vi.hoisted(() => ({
    scenario: { host: null },
    pluginTabs: [],
}));

const mockGetUsers = vi.fn();
const mockGetGroups = vi.fn();

vi.mock('../../Services/hosts', () => ({
    doGetHostUsers: (...args: unknown[]) => mockGetUsers(...args),
    doGetHostGroups: (...args: unknown[]) => mockGetGroups(...args),
}));

vi.mock('../../plugins', () => ({
    usePlugins: () => ({ hostDetailTabs: state.pluginTabs }),
}));

vi.mock('../../Components/HostDetail/useHostData', async () => {
    const R = await import('react');
    return {
        useHostData: (args: Record<string, (_v: unknown) => void>) => {
            R.useEffect(() => {
                const s = state.scenario;
                args.setHost(s.host);
                args.setLicenseModules(s.modules ?? []);
                args.setLicenseFeatures(s.features ?? []);
                args.setUbuntuProInfo(s.ubuntuPro ?? null);
                if (s.error) args.setError(s.error);
                args.setLoading(s.loading ?? false);
            }, []);
        },
    };
});

vi.mock('../../Components/HostDetail/useHostTabNavigation', () => ({
    useHostTabNavigation: ({ setCurrentTab }: { setCurrentTab: (_n: number) => void }) => ({
        hostTabGroups: [],
        handleTabChange: (_e: unknown, idx: number) => setCurrentTab(idx),
    }),
}));

const { emptyHook } = vi.hoisted(() => ({ emptyHook: () => ({}) }));
vi.mock('../../Components/HostDetail/useHostPermissions', () => ({ useHostPermissions: emptyHook }));
vi.mock('../../Components/HostDetail/useHostSnackbar', () => ({ useHostSnackbar: emptyHook }));
vi.mock('../../Components/HostDetail/useHostAntivirus', () => ({ useHostAntivirus: emptyHook }));
vi.mock('../../Components/HostDetail/useHostUbuntuPro', () => ({ useHostUbuntuPro: emptyHook }));
vi.mock('../../Components/HostDetail/useHostTags', () => ({ useHostTags: emptyHook }));
vi.mock('../../Components/HostDetail/useHostObservability', () => ({ useHostObservability: emptyHook }));
vi.mock('../../Components/HostDetail/useChildHosts', () => ({ useChildHosts: emptyHook }));
vi.mock('../../Components/HostDetail/useHostSoftware', () => ({ useHostSoftware: emptyHook }));
vi.mock('../../Components/HostDetail/useHostAccessManagement', () => ({ useHostAccessManagement: emptyHook }));
vi.mock('../../Components/HostDetail/useHostRolesAndCerts', () => ({ useHostRolesAndCerts: emptyHook }));
vi.mock('../../Components/HostDetail/useHostLifecycle', () => ({ useHostLifecycle: emptyHook }));
vi.mock('../../Components/HostDetail/useHostInventoryFilters', () => ({ useHostInventoryFilters: emptyHook }));
vi.mock('../../Components/HostDetail/useCertificateGrid', () => ({ useCertificateGrid: emptyHook }));

vi.mock('../../Components/HostDetail/HostDetailHeader', () => ({
    default: ({ host }: { host: { fqdn: string } }) => <div data-testid="header">{host.fqdn}</div>,
}));

vi.mock('../../Components/HostDetail/HostDetailNavRail', () => ({
    default: ({ tabDefinitions, handleTabChange }: {
        tabDefinitions: Array<{ id: string; label: string }>;
        handleTabChange: (_e: unknown, _i: number) => void;
    }) => (
        <div data-testid="rail">
            {tabDefinitions.map((td, i) => (
                <button key={td.id} data-testid={`tab-${td.id}`} onClick={() => handleTabChange(null, i)}>
                    {td.label}
                </button>
            ))}
        </div>
    ),
}));

vi.mock('../../Components/HostDetail/HostDetailTabContent', () => ({
    default: ({ currentTabId, visiblePluginTabs }: {
        currentTabId: string;
        visiblePluginTabs: Array<{ id: string }>;
    }) => (
        <div>
            <div data-testid="current-tab">{currentTabId}</div>
            <div data-testid="visible-plugins">{visiblePluginTabs.map(p => p.id).join(',')}</div>
        </div>
    ),
}));

vi.mock('../../Components/HostDetail/HostConfirmDialogs', () => ({ default: () => null }));
vi.mock('../../Components/HostDetail/CreateChildHostDialog', () => ({ default: () => null }));
vi.mock('../../Components/HostDetail/HostActionDialogs', () => ({
    default: ({ onAddUserSuccess, onAddGroupSuccess }: {
        onAddUserSuccess: () => void;
        onAddGroupSuccess: () => void;
    }) => (
        <div>
            <button onClick={onAddUserSuccess}>user-added</button>
            <button onClick={onAddGroupSuccess}>group-added</button>
        </div>
    ),
}));

import HostDetail from '../../Pages/HostDetail';

const renderPage = (scenario: Scenario, path = '/hosts/h1') => {
    state.scenario = scenario;
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/hosts/:hostId" element={<HostDetail />} />
                <Route path="/hosts" element={<div>hosts list page</div>} />
            </Routes>
        </MemoryRouter>,
    );
};

const tabIds = () =>
    screen.getAllByRole('button')
        .map(b => b.getAttribute('data-testid'))
        .filter((id): id is string => !!id && id.startsWith('tab-'))
        .map(id => id.slice(4));

describe('HostDetail page', () => {
    beforeEach(() => {
        state.pluginTabs = [];
        mockGetUsers.mockReset();
        mockGetGroups.mockReset();
    });

    it('shows a spinner while loading', () => {
        renderPage({ host: null, loading: true });
        expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('shows the error message and navigates back to the host list', async () => {
        renderPage({ host: null, error: 'Boom: host lookup failed' });
        expect(await screen.findByText('Boom: host lookup failed')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button'));
        expect(await screen.findByText('hosts list page')).toBeInTheDocument();
    });

    it('shows "Host not found" when there is no host and no error', async () => {
        renderPage({ host: null });
        expect(await screen.findByText('Host not found')).toBeInTheDocument();
    });

    it('builds the minimal tab set for an unknown platform', async () => {
        renderPage({ host: { fqdn: 'plain.example', platform: 'Plan9' } });
        expect(await screen.findByTestId('header')).toHaveTextContent('plain.example');
        expect(tabIds()).toEqual([
            'info', 'hardware', 'processes', 'software', 'software-changes',
            'access', 'security', 'certificates', 'server-roles', 'diagnostics',
        ]);
        expect(screen.getByTestId('current-tab')).toHaveTextContent('info');
    });

    it('returns no repo/child tabs when the host has no platform info', async () => {
        renderPage({ host: { fqdn: 'bare.example' }, modules: ['container_engine'] });
        await screen.findByTestId('header');
        const ids = tabIds();
        expect(ids).not.toContain('third-party-repos');
        expect(ids).not.toContain('child-hosts');
        expect(ids).not.toContain('ubuntu-pro');
    });

    it('adds third-party repos, child hosts, Ubuntu Pro, advisor, compliance and image mode when eligible', async () => {
        renderPage({
            host: { fqdn: 'u.example', platform: 'Linux', platform_release: 'Ubuntu 24.04', is_image_mode: true },
            modules: ['container_engine', 'advisor_engine', 'compliance_engine'],
            features: ['compliance'],
            ubuntuPro: { available: true },
        });
        await screen.findByTestId('header');
        expect(tabIds()).toEqual([
            'info', 'advisor', 'hardware', 'processes', 'software', 'software-changes',
            'third-party-repos', 'access', 'security', 'compliance', 'certificates',
            'server-roles', 'child-hosts', 'ubuntu-pro', 'image-mode', 'diagnostics',
        ]);
    });

    it('hides compliance without the compliance feature and Ubuntu Pro when unavailable', async () => {
        renderPage({
            host: { fqdn: 'u.example', platform: 'Ubuntu' },
            modules: ['compliance_engine'],
            features: [],
            ubuntuPro: { available: false },
        });
        await screen.findByTestId('header');
        const ids = tabIds();
        expect(ids).toContain('third-party-repos');
        expect(ids).not.toContain('compliance');
        expect(ids).not.toContain('ubuntu-pro');
        expect(ids).not.toContain('child-hosts');
    });

    it('treats OpenBSD as unsupported for third-party repos but supports child hosts', async () => {
        renderPage({ host: { fqdn: 'o.example', platform: 'OpenBSD' }, modules: ['container_engine'] });
        await screen.findByTestId('header');
        const ids = tabIds();
        expect(ids).not.toContain('third-party-repos');
        expect(ids).toContain('child-hosts');
    });

    it('hides third-party repos when only the release string says OpenBSD', async () => {
        renderPage({ host: { fqdn: 'o2.example', platform: 'Ubuntu', platform_release: 'OpenBSD 7.5' } });
        await screen.findByTestId('header');
        expect(tabIds()).not.toContain('third-party-repos');
    });

    it('detects repo support from the release string alone', async () => {
        renderPage({ host: { fqdn: 'r.example', platform: 'Linux', platform_release: 'Fedora 40' } });
        await screen.findByTestId('header');
        expect(tabIds()).toContain('third-party-repos');
    });

    it('never offers child hosts on a child host', async () => {
        renderPage({
            host: { fqdn: 'c.example', platform: 'Windows', parent_host_id: 'p1' },
            modules: ['container_engine'],
        });
        await screen.findByTestId('header');
        const ids = tabIds();
        expect(ids).toContain('third-party-repos');
        expect(ids).not.toContain('child-hosts');
    });

    it('does not offer child hosts on macOS even when licensed', async () => {
        renderPage({ host: { fqdn: 'm.example', platform: 'macOS' }, modules: ['container_engine'] });
        await screen.findByTestId('header');
        const ids = tabIds();
        expect(ids).toContain('third-party-repos');
        expect(ids).not.toContain('child-hosts');
    });

    it('filters plugin tabs by module, feature and id collision, and places them by position', async () => {
        const icon = <span />;
        const comp = () => null;
        state.pluginTabs = [
            { id: 'p-after-info', icon, labelKey: 'Plugin After Info', component: comp, position: 'after-info' },
            { id: 'p-after-sec', icon, labelKey: 'Plugin After Security', component: comp, position: 'after-security', moduleRequired: 'mod_a' },
            { id: 'p-before-diag', icon, labelKey: 'Plugin Before Diag', component: comp, position: 'before-diagnostics', featureFlag: 'feat_b' },
            { id: 'p-unlicensed', icon, labelKey: 'Nope', component: comp, position: 'after-info', moduleRequired: 'mod_missing' },
            { id: 'p-no-feature', icon, labelKey: 'Nope2', component: comp, position: 'after-info', featureFlag: 'feat_missing' },
            { id: 'info', icon, labelKey: 'Collides', component: comp, position: 'after-info' },
        ];
        renderPage({ host: { fqdn: 'p.example', platform: 'Plan9' }, modules: ['mod_a'], features: ['feat_b'] });
        await screen.findByTestId('header');
        expect(tabIds()).toEqual([
            'info', 'p-after-info', 'hardware', 'processes', 'software', 'software-changes',
            'access', 'security', 'p-after-sec', 'certificates', 'server-roles',
            'p-before-diag', 'diagnostics',
        ]);
        // The colliding "info" plugin tab is still "visible" (license OK) but
        // is dropped from the tab definitions; unlicensed ones are filtered.
        expect(screen.getByTestId('visible-plugins')).toHaveTextContent('p-after-info,p-after-sec,p-before-diag,info');
    });

    it('switches the current tab when a rail entry is clicked', async () => {
        renderPage({ host: { fqdn: 's.example', platform: 'Plan9' } });
        await screen.findByTestId('header');
        fireEvent.click(screen.getByTestId('tab-security'));
        expect(screen.getByTestId('current-tab')).toHaveTextContent('security');
        fireEvent.click(screen.getByTestId('tab-diagnostics'));
        expect(screen.getByTestId('current-tab')).toHaveTextContent('diagnostics');
    });

    it('reloads users and groups after an add succeeds', async () => {
        mockGetUsers.mockResolvedValue([]);
        mockGetGroups.mockRejectedValue(new Error('nope'));
        const errSpy = vi.spyOn(globalThis.console, 'error').mockImplementation(() => {});
        renderPage({ host: { fqdn: 'a.example', platform: 'Plan9' } });
        await screen.findByTestId('header');
        fireEvent.click(screen.getByText('user-added'));
        fireEvent.click(screen.getByText('group-added'));
        expect(mockGetUsers).toHaveBeenCalledWith('h1');
        expect(mockGetGroups).toHaveBeenCalledWith('h1');
        await waitFor(() => expect(errSpy).toHaveBeenCalled());
        errSpy.mockRestore();
    });
});
