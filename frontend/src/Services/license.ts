/**
 * License service for Pro+ license management.
 */

import axiosInstance from './api';

export interface LicenseInfo {
    active: boolean;
    tier?: string;
    license_id?: string;
    features?: string[];
    modules?: string[];
    expires_at?: string;
    customer_name?: string;
    parent_hosts?: number;
    child_hosts?: number;
}

export interface HealthAnalysis {
    id: string;
    host_id: string;
    analyzed_at: string;
    score: number;
    grade: string;
    issues?: Array<{
        severity: string;
        category: string;
        message: string;
        details?: Record<string, unknown>;
    }>;
    recommendations?: Array<{
        priority: string;
        category: string;
        message: string;
        action?: string;
    }>;
    analysis_version?: string;
}

export interface HealthHistory {
    analyses: HealthAnalysis[];
    total: number;
}

/**
 * Get current license information.
 */
export const getLicenseInfo = async (): Promise<LicenseInfo> => {
    const response = await axiosInstance.get('/api/license');
    return response.data;
};

/**
 * Install a new license key.
 */
export const installLicense = async (licenseKey: string): Promise<{
    success: boolean;
    message: string;
    license_info?: LicenseInfo;
}> => {
    const response = await axiosInstance.post('/api/license', {
        license_key: licenseKey
    });
    return response.data;
};

/**
 * Get health analysis for a host.
 */
export const getHostHealthAnalysis = async (hostId: string, refresh = false): Promise<HealthAnalysis> => {
    const response = await axiosInstance.get(`/api/host/${hostId}/health-analysis`, {
        params: { refresh }
    });
    return response.data;
};

/**
 * Run a new health analysis for a host.
 */
export const runHostHealthAnalysis = async (hostId: string): Promise<HealthAnalysis> => {
    const response = await axiosInstance.post(`/api/host/${hostId}/health-analysis`);
    return response.data;
};

/**
 * Get health analysis history for a host.
 */
export const getHostHealthHistory = async (hostId: string, limit = 10): Promise<HealthHistory> => {
    const response = await axiosInstance.get(`/api/host/${hostId}/health-analysis/history`, {
        params: { limit }
    });
    return response.data;
};
