// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import type { TFunction } from 'i18next';

import {
    formatDate,
    formatTimestamp,
    getStatusColor,
    getDisplayStatus,
    getApprovalStatusColor,
    formatMemorySize,
    formatCpuFrequency,
    getUserIdDisplay,
    getGroupIdDisplay,
    formatBytesWithCommas,
    formatCapacityWithFree,
    getStorageUsagePercentage,
    getStorageUsageColor,
    formatDateTime,
    getInstallationStatusColor,
    getTranslatedStatus,
    getOpenTelemetryServiceLabel,
    getOpenTelemetryServiceColor,
    getRoleServiceStatusLabel,
    getRoleServiceStatusColor,
    getServiceStatusLabel,
    getServiceStatusColor,
    resolveAntivirusOsName,
    isUbuntuHost,
    supportsChildHosts,
    resolveWithLegacyFallback,
    runOptionalFetch,
    isWindowsDistribution,
} from '../hostDetailHelpers';
import type { SysManageHost, UserAccount, UserGroup } from '../../../Services/hosts';

// Stand-in for i18next's t(key, fallback): return the English default when one
// is given, else echo the key.  Echoing matters -- getTranslatedStatus decides
// "was this translated?" by comparing the result against the key.
const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

const host = (overrides: Partial<SysManageHost> = {}) =>
    ({ id: '1', fqdn: 'h.example.test', ...overrides }) as SysManageHost;

describe('status + colour mapping', () => {
    test('getStatusColor is binary on "up"', () => {
        expect(getStatusColor('up')).toBe('success');
        expect(getStatusColor('down')).toBe('error');
        expect(getStatusColor('')).toBe('error');
    });

    test.each([
        ['approved', 'success'],
        ['pending', 'warning'],
        ['rejected', 'error'],
        ['revoked', 'error'],
        ['anything-else', 'default'],
    ])('getApprovalStatusColor(%s) -> %s', (status, expected) => {
        expect(getApprovalStatusColor(status)).toBe(expected);
    });

    test('getInstallationStatusColor is case-insensitive', () => {
        expect(getInstallationStatusColor('COMPLETED')).toBe('success');
        expect(getInstallationStatusColor('Failed')).toBe('error');
        for (const s of ['pending', 'queued', 'installing', 'in_progress']) {
            expect(getInstallationStatusColor(s)).toBe('warning');
        }
        expect(getInstallationStatusColor('weird')).toBe('default');
    });

    test.each([
        ['running', 'success'],
        ['stopped', 'error'],
        ['other', 'default'],
    ])('getOpenTelemetryServiceColor(%s) -> %s', (s, expected) => {
        expect(getOpenTelemetryServiceColor(s)).toBe(expected);
    });

    test('getOpenTelemetryServiceLabel covers all three branches', () => {
        expect(getOpenTelemetryServiceLabel(t, 'running')).toBe('Running');
        expect(getOpenTelemetryServiceLabel(t, 'stopped')).toBe('Stopped');
        expect(getOpenTelemetryServiceLabel(t, 'garbage')).toBe('Unknown');
    });

    test('role service status maps label and colour together', () => {
        expect(getRoleServiceStatusLabel(t, 'running')).toBe('Running');
        expect(getRoleServiceStatusColor('running')).toBe('success');
        expect(getRoleServiceStatusLabel(t, 'stopped')).toBe('Stopped');
        expect(getRoleServiceStatusColor('stopped')).toBe('error');
        expect(getRoleServiceStatusLabel(t, 'installed')).toBe('Installed');
        expect(getRoleServiceStatusColor('installed')).toBe('info');
    });

    test('role service status falls back to the RAW value before "Unknown"', () => {
        // A status we do not recognise is shown as-is rather than hidden behind
        // "Unknown" -- an operator can act on "degraded", not on "Unknown".
        expect(getRoleServiceStatusLabel(t, 'degraded')).toBe('degraded');
        expect(getRoleServiceStatusLabel(t, null)).toBe('Unknown');
        expect(getRoleServiceStatusLabel(t, undefined)).toBe('Unknown');
        expect(getRoleServiceStatusColor(null)).toBe('default');
    });

    test('Ubuntu Pro service status: n/a is distinct from disabled', () => {
        expect(getServiceStatusLabel(t, 'n/a')).toBe('N/A');
        expect(getServiceStatusColor('n/a')).toBe('default');
        expect(getServiceStatusLabel(t, 'enabled')).toBe('Enabled');
        expect(getServiceStatusColor('enabled')).toBe('success');
        expect(getServiceStatusLabel(t, 'disabled')).toBe('Disabled');
        expect(getServiceStatusColor('disabled')).toBe('warning');
    });

    test('getTranslatedStatus falls back to a humanised key when untranslated', () => {
        // Our stub echoes the key, which is exactly the "no translation" signal
        // the function tests for.
        expect(getTranslatedStatus(t, 'in_progress')).toBe('In progress');
        expect(getTranslatedStatus(t, 'failed')).toBe('Failed');
    });

    test('getTranslatedStatus uses the translation when there is one', () => {
        const translating = ((key: string) =>
            key === 'scripts.status.failed' ? 'Échec' : key) as unknown as TFunction;
        expect(getTranslatedStatus(translating, 'failed')).toBe('Échec');
    });
});

describe('formatting', () => {
    test('formatMemorySize crosses to GB at 1024 MB', () => {
        expect(formatMemorySize(t, 512)).toBe('512 MB');
        expect(formatMemorySize(t, 1024)).toBe('1.0 GB');
        expect(formatMemorySize(t, 3072)).toBe('3.0 GB');
    });

    test('formatCpuFrequency crosses to GHz at 1000 MHz', () => {
        expect(formatCpuFrequency(t, 800)).toBe('800 MHz');
        expect(formatCpuFrequency(t, 2400)).toBe('2.4 GHz');
    });

    test('zero and undefined are "not available", not "0"', () => {
        // 0 MB of RAM is not a fact about a host, it is missing data.
        expect(formatMemorySize(t, 0)).toBe('common.notAvailable');
        expect(formatMemorySize(t, undefined)).toBe('common.notAvailable');
        expect(formatCpuFrequency(t, 0)).toBe('common.notAvailable');
        expect(formatBytesWithCommas(t, 0)).toBe('common.notAvailable');
        expect(formatBytesWithCommas(t, undefined)).toBe('common.notAvailable');
    });

    test('formatBytesWithCommas walks the unit ladder', () => {
        expect(formatBytesWithCommas(t, 512)).toBe('512 B');
        expect(formatBytesWithCommas(t, 1024)).toBe('1 KB');
        expect(formatBytesWithCommas(t, 1024 ** 3)).toBe('1 GB');
        expect(formatBytesWithCommas(t, 1024 ** 4)).toBe('1 TB');
        // Beyond the ladder it stays in TB rather than inventing a unit.
        expect(formatBytesWithCommas(t, 1024 ** 5)).toContain('TB');
    });

    test('formatCapacityWithFree prefers available over used', () => {
        // available and used disagree on purpose: available must win, because it
        // is what the filesystem reports as usable.
        const out = formatCapacityWithFree(t, 1000, 900, 250);
        expect(out).toContain('25% free');
    });

    test('formatCapacityWithFree derives free from used when available is absent', () => {
        expect(formatCapacityWithFree(t, 1000, 750, undefined)).toContain('25% free');
    });

    test('formatCapacityWithFree omits the percentage when it knows neither', () => {
        expect(formatCapacityWithFree(t, 1000)).not.toContain('free');
        expect(formatCapacityWithFree(t, 0)).toBe('common.notAvailable');
    });
});

describe('storage usage', () => {
    test('percentage prefers available, matching the text display', () => {
        expect(getStorageUsagePercentage(1000, 100, 250)).toBe(75);
        expect(getStorageUsagePercentage(1000, 400, undefined)).toBe(40);
        expect(getStorageUsagePercentage(0)).toBe(0);
        expect(getStorageUsagePercentage(1000)).toBe(0);
    });

    test('percentage is clamped to 0..100', () => {
        // A filesystem can report used > capacity (reserved blocks); the bar
        // must not render past its track.
        expect(getStorageUsagePercentage(1000, 5000, undefined)).toBe(100);
        expect(getStorageUsagePercentage(1000, 0, 5000)).toBe(0);
    });

    test.each([
        [0, 'success'],
        [69.9, 'success'],
        [70, 'warning'],
        [89.9, 'warning'],
        [90, 'error'],
        [100, 'error'],
    ])('getStorageUsageColor(%s) -> %s', (pct, expected) => {
        expect(getStorageUsageColor(pct as number)).toBe(expected);
    });
});

describe('identity display', () => {
    test('Windows hosts show SID, others show UID/GID', () => {
        const win = host({ platform: 'Windows Server 2022' });
        const linux = host({ platform: 'Linux' });
        const user = { security_id: 'S-1-5-21', uid: 1000 } as UserAccount;
        const group = { security_id: 'S-1-5-32', gid: 27 } as UserGroup;

        expect(getUserIdDisplay(t, win, user)).toBe('SID: S-1-5-21');
        expect(getUserIdDisplay(t, linux, user)).toBe('UID: 1000');
        expect(getGroupIdDisplay(t, win, group)).toBe('SID: S-1-5-32');
        expect(getGroupIdDisplay(t, linux, group)).toBe('GID: 27');
    });

    test('gid 0 is root, not missing', () => {
        // The guard has to be an explicit null/undefined check: `gid || fallback`
        // would report root's group as unavailable.
        const linux = host({ platform: 'Linux' });
        expect(getGroupIdDisplay(t, linux, { gid: 0 } as UserGroup)).toBe('GID: 0');
        expect(getUserIdDisplay(t, linux, { uid: 0 } as UserAccount)).toBe('UID: 0');
    });

    test('missing ids fall back rather than printing undefined', () => {
        const win = host({ platform: 'Windows 11' });
        const linux = host({ platform: 'Linux' });
        expect(getUserIdDisplay(t, win, {} as UserAccount)).toBe('SID: common.notAvailable');
        expect(getGroupIdDisplay(t, win, {} as UserGroup)).toBe('SID: common.notAvailable');
        expect(getUserIdDisplay(t, linux, {} as UserAccount)).toBe('UID: common.notAvailable');
        expect(getGroupIdDisplay(t, linux, {} as UserGroup)).toBe('GID: common.notAvailable');
    });

    test('a null host is treated as non-Windows', () => {
        expect(getUserIdDisplay(t, null, { uid: 5 } as UserAccount)).toBe('UID: 5');
    });
});

describe('platform predicates', () => {
    test('resolveAntivirusOsName special-cases macOS', () => {
        expect(resolveAntivirusOsName('macOS', '15.1')).toBe('macOS');
    });

    test('resolveAntivirusOsName prefers a named release over the platform', () => {
        expect(resolveAntivirusOsName('Linux', 'Ubuntu 25.04')).toBe('Ubuntu');
    });

    test('resolveAntivirusOsName falls back when the release is a bare version', () => {
        // "7.7" is not a name, so the platform has to supply it.
        expect(resolveAntivirusOsName('FreeBSD', '7.7')).toBe('FreeBSD');
        expect(resolveAntivirusOsName('', '')).toBe('');
    });

    test('isUbuntuHost looks at both platform and release', () => {
        expect(isUbuntuHost('Linux', 'Ubuntu 24.04')).toBe(true);
        expect(isUbuntuHost('ubuntu', null)).toBe(true);
        expect(isUbuntuHost('Debian', 'Debian 12')).toBe(false);
        expect(isUbuntuHost(null, undefined)).toBe(false);
    });

    test('supportsChildHosts is Windows and Linux only', () => {
        expect(supportsChildHosts('Windows Server 2025')).toBe(true);
        expect(supportsChildHosts('Linux')).toBe(true);
        expect(supportsChildHosts('FreeBSD')).toBe(false);
        expect(supportsChildHosts(null)).toBe(false);
    });

    test('isWindowsDistribution matches the install identifier, not a display name', () => {
        // Display names are localized; the identifier is what the engine
        // dispatches on, so only it may be matched.
        expect(isWindowsDistribution('windows-server-2022')).toBe(true);
        expect(isWindowsDistribution('  WINDOWS-SERVER-2025 ')).toBe(true);
        expect(isWindowsDistribution('ubuntu-24.04')).toBe(false);
        expect(isWindowsDistribution(undefined)).toBe(false);
    });
});

describe('resilience helpers', () => {
    test('resolveWithLegacyFallback prefers normalized data', () => {
        expect(resolveWithLegacyFallback([{ a: 1 }], '[{"a":2}]', 'x')).toEqual([{ a: 1 }]);
    });

    test('resolveWithLegacyFallback parses the legacy field when empty', () => {
        expect(resolveWithLegacyFallback<{ a: number }>([], '[{"a":2}]', 'x')).toEqual([{ a: 2 }]);
    });

    test('malformed legacy JSON degrades to the empty list, it does not throw', () => {
        const warn = vi.spyOn(globalThis.console, 'warn').mockImplementation(() => undefined);
        expect(resolveWithLegacyFallback([], '{not json', 'roles')).toEqual([]);
        expect(warn).toHaveBeenCalled();
        warn.mockRestore();
    });

    test('runOptionalFetch swallows a rejection so the page still loads', async () => {
        const log = vi.spyOn(globalThis.console, 'log').mockImplementation(() => undefined);
        await expect(
            runOptionalFetch('optional', () => Promise.reject(new Error('boom'))),
        ).resolves.toBeUndefined();
        expect(log).toHaveBeenCalled();
        log.mockRestore();
    });

    test('runOptionalFetch still awaits the happy path', async () => {
        const fetcher = vi.fn().mockResolvedValue(undefined);
        await runOptionalFetch('optional', fetcher);
        expect(fetcher).toHaveBeenCalledOnce();
    });
});

describe('dates', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-08-25T12:00:00Z'));
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    test('formatTimestamp buckets by age', () => {
        expect(formatTimestamp(t, '2026-08-25T11:59:30Z')).toBe('just now');
        expect(formatTimestamp(t, '2026-08-25T11:30:00Z')).toBe('{{minutes}}m ago');
        expect(formatTimestamp(t, '2026-08-25T06:00:00Z')).toBe('{{hours}}h ago');
        expect(formatTimestamp(t, '2026-08-20T12:00:00Z')).toBe('{{days}}d ago');
    });

    test('formatTimestamp distinguishes "never" from "invalid"', () => {
        // Both render as text, and conflating them hides whether the agent has
        // never reported or reported something unparseable.
        expect(formatTimestamp(t, null)).toBe('never');
        expect(formatTimestamp(t, undefined)).toBe('never');
        expect(formatTimestamp(t, 'not-a-date')).toBe('invalid');
    });

    test('getDisplayStatus uses a 5-minute liveness window', () => {
        expect(getDisplayStatus(host({ last_access: '2026-08-25T11:56:00Z' }))).toBe('up');
        expect(getDisplayStatus(host({ last_access: '2026-08-25T11:54:00Z' }))).toBe('down');
        expect(getDisplayStatus(host({ last_access: undefined }))).toBe('down');
        // null arrives from the API even though the TS type says undefined,
        // so the runtime guard has to cover it too.
        expect(getDisplayStatus({ last_access: null } as unknown as SysManageHost)).toBe('down');
        expect(getDisplayStatus(host({ last_access: 'garbage' }))).toBe('down');
    });

    test('formatDate and formatDateTime return strings for valid input', () => {
        expect(typeof formatDate(t, '2026-08-25T12:00:00Z')).toBe('string');
        expect(formatDate(t, null)).toBe('N/A');
        expect(typeof formatDateTime('2026-08-25T12:00:00Z')).toBe('string');
    });
});
