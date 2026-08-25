// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { describe, test, expect } from 'vitest';

import {
    buildAllShells,
    buildPlatforms,
    getShellsForPlatform,
    normalizePlatform,
    doPlatformsMatch,
    hostHasShellEnabled,
    isHostCompatibleWithScript,
    isHostConnected,
    getStatusColor,
    buildDataGridLocaleText,
    getLanguageForShell,
    getShellHeader,
} from '../scriptsHelpers';
import type { Host, Script } from '../../../Services/scripts';

// Echo the key: these labels are i18n lookups, and echoing makes it obvious
// in a failure which key was asked for.
const t = (key: string) => key;

const host = (over: Partial<Host> = {}): Host =>
    ({
        id: 'h1',
        fqdn: 'h.example.test',
        status: 'up',
        active: true,
        platform: 'Linux',
        script_execution_enabled: true,
        enabled_shells: JSON.stringify(['bash', 'sh']),
        ...over,
    }) as unknown as Host;

const script = (over: Partial<Script> = {}): Script =>
    ({ id: 's1', name: 'x', shell_type: 'bash', platform: 'linux', ...over }) as unknown as Script;

describe('catalogs', () => {
    test('every shell lists at least one platform, and cmd is Windows-only', () => {
        const shells = buildAllShells(t);
        expect(shells.length).toBeGreaterThan(0);
        for (const s of shells) expect(s.platforms.length).toBeGreaterThan(0);
        expect(shells.find(s => s.value === 'cmd')?.platforms).toEqual(['windows']);
    });

    test('getShellsForPlatform filters by platform membership', () => {
        const shells = buildAllShells(t);
        const win = getShellsForPlatform(shells, 'windows').map(s => s.value);
        expect(win).toContain('powershell');
        expect(win).toContain('cmd');
        expect(win).not.toContain('bash');

        const obsd = getShellsForPlatform(shells, 'openbsd').map(s => s.value);
        expect(obsd).toContain('ksh');
        expect(obsd).not.toContain('cmd');
    });

    test('an unknown platform yields no shells rather than everything', () => {
        expect(getShellsForPlatform(buildAllShells(t), 'plan9')).toEqual([]);
    });

    test('buildPlatforms covers the supported OS set', () => {
        const values = buildPlatforms(t).map(p => p.value);
        expect(values).toEqual(
            expect.arrayContaining(['linux', 'darwin', 'windows', 'freebsd', 'openbsd', 'netbsd']),
        );
    });
});

describe('platform normalisation', () => {
    test.each([
        ['Windows', 'windows'],
        ['win32', 'windows'],
        ['WIN', 'windows'],
        ['darwin', 'darwin'],
        ['FreeBSD', 'freebsd'],
        ['OpenBSD', 'openbsd'],
        ['NetBSD', 'netbsd'],
        ['Ubuntu', 'linux'],
        ['', 'linux'],
    ])('normalizePlatform(%s) -> %s', (input, expected) => {
        expect(normalizePlatform(input)).toBe(expected);
    });

    test('an unknown OS defaults to linux, not to a mismatch', () => {
        // Defaulting to linux keeps a Unix-like host usable rather than
        // silently excluding it from every script.
        expect(normalizePlatform('SunOS')).toBe('linux');
    });

    test('doPlatformsMatch treats missing information as compatible', () => {
        // An unknown platform must not block execution; the shell check still
        // has to pass, so this is permissive rather than unsafe.
        expect(doPlatformsMatch(undefined, 'Linux')).toBe(true);
        expect(doPlatformsMatch('linux', undefined)).toBe(true);
        expect(doPlatformsMatch('linux', 'Ubuntu')).toBe(true);
        expect(doPlatformsMatch('windows', 'Ubuntu')).toBe(false);
        expect(doPlatformsMatch('windows', 'win32')).toBe(true);
    });
});

describe('host shell capability', () => {
    test('reads the JSON list case-insensitively', () => {
        expect(hostHasShellEnabled(host({ enabled_shells: '["Bash"]' }), 'bash')).toBe(true);
        expect(hostHasShellEnabled(host(), 'zsh')).toBe(false);
    });

    test('missing or malformed enabled_shells is NOT compatible', () => {
        // Failing closed matters: guessing "probably has bash" would dispatch a
        // script to a host that cannot run it.
        expect(hostHasShellEnabled(host({ enabled_shells: undefined }), 'bash')).toBe(false);
        expect(hostHasShellEnabled(host({ enabled_shells: 'not json' }), 'bash')).toBe(false);
    });
});

describe('host/script compatibility', () => {
    test('all three conditions must hold', () => {
        expect(isHostCompatibleWithScript(host(), script())).toBe(true);
    });

    test('execution disabled on the host blocks everything else', () => {
        expect(
            isHostCompatibleWithScript(host({ script_execution_enabled: false }), script()),
        ).toBe(false);
    });

    test('a platform mismatch blocks even when the shell exists', () => {
        expect(
            isHostCompatibleWithScript(host({ platform: 'Windows' }), script({ platform: 'linux' })),
        ).toBe(false);
    });

    test('a missing shell blocks even when the platform matches', () => {
        expect(
            isHostCompatibleWithScript(host({ enabled_shells: '["sh"]' }), script({ shell_type: 'zsh' })),
        ).toBe(false);
    });
});

describe('connectivity + status', () => {
    test('isHostConnected needs BOTH up and active', () => {
        expect(isHostConnected(host())).toBe(true);
        expect(isHostConnected(host({ status: 'down' }))).toBe(false);
        expect(isHostConnected(host({ active: false }))).toBe(false);
    });

    test.each([
        ['pending', 'default'],
        ['running', 'info'],
        ['completed', 'success'],
        ['failed', 'error'],
        ['timeout', 'warning'],
        ['something-new', 'default'],
    ])('getStatusColor(%s) -> %s', (status, expected) => {
        expect(getStatusColor(status)).toBe(expected);
    });
});

describe('grid locale text', () => {
    test('row-count label handles the unknown-total case', () => {
        const lt = buildDataGridLocaleText(t, 'nothing here');
        const label = lt.MuiTablePagination.labelDisplayedRows;
        expect(label({ from: 1, to: 10, count: 42 })).toBe('1-10 common.of 42');
        // count === -1 means "total unknown".  NOTE the doubled label: the
        // source builds countDisplay as `of <to>` and then prepends `of` again,
        // so a real locale renders "1-10 of of 10".  Pinned as CURRENT
        // behaviour, not as desired behaviour -- MUI's own convention here is
        // "1-10 of more than 10".  See ROADMAP Phase 19 coverage note.
        expect(label({ from: 1, to: 10, count: -1 })).toBe('1-10 common.of common.of 10');
    });

    test('selection footer is singular for exactly one row', () => {
        const lt = buildDataGridLocaleText(t, 'nothing here');
        expect(lt.footerRowSelected(1)).toContain('common.rowSelected');
        expect(lt.footerRowSelected(2)).toContain('common.rowsSelected');
        expect(lt.noRowsLabel).toBe('nothing here');
        expect(lt.noResultsOverlayLabel).toBe('nothing here');
    });
});

describe('editor affordances', () => {
    test.each([
        ['bash', 'shell'],
        ['sh', 'shell'],
        ['zsh', 'shell'],
        ['ksh', 'shell'],
        ['powershell', 'powershell'],
        ['cmd', 'bat'],
        ['unknown', 'shell'],
    ])('getLanguageForShell(%s) -> %s', (shell, expected) => {
        expect(getLanguageForShell(shell)).toBe(expected);
    });

    test('bash shebang follows the BSD path convention', () => {
        // /bin/bash does not exist on the BSDs; emitting it would produce a
        // script that fails at exec time rather than at save time.
        expect(getShellHeader('bash', 'linux')).toBe('#!/bin/bash\n\n');
        expect(getShellHeader('bash', 'darwin')).toBe('#!/bin/bash\n\n');
        for (const bsd of ['freebsd', 'openbsd', 'netbsd']) {
            expect(getShellHeader('bash', bsd)).toBe('#!/usr/local/bin/bash\n\n');
        }
        expect(getShellHeader('bash', 'plan9')).toBe('#!/bin/bash\n\n');
    });

    test('sh is /bin/sh everywhere', () => {
        for (const p of ['linux', 'darwin', 'freebsd', 'openbsd', 'netbsd']) {
            expect(getShellHeader('sh', p)).toBe('#!/bin/sh\n\n');
        }
    });

    test('zsh and ksh differ per BSD, and OpenBSD ships ksh in /bin', () => {
        expect(getShellHeader('zsh', 'linux')).toBe('#!/bin/zsh\n\n');
        expect(getShellHeader('zsh', 'freebsd')).toBe('#!/usr/local/bin/zsh\n\n');
        expect(getShellHeader('zsh', 'plan9')).toBe('#!/bin/zsh\n\n');
        expect(getShellHeader('ksh', 'linux')).toBe('#!/bin/ksh\n\n');
        expect(getShellHeader('ksh', 'freebsd')).toBe('#!/usr/local/bin/ksh\n\n');
        // ksh is the DEFAULT shell on OpenBSD, so it lives in /bin there.
        expect(getShellHeader('ksh', 'openbsd')).toBe('#!/bin/ksh\n\n');
        expect(getShellHeader('ksh', 'plan9')).toBe('#!/bin/ksh\n\n');
    });

    test('windows shells get comments, not shebangs', () => {
        expect(getShellHeader('powershell', 'windows')).toBe('# PowerShell Script\n\n');
        expect(getShellHeader('cmd', 'windows')).toBe('@echo off\nREM Windows Batch Script\n\n');
        expect(getShellHeader('nonsense', 'linux')).toBe('#!/bin/bash\n\n');
    });
});
