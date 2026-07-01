import api from './api';

export interface LoggingConfig {
    native_enabled: boolean;
    native_target: string;
    native_identifier: string | null;
    log_level: string | null;
    verbosity: string | null;
}

export interface LoggingSettingsResponse {
    server: LoggingConfig;
    server_os_family: string;
    server_valid_targets: string[];
    agents: Record<string, LoggingConfig | null>;
    agent_valid_targets: Record<string, string[]>;
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
