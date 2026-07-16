// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import api from './api';

export interface LoggingConfig {
    native_enabled: boolean;
    native_target: string;
    native_identifier: string | null;
    log_level: string | null;
    verbosity: string | null;
    // Remote-syslog forwarding (Phase 14.5) — only used when
    // native_target === 'syslog_remote'; gated behind LOG_ROUTING (Professional).
    syslog_host?: string | null;
    syslog_port?: number | null;
    syslog_facility?: string | null;
    syslog_protocol?: string | null;
}

export interface LoggingSettingsResponse {
    server: LoggingConfig;
    server_os_family: string;
    server_valid_targets: string[];
    agents: Record<string, LoggingConfig | null>;
    agent_valid_targets: Record<string, string[]>;
    // True when the Professional LOG_ROUTING feature is licensed; the UI offers
    // the syslog_remote target but disables it with a hint when this is false.
    log_routing_licensed: boolean;
}

export interface UpdateLoggingSettingsRequest {
    server?: LoggingConfig;
    agents?: Record<string, LoggingConfig>;
}

export const doGetLoggingSettings = async (): Promise<LoggingSettingsResponse> => {
    const response = await api.get<LoggingSettingsResponse>('/api/v1/logging-settings');
    return response.data;
};

export const doUpdateLoggingSettings = async (
    payload: UpdateLoggingSettingsRequest,
): Promise<LoggingSettingsResponse> => {
    const response = await api.put<LoggingSettingsResponse>(
        '/api/v1/logging-settings',
        payload,
    );
    return response.data;
};
