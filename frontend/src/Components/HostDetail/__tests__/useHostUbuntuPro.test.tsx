// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, afterEach, test, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { TFunction } from 'i18next';

vi.mock('../../../Services/api', () => ({
    default: { get: vi.fn() },
}));

vi.mock('../../../Services/hosts', () => ({
    doGetHostUbuntuPro: vi.fn(),
    doAttachUbuntuPro: vi.fn(),
    doDetachUbuntuPro: vi.fn(),
    doEnableUbuntuProService: vi.fn(),
    doDisableUbuntuProService: vi.fn(),
}));

import axiosInstance from '../../../Services/api';
import * as hosts from '../../../Services/hosts';
import { useHostUbuntuPro } from '../useHostUbuntuPro';
import type { SysManageHost, UbuntuProInfo } from '../../../Services/hosts';

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

const makeHost = (over: Partial<SysManageHost> = {}): SysManageHost =>
    ({ id: 'h1', active: true, ...over } as unknown as SysManageHost);

const proInfo = (over: Partial<UbuntuProInfo> = {}): UbuntuProInfo =>
    ({
        available: true,
        attached: true,
        services: [
            { name: 'esm-infra', status: 'enabled' },
            { name: 'livepatch', status: 'disabled' },
            { name: 'fips', status: 'n/a' },
        ],
        ...over,
    } as unknown as UbuntuProInfo);

interface SetupOpts {
    hostId?: string | undefined;
    host?: SysManageHost | null;
    ubuntuProInfo?: UbuntuProInfo | null;
    isUbuntu?: () => boolean;
}

const setup = (opts: SetupOpts = {}) => {
    const setUbuntuProInfo = vi.fn();
    const setSnackbarMessage = vi.fn();
    const setSnackbarSeverity = vi.fn();
    const setSnackbarOpen = vi.fn();
    const props = {
        hostId: 'hostId' in opts ? opts.hostId : 'h1',
        host: 'host' in opts ? (opts.host as SysManageHost | null) : makeHost(),
        ubuntuProInfo: 'ubuntuProInfo' in opts ? (opts.ubuntuProInfo as UbuntuProInfo | null) : proInfo(),
        setUbuntuProInfo,
        isUbuntu: opts.isUbuntu ?? (() => true),
        t,
        setSnackbarMessage,
        setSnackbarSeverity,
        setSnackbarOpen,
    };
    const utils = renderHook((p: typeof props) => useHostUbuntuPro(p), { initialProps: props });
    return { ...utils, setUbuntuProInfo, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen };
};

describe('useHostUbuntuPro', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.useFakeTimers();
        mockGet.mockResolvedValue({ data: { master_key: '' } });
        m(hosts.doGetHostUbuntuPro).mockResolvedValue(proInfo({ attached: true }));
        m(hosts.doAttachUbuntuPro).mockResolvedValue({});
        m(hosts.doDetachUbuntuPro).mockResolvedValue({});
        m(hosts.doEnableUbuntuProService).mockResolvedValue({});
        m(hosts.doDisableUbuntuProService).mockResolvedValue({});
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    test('auto-refresh polls Ubuntu Pro info every 30s', async () => {
        const { setUbuntuProInfo } = setup();
        await act(async () => {
            await vi.advanceTimersByTimeAsync(30000);
        });
        expect(hosts.doGetHostUbuntuPro).toHaveBeenCalledWith('h1');
        expect(setUbuntuProInfo).toHaveBeenCalled();
    });

    describe('attach', () => {
        test('master key present → attach directly + poll', async () => {
            mockGet.mockResolvedValueOnce({ data: { master_key: 'MASTER' } });
            m(hosts.doGetHostUbuntuPro).mockResolvedValue(proInfo({ attached: true }));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleUbuntuProAttach();
            });
            expect(hosts.doAttachUbuntuPro).toHaveBeenCalledWith('h1', 'MASTER');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
            await act(async () => {
                await vi.advanceTimersByTimeAsync(2500);
            });
        });

        test('master key attach failure → error snackbar', async () => {
            mockGet.mockResolvedValueOnce({ data: { master_key: 'MASTER' } });
            m(hosts.doAttachUbuntuPro).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleUbuntuProAttach();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });

        test('no master key → opens token dialog', async () => {
            mockGet.mockResolvedValueOnce({ data: { master_key: '' } });
            const { result } = setup();
            await act(async () => {
                await result.current.handleUbuntuProAttach();
            });
            expect(result.current.ubuntuProTokenDialog).toBe(true);
        });

        test('get error → opens token dialog', async () => {
            mockGet.mockRejectedValueOnce(new Error('boom'));
            const { result } = setup();
            await act(async () => {
                await result.current.handleUbuntuProAttach();
            });
            expect(result.current.ubuntuProTokenDialog).toBe(true);
        });
    });

    describe('token submit', () => {
        test('guard on empty token', async () => {
            const { result } = setup();
            await act(async () => {
                await result.current.handleUbuntuProTokenSubmit();
            });
            expect(hosts.doAttachUbuntuPro).not.toHaveBeenCalled();
        });

        test('success', async () => {
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.setUbuntuProToken('TOKEN123'));
            await act(async () => {
                await result.current.handleUbuntuProTokenSubmit();
            });
            expect(hosts.doAttachUbuntuPro).toHaveBeenCalledWith('h1', 'TOKEN123');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('error', async () => {
            m(hosts.doAttachUbuntuPro).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.setUbuntuProToken('TOKEN123'));
            await act(async () => {
                await result.current.handleUbuntuProTokenSubmit();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });

        test('cancel resets', () => {
            const { result } = setup();
            act(() => result.current.setUbuntuProToken('X'));
            act(() => result.current.handleUbuntuProTokenCancel());
            expect(result.current.ubuntuProToken).toBe('');
            expect(result.current.ubuntuProTokenDialog).toBe(false);
        });
    });

    describe('detach', () => {
        test('open confirm then cancel', () => {
            const { result } = setup();
            act(() => result.current.handleUbuntuProDetach());
            expect(result.current.ubuntuProDetachConfirmOpen).toBe(true);
            act(() => result.current.handleCancelUbuntuProDetach());
            expect(result.current.ubuntuProDetachConfirmOpen).toBe(false);
        });

        test('confirm guard when no host', async () => {
            const { result } = setup({ host: null });
            await act(async () => {
                await result.current.handleConfirmUbuntuProDetach();
            });
            expect(hosts.doDetachUbuntuPro).not.toHaveBeenCalled();
        });

        test('confirm success polls until detached', async () => {
            m(hosts.doGetHostUbuntuPro).mockResolvedValue(proInfo({ attached: false }));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleConfirmUbuntuProDetach();
            });
            expect(hosts.doDetachUbuntuPro).toHaveBeenCalledWith('h1');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
            await act(async () => {
                await vi.advanceTimersByTimeAsync(2500);
            });
        });

        test('confirm error', async () => {
            m(hosts.doDetachUbuntuPro).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            await act(async () => {
                await result.current.handleConfirmUbuntuProDetach();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });

    describe('services editing', () => {
        test('getEditedServiceLabel reflects status and edits', () => {
            const { result } = setup();
            expect(result.current.getEditedServiceLabel('esm-infra', 'enabled')).toBe('Enabled');
            expect(result.current.getEditedServiceLabel('livepatch', 'disabled')).toBe('Disabled');
        });

        test('edit toggle initializes and cancels', () => {
            const { result } = setup();
            act(() => result.current.handleServicesEditToggle());
            expect(result.current.servicesEditMode).toBe(true);
            expect(result.current.editedServices).toEqual({ 'esm-infra': true, livepatch: false });
            act(() => result.current.handleServicesEditToggle());
            expect(result.current.servicesEditMode).toBe(false);
            expect(result.current.editedServices).toEqual({});
        });

        test('handleServiceToggle updates edited map', () => {
            const { result } = setup();
            act(() => result.current.handleServiceToggle('livepatch', true));
            expect(result.current.editedServices.livepatch).toBe(true);
        });

        test('save applies enable/disable changes', async () => {
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleServicesEditToggle());
            act(() => result.current.handleServiceToggle('esm-infra', false)); // was enabled → disable
            act(() => result.current.handleServiceToggle('livepatch', true)); // was disabled → enable
            await act(async () => {
                await result.current.handleServicesSave();
            });
            expect(hosts.doDisableUbuntuProService).toHaveBeenCalledWith('h1', 'esm-infra');
            expect(hosts.doEnableUbuntuProService).toHaveBeenCalledWith('h1', 'livepatch');
            expect(setSnackbarSeverity).toHaveBeenCalledWith('success');
        });

        test('save with no changes shows no-changes message', async () => {
            const { result } = setup();
            act(() => result.current.handleServicesEditToggle());
            await act(async () => {
                await result.current.handleServicesSave();
            });
            expect(result.current.servicesMessage).toContain('No changes');
        });

        test('save guard when no ubuntuProInfo', async () => {
            const { result } = setup({ ubuntuProInfo: null });
            await act(async () => {
                await result.current.handleServicesSave();
            });
            expect(hosts.doEnableUbuntuProService).not.toHaveBeenCalled();
        });

        test('save error path', async () => {
            m(hosts.doDisableUbuntuProService).mockRejectedValueOnce(new Error('boom'));
            const { result, setSnackbarSeverity } = setup();
            act(() => result.current.handleServicesEditToggle());
            act(() => result.current.handleServiceToggle('esm-infra', false));
            await act(async () => {
                await result.current.handleServicesSave();
            });
            expect(setSnackbarSeverity).toHaveBeenCalledWith('error');
        });
    });
});
