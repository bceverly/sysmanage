// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// An SSDP M-SEARCH's ST is what the device is LOOKING FOR, not what it is
// (2026-10-17: a Windows laptop searching for its router showed as network
// gear).  The grid keeps those apart, labeled "Searches for".

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

vi.mock('react-i18next', () => {
    const t = (_key: string, fallback?: string, params?: Record<string, string>) =>
        (fallback ?? _key).replace(/\{\{(\w+)\}\}/g, (_m, name) => params?.[name] ?? '');
    return { useTranslation: () => ({ t, i18n: { language: 'en' } }) };
});

import type { DiscoveredDevice } from '../../../Services/assetDiscoveryService';
import DeviceTable, { splitSsdp } from '../DeviceTable';

const device = (evidence: DiscoveredDevice['evidence']): DiscoveredDevice => ({
    id: 'x13s', identity: 'ip:192.168.4.193', identity_kind: 'ip', mac: null,
    mac_locally_administered: false, last_ip: '192.168.4.193', ips: ['192.168.4.193'],
    hostnames: [], evidence, methods: ['ssdp'], managed_host_id: null,
    managed_host_fqdn: null, managed_reason: null, first_seen_at: null, last_seen_at: null,
    status: 'unmanaged', networks: [], observers: [], exclusion: null,
});

const IGD = 'urn:schemas-upnp-org:device:InternetGatewayDevice:1';

describe('SSDP searches vs identity', () => {
    test("an older agent's bare ST lines with no SERVER are searches", () => {
        const split = splitSsdp(device({ ssdp: [`ST: ${IGD}`, 'ST: upnp:rootdevice'] }));
        expect(split.identity).toEqual([]);
        expect(split.searches).toEqual([IGD, 'upnp:rootdevice']);
    });

    test("a router's reply (SERVER present) keeps its ST as identity", () => {
        const split = splitSsdp(device({ ssdp: ['SERVER: MiniUPnPd/2.3', `ST: ${IGD}`] }));
        expect(split.identity).toEqual(['SERVER: MiniUPnPd/2.3', `ST: ${IGD}`]);
        expect(split.searches).toEqual([]);
    });

    test('a newer agent sends searches apart and marks reply ST as RST', () => {
        const split = splitSsdp(device({ ssdp: [`RST: ${IGD}`], ssdp_searches: ['ssdp:all'] }));
        expect(split.identity).toEqual([`RST: ${IGD}`]);
        expect(split.searches).toEqual(['ssdp:all']);
    });

    test('the grid shows searches as their own labeled chip, not as identity', () => {
        render(
            <DeviceTable
                devices={[device({ mdns_services: ['_dosvc._tcp'], ssdp: [`ST: ${IGD}`, 'ST: upnp:rootdevice'] })]}
                selectable={false}
                selected={new Set()}
                onToggle={() => undefined}
                onToggleAll={() => undefined}
            />,
        );
        expect(screen.getByTestId('ssdp-searches')).toHaveTextContent(`Searches for: ${IGD} (+1)`);
        expect(screen.queryByText(`ST: ${IGD}`)).toBeNull();
        expect(screen.getByText('_dosvc._tcp')).toBeInTheDocument();
    });
});
