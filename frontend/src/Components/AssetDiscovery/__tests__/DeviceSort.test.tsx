// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The discovered-devices table sorts by column (Bryan, 2026-10-16).  Addresses
// sort by number, not as text; blanks stay last in either direction.

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
import { ipSortKey, sortDevices } from '../deviceSort';

const device = (id: string, over: Partial<DiscoveredDevice> = {}): DiscoveredDevice => ({
    id,
    identity: id,
    identity_kind: 'mac',
    mac: null,
    mac_locally_administered: false,
    last_ip: null,
    ips: [],
    hostnames: [],
    evidence: {},
    methods: [],
    managed_host_id: null,
    managed_host_fqdn: null,
    managed_reason: null,
    first_seen_at: null,
    last_seen_at: null,
    status: 'unmanaged',
    networks: [],
    observers: [],
    exclusion: null,
    ...over,
});

const ids = (rows: DiscoveredDevice[]) => rows.map(row => row.id);

describe('deviceSort', () => {
    test('IPv4 sorts by number, not as text', () => {
        const rows = [
            device('ten', { last_ip: '192.168.4.10' }),
            device('nine', { last_ip: '192.168.4.9' }),
            device('hundred', { last_ip: '192.168.4.100' }),
            device('lower', { last_ip: '10.0.0.200' }),
        ];
        expect(ids(sortDevices(rows, 'address', 'asc'))).toEqual(['lower', 'nine', 'ten', 'hundred']);
        expect(ids(sortDevices(rows, 'address', 'desc'))).toEqual(['hundred', 'ten', 'nine', 'lower']);
    });

    test('IPv6 sorts after IPv4, :: compression understood', () => {
        expect(ipSortKey('fe80::1')).toEqual([6, 0xfe80, 0, 0, 0, 0, 0, 0, 1]);
        expect(ipSortKey('2001:db8:0:0:0:0:0:2')).toEqual([6, 0x2001, 0xdb8, 0, 0, 0, 0, 0, 2]);
        const rows = [
            device('v6', { last_ip: 'fe80::1' }),
            device('v4', { last_ip: '192.168.4.11' }),
            device('doc', { last_ip: '2001:db8::2' }),
        ];
        expect(ids(sortDevices(rows, 'address', 'asc'))).toEqual(['v4', 'doc', 'v6']);
    });

    test('unparseable and missing addresses stay last in both directions', () => {
        expect(ipSortKey('999.1.1.1')).toBeNull();
        expect(ipSortKey('not-an-ip')).toBeNull();
        const rows = [
            device('none'),
            device('a', { last_ip: '192.168.4.2' }),
            device('b', { last_ip: '192.168.4.3' }),
        ];
        expect(ids(sortDevices(rows, 'address', 'asc'))).toEqual(['a', 'b', 'none']);
        expect(ids(sortDevices(rows, 'address', 'desc'))).toEqual(['b', 'a', 'none']);
    });

    test('last seen sorts by time, text columns ignore case', () => {
        const rows = [
            device('old', { last_seen_at: '2026-10-15T09:00:00Z', observers: ['nas'] }),
            device('new', { last_seen_at: '2026-10-16T09:00:00Z', observers: ['Beast'] }),
        ];
        expect(ids(sortDevices(rows, 'lastSeen', 'desc'))).toEqual(['new', 'old']);
        expect(ids(sortDevices(rows, 'seenBy', 'asc'))).toEqual(['new', 'old']);
    });

    test('status puts the actionable unmanaged devices first', () => {
        const rows = [
            device('m', { status: 'managed' }),
            device('x', { status: 'excluded' }),
            device('u', { status: 'unmanaged' }),
        ];
        expect(ids(sortDevices(rows, 'status', 'asc'))).toEqual(['u', 'x', 'm']);
    });
});

describe('DeviceTable sorting', () => {
    const rows = [
        // A MAC each, or the Device column falls back to showing the IP too.
        device('ten', { mac: 'aa:aa:aa:aa:aa:10', last_ip: '192.168.4.10' }),
        device('nine', { mac: 'aa:aa:aa:aa:aa:09', last_ip: '192.168.4.9' }),
    ];
    const renderTable = () => render(
        <DeviceTable devices={rows} selectable={false} selected={new Set()} onToggle={() => {}} onToggleAll={() => {}} />,
    );
    const addressOrder = () =>
        screen.getAllByText(/^192\.168\.4\.\d+$/).map(cell => cell.textContent);

    test('keeps the server order until a header is clicked', () => {
        renderTable();
        expect(addressOrder()).toEqual(['192.168.4.10', '192.168.4.9']);
    });

    test('clicking Address sorts ascending, clicking again flips it', () => {
        renderTable();
        const header = screen.getByRole('button', { name: 'Address' });
        fireEvent.click(header);
        expect(addressOrder()).toEqual(['192.168.4.9', '192.168.4.10']);
        expect(within(header.closest('th') as HTMLElement).getByRole('button')).toBeTruthy();
        expect(header.closest('th')?.getAttribute('aria-sort')).toBe('ascending');
        fireEvent.click(header);
        expect(addressOrder()).toEqual(['192.168.4.10', '192.168.4.9']);
        expect(header.closest('th')?.getAttribute('aria-sort')).toBe('descending');
    });
});
