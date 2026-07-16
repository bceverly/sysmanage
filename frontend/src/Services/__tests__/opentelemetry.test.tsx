// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for OpenTelemetry API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    doCheckOpenTelemetryEligibility,
    doDeployOpenTelemetry,
    doGetOpenTelemetryStatus,
    doStartOpenTelemetry,
    doStopOpenTelemetry,
    doRestartOpenTelemetry,
    doConnectOpenTelemetryToGrafana,
    doDisconnectOpenTelemetryFromGrafana,
    doRemoveOpenTelemetry,
} from '../opentelemetry';
import api from '../api';

// Mock axios instance
vi.mock('../api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

const okResponse = (data: unknown) => ({
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {} as any,
});

// An axios error with a response body (has .response.data.detail).
const axiosErrorWithDetail = (detail: string) => ({
    response: { data: { detail } },
});

// An axios error with a response but no detail.
const axiosErrorNoDetail = () => ({
    response: { data: {} },
});

// A network error (no response).
const networkError = () => ({ request: {} });

describe('OpenTelemetry API Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('doCheckOpenTelemetryEligibility', () => {
        it('fetches eligibility successfully', async () => {
            const mock = {
                eligible: true,
                grafana_enabled: true,
                opentelemetry_installed: false,
                agent_privileged: true,
            };
            vi.mocked(api.get).mockResolvedValueOnce(okResponse(mock));

            const result = await doCheckOpenTelemetryEligibility('42');

            expect(result).toEqual(mock);
            expect(api.get).toHaveBeenCalledWith(
                '/api/v1/opentelemetry/hosts/42/opentelemetry-eligible',
            );
        });

        it('throws detail message on response error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(
                axiosErrorWithDetail('boom'),
            );
            await expect(doCheckOpenTelemetryEligibility('1')).rejects.toThrow(
                'boom',
            );
        });

        it('throws default message when response has no detail', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(axiosErrorNoDetail());
            await expect(doCheckOpenTelemetryEligibility('1')).rejects.toThrow(
                'Failed to check OpenTelemetry eligibility',
            );
        });

        it('throws network error message when no response', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(networkError());
            await expect(doCheckOpenTelemetryEligibility('1')).rejects.toThrow(
                'Network error while checking OpenTelemetry eligibility',
            );
        });
    });

    describe('doDeployOpenTelemetry', () => {
        it('deploys successfully', async () => {
            const mock = { success: true, message: 'deployed' };
            vi.mocked(api.post).mockResolvedValueOnce(okResponse(mock));

            const result = await doDeployOpenTelemetry('7');

            expect(result).toEqual(mock);
            expect(api.post).toHaveBeenCalledWith(
                '/api/v1/opentelemetry/hosts/7/deploy-opentelemetry',
            );
        });

        it('throws detail message on response error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(
                axiosErrorWithDetail('deploy fail'),
            );
            await expect(doDeployOpenTelemetry('7')).rejects.toThrow(
                'deploy fail',
            );
        });

        it('throws default message when response has no detail', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(axiosErrorNoDetail());
            await expect(doDeployOpenTelemetry('7')).rejects.toThrow(
                'Failed to deploy OpenTelemetry',
            );
        });

        it('throws network error message when no response', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(networkError());
            await expect(doDeployOpenTelemetry('7')).rejects.toThrow(
                'Network error while deploying OpenTelemetry',
            );
        });
    });

    describe('doGetOpenTelemetryStatus', () => {
        it('gets status successfully', async () => {
            const mock = {
                deployed: true,
                service_status: 'running',
                grafana_url: 'http://g',
                grafana_configured: true,
            };
            vi.mocked(api.get).mockResolvedValueOnce(okResponse(mock));

            const result = await doGetOpenTelemetryStatus('9');

            expect(result).toEqual(mock);
            expect(api.get).toHaveBeenCalledWith(
                '/api/v1/opentelemetry/hosts/9/opentelemetry-status',
            );
        });

        it('throws detail message on response error', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(
                axiosErrorWithDetail('status fail'),
            );
            await expect(doGetOpenTelemetryStatus('9')).rejects.toThrow(
                'status fail',
            );
        });

        it('throws default message when response has no detail', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(axiosErrorNoDetail());
            await expect(doGetOpenTelemetryStatus('9')).rejects.toThrow(
                'Failed to get OpenTelemetry status',
            );
        });

        it('throws network error message when no response', async () => {
            vi.mocked(api.get).mockRejectedValueOnce(networkError());
            await expect(doGetOpenTelemetryStatus('9')).rejects.toThrow(
                'Network error while getting OpenTelemetry status',
            );
        });
    });

    describe('doStartOpenTelemetry', () => {
        it('starts successfully', async () => {
            const mock = { success: true, message: 'started' };
            vi.mocked(api.post).mockResolvedValueOnce(okResponse(mock));

            const result = await doStartOpenTelemetry('3');

            expect(result).toEqual(mock);
            expect(api.post).toHaveBeenCalledWith(
                '/api/v1/opentelemetry/hosts/3/opentelemetry/start',
            );
        });

        it('throws detail message on response error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(
                axiosErrorWithDetail('start fail'),
            );
            await expect(doStartOpenTelemetry('3')).rejects.toThrow(
                'start fail',
            );
        });

        it('throws network error message when no response', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(networkError());
            await expect(doStartOpenTelemetry('3')).rejects.toThrow(
                'Network error while starting OpenTelemetry',
            );
        });
    });

    describe('doStopOpenTelemetry', () => {
        it('stops successfully', async () => {
            const mock = { success: true, message: 'stopped' };
            vi.mocked(api.post).mockResolvedValueOnce(okResponse(mock));

            const result = await doStopOpenTelemetry('4');

            expect(result).toEqual(mock);
            expect(api.post).toHaveBeenCalledWith(
                '/api/v1/opentelemetry/hosts/4/opentelemetry/stop',
            );
        });

        it('throws detail message on response error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(
                axiosErrorWithDetail('stop fail'),
            );
            await expect(doStopOpenTelemetry('4')).rejects.toThrow('stop fail');
        });

        it('throws network error message when no response', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(networkError());
            await expect(doStopOpenTelemetry('4')).rejects.toThrow(
                'Network error while stopping OpenTelemetry',
            );
        });
    });

    describe('doRestartOpenTelemetry', () => {
        it('restarts successfully', async () => {
            const mock = { success: true, message: 'restarted' };
            vi.mocked(api.post).mockResolvedValueOnce(okResponse(mock));

            const result = await doRestartOpenTelemetry('5');

            expect(result).toEqual(mock);
            expect(api.post).toHaveBeenCalledWith(
                '/api/v1/opentelemetry/hosts/5/opentelemetry/restart',
            );
        });

        it('throws detail message on response error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(
                axiosErrorWithDetail('restart fail'),
            );
            await expect(doRestartOpenTelemetry('5')).rejects.toThrow(
                'restart fail',
            );
        });

        it('throws network error message when no response', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(networkError());
            await expect(doRestartOpenTelemetry('5')).rejects.toThrow(
                'Network error while restarting OpenTelemetry',
            );
        });
    });

    describe('doConnectOpenTelemetryToGrafana', () => {
        it('connects successfully', async () => {
            const mock = { success: true, message: 'connected' };
            vi.mocked(api.post).mockResolvedValueOnce(okResponse(mock));

            const result = await doConnectOpenTelemetryToGrafana('6');

            expect(result).toEqual(mock);
            expect(api.post).toHaveBeenCalledWith(
                '/api/v1/opentelemetry/hosts/6/opentelemetry/connect',
            );
        });

        it('throws detail message on response error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(
                axiosErrorWithDetail('connect fail'),
            );
            await expect(doConnectOpenTelemetryToGrafana('6')).rejects.toThrow(
                'connect fail',
            );
        });

        it('throws network error message when no response', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(networkError());
            await expect(doConnectOpenTelemetryToGrafana('6')).rejects.toThrow(
                'Network error while connecting OpenTelemetry to Grafana',
            );
        });
    });

    describe('doDisconnectOpenTelemetryFromGrafana', () => {
        it('disconnects successfully', async () => {
            const mock = { success: true, message: 'disconnected' };
            vi.mocked(api.post).mockResolvedValueOnce(okResponse(mock));

            const result = await doDisconnectOpenTelemetryFromGrafana('8');

            expect(result).toEqual(mock);
            expect(api.post).toHaveBeenCalledWith(
                '/api/v1/opentelemetry/hosts/8/opentelemetry/disconnect',
            );
        });

        it('throws detail message on response error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(
                axiosErrorWithDetail('disconnect fail'),
            );
            await expect(
                doDisconnectOpenTelemetryFromGrafana('8'),
            ).rejects.toThrow('disconnect fail');
        });

        it('throws network error message when no response', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(networkError());
            await expect(
                doDisconnectOpenTelemetryFromGrafana('8'),
            ).rejects.toThrow(
                'Network error while disconnecting OpenTelemetry from Grafana',
            );
        });
    });

    describe('doRemoveOpenTelemetry', () => {
        it('removes successfully', async () => {
            const mock = { success: true, message: 'removed' };
            vi.mocked(api.post).mockResolvedValueOnce(okResponse(mock));

            const result = await doRemoveOpenTelemetry('10');

            expect(result).toEqual(mock);
            expect(api.post).toHaveBeenCalledWith(
                '/api/v1/opentelemetry/hosts/10/remove-opentelemetry',
            );
        });

        it('throws detail message on response error', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(
                axiosErrorWithDetail('remove fail'),
            );
            await expect(doRemoveOpenTelemetry('10')).rejects.toThrow(
                'remove fail',
            );
        });

        it('throws default message when response has no detail', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(axiosErrorNoDetail());
            await expect(doRemoveOpenTelemetry('10')).rejects.toThrow(
                'Failed to remove OpenTelemetry',
            );
        });

        it('throws network error message when no response', async () => {
            vi.mocked(api.post).mockRejectedValueOnce(networkError());
            await expect(doRemoveOpenTelemetry('10')).rejects.toThrow(
                'Network error while removing OpenTelemetry',
            );
        });
    });
});
