// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, afterEach, test, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { TFunction } from 'i18next';

vi.mock('../../../Services/opentelemetry', () => ({
    doCheckOpenTelemetryEligibility: vi.fn(),
    doDeployOpenTelemetry: vi.fn(),
    doGetOpenTelemetryStatus: vi.fn(),
    doStartOpenTelemetry: vi.fn(),
    doStopOpenTelemetry: vi.fn(),
    doRestartOpenTelemetry: vi.fn(),
    doConnectOpenTelemetryToGrafana: vi.fn(),
    doDisconnectOpenTelemetryFromGrafana: vi.fn(),
    doRemoveOpenTelemetry: vi.fn(),
}));

vi.mock('../../../Services/graylog', () => ({
    doCheckGraylogHealth: vi.fn(),
    doGetGraylogAttachment: vi.fn(),
}));

vi.mock('../../../Services/hosts', () => ({
    doGetHostSoftware: vi.fn(),
}));

import * as otel from '../../../Services/opentelemetry';
import * as graylog from '../../../Services/graylog';
import { doGetHostSoftware } from '../../../Services/hosts';
import { useHostObservability } from '../useHostObservability';
import type { SysManageHost } from '../../../Services/hosts';

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

const makeHost = (over: Partial<SysManageHost> = {}): SysManageHost =>
    ({ id: 'h1', active: true, is_agent_privileged: true, ...over } as unknown as SysManageHost);

interface SetupOpts {
    hostId?: string | undefined;
    host?: SysManageHost | null;
    currentTabId?: string;
}

const setup = (opts: SetupOpts = {}) => {
    const setSnackbarMessage = vi.fn();
    const setSnackbarSeverity = vi.fn();
    const setSnackbarOpen = vi.fn();
    const setSoftwarePackages = vi.fn();
    const props = {
        hostId: 'hostId' in opts ? opts.hostId : 'h1',
        host: 'host' in opts ? (opts.host as SysManageHost | null) : makeHost(),
        currentTabId: opts.currentTabId ?? 'overview',
        t,
        setSnackbarMessage,
        setSnackbarSeverity,
        setSnackbarOpen,
        setSoftwarePackages,
    };
    const utils = renderHook((p: typeof props) => useHostObservability(p), { initialProps: props });
    return { ...utils, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen, setSoftwarePackages };
};

describe('useHostObservability', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.useFakeTimers();
        m(otel.doGetOpenTelemetryStatus).mockResolvedValue({ status: 'running' });
        m(otel.doCheckOpenTelemetryEligibility).mockResolvedValue({ has_permission: true, eligible: true });
        m(otel.doStartOpenTelemetry).mockResolvedValue({});
        m(otel.doStopOpenTelemetry).mockResolvedValue({});
        m(otel.doRestartOpenTelemetry).mockResolvedValue({});
        m(otel.doConnectOpenTelemetryToGrafana).mockResolvedValue({});
        m(otel.doDisconnectOpenTelemetryFromGrafana).mockResolvedValue({});
        m(otel.doRemoveOpenTelemetry).mockResolvedValue({});
        m(otel.doDeployOpenTelemetry).mockResolvedValue({ message: 'queued' });
        m(graylog.doCheckGraylogHealth).mockResolvedValue({ healthy: true });
        m(graylog.doGetGraylogAttachment).mockResolvedValue({
            is_attached: true,
            mechanism: 'syslog',
            target_hostname: 'log.host',
            target_ip: '10.0.0.1',
            port: 514,
        });
        m(doGetHostSoftware).mockResolvedValue({ items: [] });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    test('initial state', () => {
        const { result } = setup();
        expect(result.current.openTelemetryStatus).toBeNull();
        expect(result.current.graylogAttached).toBe(false);
        expect(result.current.graylogAttachModalOpen).toBe(false);
    });

    describe('fetchOpenTelemetryStatus', () => {
        test('no hostId → noop', async () => {
            const { result } = setup({ hostId: undefined });
            await act(async () => {
                await result.current.fetchOpenTelemetryStatus();
            });
            expect(otel.doGetOpenTelemetryStatus).not.toHaveBeenCalled();
        });

        test('success sets status', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.fetchOpenTelemetryStatus();
            });
            expect(result.current.openTelemetryStatus).toEqual({ status: 'running' });
        });

        test('error is swallowed', async () => {
            m(otel.doGetOpenTelemetryStatus).mockRejectedValueOnce(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                await result.current.fetchOpenTelemetryStatus();
            });
            expect(result.current.openTelemetryLoading).toBe(false);
        });
    });

    describe('fetchGraylogAttachment', () => {
        test('success sets attachment fields', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.fetchGraylogAttachment();
            });
            expect(result.current.graylogAttached).toBe(true);
            expect(result.current.graylogMechanism).toBe('syslog');
            expect(result.current.graylogPort).toBe(514);
        });

        test('error swallowed', async () => {
            m(graylog.doGetGraylogAttachment).mockRejectedValueOnce(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                await result.current.fetchGraylogAttachment();
            });
            expect(result.current.graylogLoading).toBe(false);
        });
    });

    describe.each([
        ['handleOpenTelemetryStart', 'doStartOpenTelemetry'],
        ['handleOpenTelemetryStop', 'doStopOpenTelemetry'],
        ['handleOpenTelemetryRestart', 'doRestartOpenTelemetry'],
        ['handleOpenTelemetryConnect', 'doConnectOpenTelemetryToGrafana'],
        ['handleOpenTelemetryDisconnect', 'doDisconnectOpenTelemetryFromGrafana'],
        ['handleRemoveOpenTelemetry', 'doRemoveOpenTelemetry'],
    ] as const)('%s', (fnName, svcName) => {
        test('no hostId → noop', async () => {
            const { result } = setup({ hostId: undefined });
            await act(async () => {
                await (result.current[fnName] as () => Promise<void>)();
            });
            expect(m((otel as Record<string, unknown>)[svcName])).not.toHaveBeenCalled();
        });

        test('success shows snackbar and refreshes', async () => {
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await (result.current[fnName] as () => Promise<void>)();
            });
            expect(m((otel as Record<string, unknown>)[svcName])).toHaveBeenCalledWith('h1');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
            await act(async () => {
                await vi.advanceTimersByTimeAsync(2500);
            });
        });

        test('error shows error snackbar', async () => {
            m((otel as Record<string, unknown>)[svcName]).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await (result.current[fnName] as () => Promise<void>)();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });

    describe('graylog attach modal', () => {
        test('open then close refreshes attachment', async () => {
            const { result } = setup();
            act(() => result.current.handleAttachToGraylog());
            expect(result.current.graylogAttachModalOpen).toBe(true);
            await act(async () => {
                result.current.handleGraylogAttachModalClose();
            });
            expect(result.current.graylogAttachModalOpen).toBe(false);
            expect(graylog.doGetGraylogAttachment).toHaveBeenCalled();
        });
    });

    describe('handleDeployOpenTelemetry', () => {
        test('no hostId → noop', async () => {
            const { result } = setup({ hostId: undefined });
            await act(async () => {
                await result.current.handleDeployOpenTelemetry();
            });
            expect(otel.doDeployOpenTelemetry).not.toHaveBeenCalled();
        });

        test('success queues, then refreshes software + eligibility', async () => {
            const { result, setSnackbarSeverity, setSoftwarePackages } = setup();
            await act(async () => {
                await result.current.handleDeployOpenTelemetry();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
            await act(async () => {
                await vi.advanceTimersByTimeAsync(5500);
            });
            expect(doGetHostSoftware).toHaveBeenCalledWith('h1');
            expect(setSoftwarePackages).toHaveBeenCalled();
        });

        test('deploy error shows error snackbar', async () => {
            m(otel.doDeployOpenTelemetry).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleDeployOpenTelemetry();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });

        test('software refresh error is swallowed', async () => {
            m(doGetHostSoftware).mockRejectedValueOnce(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                await result.current.handleDeployOpenTelemetry();
            });
            await act(async () => {
                await vi.advanceTimersByTimeAsync(5500);
            });
            expect(result.current.openTelemetryDeploying).toBe(false);
        });
    });

    describe('effects', () => {
        test('info tab fetches otel + graylog and checks eligibility', async () => {
            setup({ currentTabId: 'info' });
            await act(async () => {
                await vi.advanceTimersByTimeAsync(100);
            });
            expect(otel.doGetOpenTelemetryStatus).toHaveBeenCalled();
            expect(graylog.doGetGraylogAttachment).toHaveBeenCalled();
            expect(otel.doCheckOpenTelemetryEligibility).toHaveBeenCalled();
            expect(graylog.doCheckGraylogHealth).toHaveBeenCalled();
        });

        test('info tab auto-refresh interval fires', async () => {
            setup({ currentTabId: 'info' });
            await act(async () => {
                await vi.advanceTimersByTimeAsync(100);
            });
            m(otel.doGetOpenTelemetryStatus).mockClear();
            await act(async () => {
                await vi.advanceTimersByTimeAsync(30000);
            });
            expect(otel.doGetOpenTelemetryStatus).toHaveBeenCalled();
        });

        test('inactive host disables eligibility', async () => {
            const { result } = setup({ host: makeHost({ active: false }) });
            await act(async () => {
                await vi.advanceTimersByTimeAsync(100);
            });
            expect(result.current.canDeployOpenTelemetry).toBe(false);
            expect(result.current.openTelemetryEligible).toBe(false);
        });

        test('eligibility check error path', async () => {
            m(otel.doCheckOpenTelemetryEligibility).mockRejectedValue(new Error('boom'));
            m(graylog.doCheckGraylogHealth).mockRejectedValue(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                await vi.advanceTimersByTimeAsync(100);
            });
            expect(result.current.canDeployOpenTelemetry).toBe(false);
            expect(result.current.canAttachGraylog).toBe(false);
        });
    });
});
