// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for loggingSettings API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    doGetLoggingSettings,
    doUpdateLoggingSettings,
    UpdateLoggingSettingsRequest,
} from '../loggingSettings';
import api from '../api';

vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        put: vi.fn(),
    },
}));

describe('Logging Settings API Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('doGetLoggingSettings', () => {
        it('fetches logging settings', async () => {
            const data = {
                server: {
                    native_enabled: true,
                    native_target: 'syslog',
                    native_identifier: null,
                    log_level: 'info',
                    verbosity: null,
                },
                server_os_family: 'linux',
                server_valid_targets: ['syslog'],
                agents: {},
                agent_valid_targets: {},
                log_routing_licensed: false,
            };
            vi.mocked(api.get).mockResolvedValueOnce({ data } as never);

            const result = await doGetLoggingSettings();

            expect(result).toEqual(data);
            expect(api.get).toHaveBeenCalledWith('/api/v1/logging-settings');
        });

        it('rethrows on error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(new Error('boom'));
            await expect(doGetLoggingSettings()).rejects.toThrow('boom');
        });
    });

    describe('doUpdateLoggingSettings', () => {
        it('updates logging settings', async () => {
            const payload: UpdateLoggingSettingsRequest = {
                server: {
                    native_enabled: false,
                    native_target: 'file',
                    native_identifier: null,
                    log_level: null,
                    verbosity: null,
                },
            };
            const data = { server: payload.server };
            vi.mocked(api.put).mockResolvedValueOnce({ data } as never);

            const result = await doUpdateLoggingSettings(payload);

            expect(result).toEqual(data);
            expect(api.put).toHaveBeenCalledWith('/api/v1/logging-settings', payload);
        });

        it('rethrows on error', async () => {
            vi.mocked(api.put).mockRejectedValueOnce(new Error('fail'));
            await expect(doUpdateLoggingSettings({})).rejects.toThrow('fail');
        });
    });
});
