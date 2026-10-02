// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Network discovery UI (Phase 21.6 S3).  The property under test is the
// feature's: the list is shown WITH its blind spots -- a list without them
// reads as "these are all the unmanaged devices", which it never is.

import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('react-i18next', () => {
    const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
        let s = typeof fallback === 'string' ? fallback : key;
        for (const [k, v] of Object.entries(opts ?? {})) {
            s = s.replace(new RegExp(`{{${k}}}`, 'g'), String(v));
        }
        return s;
    };
    return { useTranslation: () => ({ t, i18n: { language: 'en' } }) };
});

vi.mock('../../../Services/assetDiscoveryService', async () => {
    const actual = await vi.importActual<typeof import('../../../Services/assetDiscoveryService')>(
        '../../../Services/assetDiscoveryService',
    );
    return {
        ...actual,
        assetDiscoveryService: {
            getSummary: vi.fn(),
            listDevices: vi.fn(),
            listExclusions: vi.fn(),
            exclude: vi.fn(),
            revoke: vi.fn(),
            setPolicy: vi.fn(),
            listSweeps: vi.fn(),
            requestSweep: vi.fn(),
            excludeAddress: vi.fn(),
        },
    };
});

vi.mock('../../../Services/permissions', () => ({
    hasPermission: vi.fn(),
    SecurityRoles: { MANAGE_NETWORK_DISCOVERY: 'Manage Network Discovery' },
}));

import { assetDiscoveryService } from '../../../Services/assetDiscoveryService';
import type { DiscoveredDevice, DiscoverySummary } from '../../../Services/assetDiscoveryService';
import { hasPermission } from '../../../Services/permissions';
import AssetDiscovery from '../../../Pages/AssetDiscovery';

const svc = assetDiscoveryService as unknown as Record<string, ReturnType<typeof vi.fn>>;

const summary = (over: Partial<DiscoverySummary> = {}): DiscoverySummary => ({
    policy: { enabled: true, report_interval_seconds: 300, sweep_enabled: true, updated_by: 'op@example.com', updated_at: '2026-09-29T10:00:00' },
    counts: { unmanaged: 2, managed: 1, excluded: 0 },
    networks: [{ network: '192.168.4.0/24', unmanaged: 2, observers: 1 }],
    observers: [
        {
            host_id: 'h1',
            fqdn: 'win-01.example.com',
            networks: [{ interface: 'wlan0', network: '192.168.4.0/24' }],
            last_report_at: '2026-09-29T10:00:00',
            stale: true,
            unavailable: { arp_listen: 'unsupported_platform' },
        },
    ],
    coverage: { equipped: 3, not_equipped: 1, unknown: 1 },
    blind_spots: { silent_devices_unseen: true, unswept_networks: ['192.168.4.0/24'], stale_observers: 1, observers_without_arp: 1 },
    ...over,
});

const device = (id: string, over: Partial<DiscoveredDevice> = {}): DiscoveredDevice => ({
    id,
    identity: `00:1a:2b:00:00:0${id}`,
    identity_kind: 'mac',
    mac: `00:1a:2b:00:00:0${id}`,
    mac_locally_administered: false,
    last_ip: `192.168.4.2${id}`,
    ips: [],
    hostnames: [],
    evidence: { mdns_services: ['_ipp._tcp'], ssdp: [] },
    methods: ['arp_listen'],
    managed_host_id: null,
    managed_host_fqdn: null,
    managed_reason: null,
    first_seen_at: null,
    last_seen_at: '2026-09-29T10:00:00',
    status: 'unmanaged',
    networks: ['192.168.4.0/24'],
    observers: ['agent.example.com'],
    exclusion: null,
    ...over,
});

beforeEach(() => {
    vi.clearAllMocks();
    svc.getSummary.mockResolvedValue(summary());
    svc.listDevices.mockResolvedValue({
        total: 2,
        devices: [device('1'), device('2', { mac_locally_administered: true })],
    });
    svc.listExclusions.mockResolvedValue([]);
    (hasPermission as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(true);
});

describe('AssetDiscovery page', () => {
    test('the blind spots are shown beside the list', async () => {
        render(<AssetDiscovery />);
        await screen.findByText('00:1a:2b:00:00:01');
        expect(screen.getByText(/Agents only listen/)).toBeTruthy();
        expect(screen.getByText((text) => text.includes('win-01.example.com'))).toBeTruthy();
        expect(screen.getByText(/has stopped reporting/)).toBeTruthy();
        expect(screen.getByText(/not supported on this platform/)).toBeTruthy();
        expect(screen.getByText(/2 hosts run an agent that cannot take part/)).toBeTruthy();
        expect(screen.getByText('2 on 192.168.4.0/24')).toBeTruthy();
    });

    test('says so when discovery is off', async () => {
        svc.getSummary.mockResolvedValue(summary({ policy: { enabled: false, report_interval_seconds: 300, sweep_enabled: false, updated_by: null, updated_at: null } }));
        render(<AssetDiscovery />);
        expect(await screen.findByText(/Discovery is turned off/)).toBeTruthy();
    });

    test('a locally administered address is labeled', async () => {
        render(<AssetDiscovery />);
        expect(await screen.findByText('Address may change')).toBeTruthy();
    });

    test('bulk exclude sends the selection with a category and a reason', async () => {
        svc.exclude.mockResolvedValue({ excluded: 2, already_excluded: 0, skipped_managed: 0, not_found: 0, exclusions: [] });
        render(<AssetDiscovery />);
        await screen.findByText('00:1a:2b:00:00:01');
        fireEvent.click(await screen.findByLabelText('Select all'));
        fireEvent.click(screen.getByText('Mark 2 as known and fine'));
        const dialog = await screen.findByRole('dialog');
        const confirm = within(dialog).getByText('Mark as known');
        expect((confirm.closest('button') as HTMLButtonElement).disabled).toBe(true); // no reason yet
        fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'Office printers' } });
        fireEvent.click(confirm);
        await waitFor(() => expect(svc.exclude).toHaveBeenCalledWith(['1', '2'], 'printer', 'Office printers'));
        expect(await screen.findByText('2 devices marked as known.')).toBeTruthy();
    });

    test('without the role there is nothing to select and no exclude button', async () => {
        (hasPermission as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(false);
        render(<AssetDiscovery />);
        await screen.findByText('00:1a:2b:00:00:01');
        expect(screen.queryByLabelText('Select all')).toBeNull();
        expect(screen.queryByText(/as known and fine/)).toBeNull();
    });

    test('the known-and-fine tab lists decisions and can revoke one', async () => {
        svc.listExclusions.mockResolvedValue([
            {
                id: 'x1', identity: '00:1a:2b:00:00:09', category: 'printer', reason: 'Front office',
                created_by: 'op@example.com', created_at: null, revoked_by: null, revoked_at: null,
                revoke_reason: null, last_ip: '192.168.4.9', last_seen_at: null,
            },
        ]);
        svc.revoke.mockResolvedValue({});
        render(<AssetDiscovery />);
        await screen.findByText('00:1a:2b:00:00:01');
        fireEvent.click(screen.getByText('Known and fine'));
        expect(await screen.findByText('Front office')).toBeTruthy();
        fireEvent.click(screen.getByText('Revoke'));
        const dialog = await screen.findByRole('dialog');
        fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'Printer replaced' } });
        fireEvent.click(within(dialog).getByText('Revoke'));
        await waitFor(() => expect(svc.revoke).toHaveBeenCalledWith('x1', 'Printer replaced'));
    });

    test('a load failure is reported', async () => {
        svc.getSummary.mockRejectedValue(new Error('boom'));
        render(<AssetDiscovery />);
        expect(await screen.findByText('Discovered devices could not be loaded.')).toBeTruthy();
    });

    test('the networks not swept recently are named', async () => {
        render(<AssetDiscovery />);
        expect(await screen.findByText('Not swept in the last 7 days: 192.168.4.0/24')).toBeTruthy();
    });

    test('the sweeps tab shows the history and starts a sweep', async () => {
        svc.listSweeps.mockResolvedValue([
            {
                id: 's1', cidr: '192.168.4.0/24', rate: 50, addresses: 254, status: 'completed', reason: null,
                requested_by: 'op@example.com', requested_at: null, agent_host_id: 'h1', agent_fqdn: 'gdr-t14',
                finished_at: null, probed: 253, devices_found: 26,
            },
        ]);
        svc.requestSweep.mockResolvedValue({});
        render(<AssetDiscovery />);
        await screen.findByText('00:1a:2b:00:00:01');
        fireEvent.click(screen.getByText('Sweeps'));
        expect(await screen.findByText('26 of 253 addresses')).toBeTruthy();
        expect(screen.getByText('gdr-t14')).toBeTruthy();
        fireEvent.click(screen.getByText('Sweep a network'));
        const dialog = await screen.findByRole('dialog');
        fireEvent.click(within(dialog).getByText('Start sweep'));
        await waitFor(() => expect(svc.requestSweep).toHaveBeenCalledWith('192.168.4.0/24', 50));
    });

    test('a refused sweep shows the server reason', async () => {
        svc.listSweeps.mockResolvedValue([]);
        svc.requestSweep.mockRejectedValue({ response: { data: { detail: { code: 'not_on_link', message: 'No agent is on that network' } } } });
        render(<AssetDiscovery />);
        await screen.findByText('00:1a:2b:00:00:01');
        fireEvent.click(screen.getByText('Sweeps'));
        fireEvent.click(await screen.findByText('Sweep a network'));
        const dialog = await screen.findByRole('dialog');
        fireEvent.click(within(dialog).getByText('Start sweep'));
        expect(await within(dialog).findByText('No agent is on that network')).toBeTruthy();
    });

    test('with sweeps off there is no sweep button, only the reason', async () => {
        svc.getSummary.mockResolvedValue(summary({ policy: { enabled: true, report_interval_seconds: 300, sweep_enabled: false, updated_by: null, updated_at: null } }));
        svc.listSweeps.mockResolvedValue([]);
        render(<AssetDiscovery />);
        await screen.findByText('00:1a:2b:00:00:01');
        fireEvent.click(screen.getByText('Sweeps'));
        expect(await screen.findByText(/Active sweeps are turned off/)).toBeTruthy();
        expect(screen.queryByText('Sweep a network')).toBeNull();
    });

    test('vendor and a labeled guess are shown, low confidence as Maybe', async () => {
        svc.listDevices.mockResolvedValue({
            total: 2,
            devices: [
                device('1', { vendor: 'Brother Industries, LTD.', device_type: 'printer', classification: { confidence: 'high', reasons: ['mdns:_ipp'] } }),
                device('2', { device_type: 'phone_or_tablet', classification: { confidence: 'low', reasons: ['mac:locally_administered'] } }),
            ],
        });
        svc.getSummary.mockResolvedValue(summary({ types: { printer: 1, phone_or_tablet: 1 } }));
        render(<AssetDiscovery />);
        expect(await screen.findByText('Brother Industries, LTD.')).toBeTruthy();
        expect(screen.getByText('Maybe: Phone or tablet')).toBeTruthy();
        expect(screen.getByText('Printer: 1')).toBeTruthy();
    });

    test('marking a printer as known suggests the printer category', async () => {
        svc.listDevices.mockResolvedValue({
            total: 1,
            devices: [device('1', { device_type: 'iot', classification: { confidence: 'high', reasons: ['mdns:_hap'] } })],
        });
        svc.exclude.mockResolvedValue({ excluded: 1, already_excluded: 0, skipped_managed: 0, not_found: 0, exclusions: [] });
        render(<AssetDiscovery />);
        fireEvent.click(await screen.findByLabelText('00:1a:2b:00:00:01'));
        fireEvent.click(screen.getByText('Mark 1 as known and fine'));
        const dialog = await screen.findByRole('dialog');
        fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'Office thermostat' } });
        fireEvent.click(within(dialog).getByText('Mark as known'));
        await waitFor(() => expect(svc.exclude).toHaveBeenCalledWith(['1'], 'iot', 'Office thermostat'));
    });

    test('a static address is registered with its warning shown', async () => {
        svc.excludeAddress.mockResolvedValue({});
        render(<AssetDiscovery />);
        await screen.findByText('00:1a:2b:00:00:01');
        fireEvent.click(screen.getByText('Known and fine'));
        fireEvent.click(await screen.findByText('Register a static address'));
        const dialog = await screen.findByRole('dialog');
        expect(within(dialog).getByText(/Only for addresses that never change/)).toBeTruthy();
        fireEvent.change(within(dialog).getByLabelText('IP address'), { target: { value: '192.168.4.1' } });
        fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'Core router VIP' } });
        fireEvent.click(within(dialog).getByText('Register'));
        await waitFor(() => expect(svc.excludeAddress).toHaveBeenCalledWith('192.168.4.1', 'virtual_address', 'Core router VIP'));
    });

    test('a refused static address shows the server reason', async () => {
        svc.excludeAddress.mockRejectedValue({ response: { data: { detail: 'That address is already registered as known' } } });
        render(<AssetDiscovery />);
        await screen.findByText('00:1a:2b:00:00:01');
        fireEvent.click(screen.getByText('Known and fine'));
        fireEvent.click(await screen.findByText('Register a static address'));
        const dialog = await screen.findByRole('dialog');
        fireEvent.change(within(dialog).getByLabelText('IP address'), { target: { value: '192.168.4.1' } });
        fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'Core router VIP' } });
        fireEvent.click(within(dialog).getByText('Register'));
        expect(await within(dialog).findByText('That address is already registered as known')).toBeTruthy();
    });
});
