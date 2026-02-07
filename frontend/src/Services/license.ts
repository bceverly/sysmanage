/**
 * License service for Pro+ license management.
 *
 * Core license types and functions only. Pro+ module-specific
 * types and API functions are provided by the Pro+ plugin bundle.
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
