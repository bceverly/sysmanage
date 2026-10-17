// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Device hostnames in Network Discovery (Bryan, 2026-10-17): the address
// column comes first, a device is shown by the name it announces (MAC and
// vendor beneath), every name and its source is on hover, and the Device
// column sorts by that name.

import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

vi.mock('react-i18next', () => {
    const t = (_key: string, fallback?: string, params?: Record<string, string>) =>
        (fallback ?? _key).replace(/\{\{(\w+)\}\}/g, (_m, name) => params?.[name] ?? '');
    return { useTranslation: () => ({ t, i18n: { language: 'en' } }) };
});

import type { DiscoveredDevice } from '../../../Services/assetDiscoveryService';
import DeviceTable from '../DeviceTable';
import { sortDevices } from '../deviceSort';

const device = (id: string, over: Partial<DiscoveredDevice> = {}): DiscoveredDevice => ({
    id, identity: id, identity_kind: 'mac', mac: id, mac_locally_administered: false,
    last_ip: null, ips: [], hostnames: [], evidence: {}, methods: [], managed_host_id: null,
    managed_host_fqdn: null, managed_reason: null, first_seen_at: null, last_seen_at: null,
    status: 'unmanaged', networks: [], observers: [], exclusion: null, ...over,
});

const PRINTER = device('00:1a:2b:3c:4d:5e', {
    last_ip: '192.168.4.21',
    vendor: 'Brother Industries',
    display_name: 'brother-hl',
    hostnames: [
        { name: 'brother-hl', source: 'dhcp', seen_at: null },
        { name: 'brother-hl.local', source: 'mdns', seen_at: null },
    ],
});

const table = (devices: DiscoveredDevice[]) => render(
    <DeviceTable devices={devices} selectable={false} selected={new Set()} onToggle={() => {}} onToggleAll={() => {}} />,
);

describe('device hostnames', () => {
    test('the address column comes before the device column', () => {
        table([PRINTER]);
        const headers = screen.getAllByRole('columnheader').map(h => h.textContent);
        expect(headers.indexOf('Address')).toBeLessThan(headers.indexOf('Device'));
        expect(headers.indexOf('Address')).toBe(0);
        const cells = within(screen.getAllByRole('row')[1]).getAllByRole('cell');
        expect(cells[0].textContent).toContain('192.168.4.21');
        expect(cells[1].textContent).toContain('brother-hl');
    });

    test('the announced name is shown, with MAC and vendor beneath', () => {
        table([PRINTER]);
        const name = screen.getByTestId('device-name');
        expect(name.textContent).toBe('brother-hl');
        const cell = name.closest('td') as HTMLElement;
        expect(cell.textContent).toContain('00:1a:2b:3c:4d:5e');
        expect(cell.textContent).toContain('Brother Industries');
        // The name is not repeated as an evidence chip.
        expect(screen.queryByText('brother-hl.local')).toBeNull();
    });

    test('every name and its source is on hover', async () => {
        table([PRINTER]);
        fireEvent.mouseOver(screen.getByTestId('device-name'));
        const names = await screen.findByTestId('device-names');
        expect(names.textContent).toContain('brother-hl (DHCP (host name))');
        expect(names.textContent).toContain('brother-hl.local (mDNS)');
    });

    test('a device without a name is shown by its MAC as before', () => {
        table([device('00:1a:2b:3c:4d:5f', { last_ip: '192.168.4.22' })]);
        expect(screen.queryByTestId('device-name')).toBeNull();
        expect(screen.getByText('00:1a:2b:3c:4d:5f')).toBeTruthy();
    });

    test('the device column sorts by the name when there is one', () => {
        const rows = [
            device('00:00:00:00:00:09', { display_name: 'zebra-printer' }),
            device('ff:00:00:00:00:01', { display_name: 'apple-tv' }),
            device('55:00:00:00:00:05'),
        ];
        expect(sortDevices(rows, 'device', 'asc').map(r => r.id)).toEqual([
            '55:00:00:00:00:05', 'ff:00:00:00:00:01', '00:00:00:00:00:09',
        ]);
    });
});
