// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Column sorting for the discovered-devices table.  Pure functions so the
// ordering rules -- addresses by number, not as text -- are tested directly.

import type { DiscoveredDevice } from '../../Services/assetDiscoveryService';

export type SortKey = 'device' | 'address' | 'seenBy' | 'lastSeen' | 'status';
export type SortDirection = 'asc' | 'desc';

// "192.168.4.9" before "192.168.4.10": a string compare puts them the
// other way round.  The key is a tuple compared element by element: IPv4 is
// [4, a, b, c, d], IPv6 [6, g1..g8], so every IPv4 address sorts first.
// Anything unparseable has no key and sorts last.
export function ipSortKey(ip: string | null | undefined): number[] | null {
    if (!ip) return null;
    const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(ip);
    if (v4) {
        const parts = v4.slice(1).map(Number);
        return parts.some(part => part > 255) ? null : [4, ...parts];
    }
    return ipv6SortKey(ip);
}

function ipv6SortKey(ip: string): number[] | null {
    const bare = ip.split('%')[0];
    if (!bare.includes(':')) return null;
    const halves = bare.split('::');
    if (halves.length > 2) return null;
    const head = halves[0] ? halves[0].split(':') : [];
    const tail = halves.length === 2 && halves[1] ? halves[1].split(':') : [];
    const missing = 8 - head.length - tail.length;
    if (missing < 0 || (halves.length === 1 && missing !== 0)) return null;
    const groups: string[] = [...head, ...Array(missing).fill('0'), ...tail];
    if (!groups.every(group => /^[0-9a-fA-F]{1,4}$/.test(group))) return null;
    return [6, ...groups.map(group => parseInt(group, 16))];
}

const text = (value: string | null | undefined): string | null =>
    value ? value.toLocaleLowerCase() : null;

const time = (value: string | null | undefined): number | null => {
    if (!value) return null;
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed;
};

// What each column sorts by.  Status groups unmanaged first (the actionable
// ones), then excluded, then managed -- the order an operator triages in.
const STATUS_ORDER: Record<string, number> = { unmanaged: 0, excluded: 1, managed: 2 };

type SortValue = string | number | number[] | null;

function sortValue(device: DiscoveredDevice, key: SortKey): SortValue {
    switch (key) {
        case 'device':
            return text(device.mac ?? device.last_ip ?? device.identity);
        case 'address':
            return ipSortKey(device.last_ip);
        case 'seenBy':
            return text(device.observers[0]);
        case 'lastSeen':
            return time(device.last_seen_at);
        case 'status':
            return STATUS_ORDER[device.status] ?? 99;
        default:
            return null;
    }
}

function compareTuples(a: number[], b: number[]): number {
    for (let i = 0; i < Math.min(a.length, b.length); i += 1) {
        if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
    }
    return a.length - b.length;
}

function compareValues(a: SortValue, b: SortValue): number {
    if (a === b) return 0;
    if (a === null) return 1;
    if (b === null) return -1;
    if (Array.isArray(a) && Array.isArray(b)) return compareTuples(a, b);
    if (typeof a === 'string' && typeof b === 'string') return a.localeCompare(b);
    return a < b ? -1 : 1;
}

// A stable sort; missing values stay at the bottom in either direction, so
// flipping to descending never fills the top of the table with blanks.
export function sortDevices(
    devices: DiscoveredDevice[],
    key: SortKey,
    direction: SortDirection,
): DiscoveredDevice[] {
    const sign = direction === 'asc' ? 1 : -1;
    return devices
        .map((device, index) => ({ device, index, value: sortValue(device, key) }))
        .sort((left, right) => {
            if (left.value === null || right.value === null) {
                return compareValues(left.value, right.value) || left.index - right.index;
            }
            return sign * compareValues(left.value, right.value) || left.index - right.index;
        })
        .map(entry => entry.device);
}
