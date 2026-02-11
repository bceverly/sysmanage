import { AxiosError } from 'axios'

import api from './api'

type OpenTelemetryEligibilityResponse = {
    eligible: boolean;
    grafana_enabled: boolean;
    opentelemetry_installed: boolean;
    agent_privileged: boolean;
    has_permission?: boolean;
    error_message?: string;
}

type OpenTelemetryDeployResponse = {
    success: boolean;
    message: string;
}

type OpenTelemetryStatusResponse = {
    deployed: boolean;
    service_status: string; // "running", "stopped", "unknown"
    grafana_url: string | null;
    grafana_configured: boolean;
}

/**
 * Check if a host is eligible for OpenTelemetry deployment
 * @param hostId - The ID of the host to check
 * @returns Promise with eligibility information
 */
export const doCheckOpenTelemetryEligibility = async (
    hostId: string
): Promise<OpenTelemetryEligibilityResponse> => {
    try {
        const response = await api.get<OpenTelemetryEligibilityResponse>(
            `/api/opentelemetry/hosts/${hostId}/opentelemetry-eligible`
        )
        return response.data
    } catch (error) {
        const axiosError = error as AxiosError
        if (axiosError.response) {
            throw new Error(
                (axiosError.response.data as { detail?: string })?.detail ||
                'Failed to check OpenTelemetry eligibility'
            )
        }
        throw new Error('Network error while checking OpenTelemetry eligibility')
    }
}

/**
 * Deploy OpenTelemetry to a specific host
 * @param hostId - The ID of the host to deploy to
 * @returns Promise with deployment result
 */
export const doDeployOpenTelemetry = async (
    hostId: string
): Promise<OpenTelemetryDeployResponse> => {
    try {
        const response = await api.post<OpenTelemetryDeployResponse>(
            `/api/opentelemetry/hosts/${hostId}/deploy-opentelemetry`
        )
        return response.data
    } catch (error) {
        const axiosError = error as AxiosError
        if (axiosError.response) {
            throw new Error(
                (axiosError.response.data as { detail?: string })?.detail ||
                'Failed to deploy OpenTelemetry'
            )
        }
        throw new Error('Network error while deploying OpenTelemetry')
    }
}

/**
 * Get OpenTelemetry status for a specific host
 * @param hostId - The ID of the host to check
 * @returns Promise with status information
 */
export const doGetOpenTelemetryStatus = async (
    hostId: string
): Promise<OpenTelemetryStatusResponse> => {
    try {
        const response = await api.get<OpenTelemetryStatusResponse>(
            `/api/opentelemetry/hosts/${hostId}/opentelemetry-status`
        )
        return response.data
    } catch (error) {
        const axiosError = error as AxiosError
        if (axiosError.response) {
            throw new Error(
                (axiosError.response.data as { detail?: string })?.detail ||
                'Failed to get OpenTelemetry status'
            )
        }
        throw new Error('Network error while getting OpenTelemetry status')
    }
}

/**
 * Start OpenTelemetry service on a specific host
 * @param hostId - The ID of the host
 * @returns Promise with operation result
 */
export const doStartOpenTelemetry = async (
    hostId: string
): Promise<OpenTelemetryDeployResponse> => {
    try {
        const response = await api.post<OpenTelemetryDeployResponse>(
            `/api/opentelemetry/hosts/${hostId}/opentelemetry/start`
        )
        return response.data
    } catch (error) {
        const axiosError = error as AxiosError
        if (axiosError.response) {
            throw new Error(
                (axiosError.response.data as { detail?: string })?.detail ||
                'Failed to start OpenTelemetry'
            )
        }
        throw new Error('Network error while starting OpenTelemetry')
    }
}

/**
 * Stop OpenTelemetry service on a specific host
 * @param hostId - The ID of the host
 * @returns Promise with operation result
 */
export const doStopOpenTelemetry = async (
    hostId: string
): Promise<OpenTelemetryDeployResponse> => {
    try {
        const response = await api.post<OpenTelemetryDeployResponse>(
            `/api/opentelemetry/hosts/${hostId}/opentelemetry/stop`
        )
        return response.data
    } catch (error) {
        const axiosError = error as AxiosError
        if (axiosError.response) {
            throw new Error(
                (axiosError.response.data as { detail?: string })?.detail ||
                'Failed to stop OpenTelemetry'
            )
        }
        throw new Error('Network error while stopping OpenTelemetry')
    }
}

/**
 * Restart OpenTelemetry service on a specific host
 * @param hostId - The ID of the host
 * @returns Promise with operation result
 */
export const doRestartOpenTelemetry = async (
    hostId: string
): Promise<OpenTelemetryDeployResponse> => {
    try {
        const response = await api.post<OpenTelemetryDeployResponse>(
            `/api/opentelemetry/hosts/${hostId}/opentelemetry/restart`
        )
        return response.data
    } catch (error) {
        const axiosError = error as AxiosError
        if (axiosError.response) {
            throw new Error(
                (axiosError.response.data as { detail?: string })?.detail ||
                'Failed to restart OpenTelemetry'
            )
        }
        throw new Error('Network error while restarting OpenTelemetry')
    }
}

/**
 * Connect OpenTelemetry to Grafana server
 * @param hostId - The ID of the host
 * @returns Promise with operation result
 */
export const doConnectOpenTelemetryToGrafana = async (
    hostId: string
): Promise<OpenTelemetryDeployResponse> => {
    try {
        const response = await api.post<OpenTelemetryDeployResponse>(
            `/api/opentelemetry/hosts/${hostId}/opentelemetry/connect`
        )
        return response.data
    } catch (error) {
        const axiosError = error as AxiosError
        if (axiosError.response) {
            throw new Error(
                (axiosError.response.data as { detail?: string })?.detail ||
                'Failed to connect OpenTelemetry to Grafana'
            )
        }
        throw new Error('Network error while connecting OpenTelemetry to Grafana')
    }
}

/**
 * Disconnect OpenTelemetry from Grafana server
 * @param hostId - The ID of the host
 * @returns Promise with operation result
 */
export const doDisconnectOpenTelemetryFromGrafana = async (
    hostId: string
): Promise<OpenTelemetryDeployResponse> => {
    try {
        const response = await api.post<OpenTelemetryDeployResponse>(
            `/api/opentelemetry/hosts/${hostId}/opentelemetry/disconnect`
        )
        return response.data
    } catch (error) {
        const axiosError = error as AxiosError
        if (axiosError.response) {
            throw new Error(
                (axiosError.response.data as { detail?: string })?.detail ||
                'Failed to disconnect OpenTelemetry from Grafana'
            )
        }
        throw new Error('Network error while disconnecting OpenTelemetry from Grafana')
    }
}

/**
 * Remove OpenTelemetry from a specific host
 * @param hostId - The ID of the host
 * @returns Promise with operation result
 */
export const doRemoveOpenTelemetry = async (
    hostId: string
): Promise<OpenTelemetryDeployResponse> => {
    try {
        const response = await api.post<OpenTelemetryDeployResponse>(
            `/api/opentelemetry/hosts/${hostId}/remove-opentelemetry`
        )
        return response.data
    } catch (error) {
        const axiosError = error as AxiosError
        if (axiosError.response) {
            throw new Error(
                (axiosError.response.data as { detail?: string })?.detail ||
                'Failed to remove OpenTelemetry'
            )
        }
        throw new Error('Network error while removing OpenTelemetry')
    }
}
