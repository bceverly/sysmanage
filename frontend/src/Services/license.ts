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

// Vulnerability Scanning Types and Functions

export interface VulnerabilityFinding {
    id?: string;  // Unique finding ID from backend
    cve_id: string;
    package_name: string;
    installed_version: string;
    fixed_version?: string;
    severity: string;
    cvss_score?: string;
    remediation?: string;
    description?: string;
}

export interface VulnerabilityScan {
    id: string;
    host_id: string;
    scanned_at: string;
    total_packages: number;
    vulnerable_packages: number;
    total_vulnerabilities: number;
    critical_count: number;
    high_count: number;
    medium_count: number;
    low_count: number;
    risk_score: number;
    risk_level: string;
    summary?: string;
    recommendations?: string[];
    vulnerabilities?: VulnerabilityFinding[];
}

export interface VulnerabilityScanHistory {
    scans: VulnerabilityScan[];
    total: number;
}

export interface HostVulnerabilitySummary {
    host_id: string;
    hostname: string;
    fqdn: string;
    critical_count: number;
    high_count: number;
    medium_count: number;
    low_count: number;
    total_vulnerabilities: number;
    risk_score: number;
    risk_level: string;
    last_scanned_at?: string;
}

export interface HostVulnerabilityListResponse {
    hosts: HostVulnerabilitySummary[];
    total: number;
}

/**
 * Get vulnerability scan results for a host.
 */
export const getHostVulnerabilityScan = async (hostId: string, refresh = false): Promise<VulnerabilityScan> => {
    const response = await axiosInstance.get(`/api/host/${hostId}/vulnerability-scan`, {
        params: { refresh }
    });
    return response.data;
};

/**
 * Run a new vulnerability scan for a host.
 */
export const runHostVulnerabilityScan = async (hostId: string): Promise<VulnerabilityScan> => {
    const response = await axiosInstance.post(`/api/host/${hostId}/vulnerability-scan`);
    return response.data;
};

/**
 * Get vulnerability scan history for a host.
 */
export const getHostVulnerabilityHistory = async (hostId: string, limit = 10): Promise<VulnerabilityScanHistory> => {
    const response = await axiosInstance.get(`/api/host/${hostId}/vulnerability-scan/history`, {
        params: { limit }
    });
    return response.data;
};

// CVE Refresh Settings Types and Functions

export interface CveSourceInfo {
    name: string;
    description: string;
    enabled_by_default: boolean;
}

export interface CveRefreshSettings {
    id: string;
    enabled: boolean;
    refresh_interval_hours: number;
    enabled_sources: string[];
    has_nvd_api_key: boolean;
    last_refresh_at?: string;
    next_refresh_at?: string;
    created_at: string;
    updated_at: string;
}

export interface CveRefreshSettingsUpdate {
    enabled?: boolean;
    refresh_interval_hours?: number;
    enabled_sources?: string[];
    nvd_api_key?: string;
}

export interface CveDatabaseStats {
    total_cves: number;
    total_package_mappings: number;
    severity_counts: {
        critical: number;
        high: number;
        medium: number;
        low: number;
        none: number;
    };
    last_refresh_at?: string;
    next_refresh_at?: string;
    last_successful_ingestion?: {
        source: string;
        completed_at: string;
        vulnerabilities_processed: number;
    };
}

export interface CveIngestionLog {
    id: string;
    source: string;
    started_at: string;
    completed_at?: string;
    status: string;
    vulnerabilities_processed?: number;
    packages_processed?: number;
    error_message?: string;
}

export interface CveRefreshResult {
    started_at: string;
    completed_at?: string;
    sources: Record<string, { status: string; vulnerabilities_processed?: number; packages_processed?: number; error?: string }>;
    total_vulnerabilities: number;
    total_packages: number;
    errors: string[];
}

/**
 * Get available CVE data sources.
 */
export const getCveSources = async (): Promise<Record<string, CveSourceInfo>> => {
    const response = await axiosInstance.get('/api/cve-refresh/sources');
    return response.data;
};

/**
 * Get CVE refresh settings.
 */
export const getCveRefreshSettings = async (): Promise<CveRefreshSettings> => {
    const response = await axiosInstance.get('/api/cve-refresh/settings');
    return response.data;
};

/**
 * Update CVE refresh settings.
 */
export const updateCveRefreshSettings = async (settings: CveRefreshSettingsUpdate): Promise<CveRefreshSettings> => {
    const response = await axiosInstance.put('/api/cve-refresh/settings', settings);
    return response.data;
};

/**
 * Get CVE database statistics.
 */
export const getCveDatabaseStats = async (): Promise<CveDatabaseStats> => {
    const response = await axiosInstance.get('/api/cve-refresh/stats');
    return response.data;
};

/**
 * Get CVE ingestion history.
 */
export const getCveIngestionHistory = async (limit = 10): Promise<CveIngestionLog[]> => {
    const response = await axiosInstance.get('/api/cve-refresh/history', {
        params: { limit }
    });
    return response.data;
};

/**
 * Trigger CVE database refresh.
 */
export const triggerCveRefresh = async (source?: string): Promise<CveRefreshResult> => {
    const response = await axiosInstance.post('/api/cve-refresh/refresh', null, {
        params: source ? { source } : {}
    });
    return response.data;
};

/**
 * Clear NVD API key.
 */
export const clearNvdApiKey = async (): Promise<{ message: string }> => {
    const response = await axiosInstance.delete('/api/cve-refresh/nvd-api-key');
    return response.data;
};

/**
 * Get list of all hosts with their vulnerability summaries.
 */
export const getVulnerabilityHosts = async (): Promise<HostVulnerabilityListResponse> => {
    const response = await axiosInstance.get('/api/vulnerabilities/hosts');
    return response.data;
};

// Compliance Engine Types and Functions

export interface ComplianceRuleResult {
    rule_id: string;
    rule_name: string;
    category: string;
    benchmark: string;
    severity: string;
    status: string;
    description: string;
    remediation: string;
    actual_value?: string;
    expected_value?: string;
}

export interface ComplianceScan {
    id: string;
    host_id: string;
    scanned_at: string;
    profile_id: string;
    profile_name: string;
    total_rules: number;
    passed_rules: number;
    failed_rules: number;
    error_rules: number;
    not_applicable_rules: number;
    compliance_score: number;
    compliance_grade: string;
    critical_failures: number;
    high_failures: number;
    medium_failures: number;
    low_failures: number;
    summary?: string;
    results?: ComplianceRuleResult[];
}

export interface ComplianceScanHistory {
    scans: ComplianceScan[];
    total: number;
}

export interface HostComplianceSummary {
    host_id: string;
    hostname: string;
    fqdn: string;
    compliance_score: number;
    compliance_grade: string;
    passed_rules: number;
    failed_rules: number;
    critical_failures: number;
    high_failures: number;
    last_scanned_at?: string;
}

export interface HostComplianceListResponse {
    hosts: HostComplianceSummary[];
    total: number;
}

/**
 * Get compliance scan results for a host.
 */
export const getHostComplianceScan = async (
    hostId: string, refresh = false
): Promise<ComplianceScan> => {
    const response = await axiosInstance.get(
        `/api/host/${hostId}/compliance-scan`,
        { params: { refresh } }
    );
    return response.data;
};

/**
 * Run a new compliance scan for a host.
 */
export const runHostComplianceScan = async (
    hostId: string
): Promise<ComplianceScan> => {
    const response = await axiosInstance.post(
        `/api/host/${hostId}/compliance-scan`
    );
    return response.data;
};

/**
 * Get compliance scan history for a host.
 */
export const getHostComplianceHistory = async (
    hostId: string, limit = 10
): Promise<ComplianceScanHistory> => {
    const response = await axiosInstance.get(
        `/api/host/${hostId}/compliance-scan/history`,
        { params: { limit } }
    );
    return response.data;
};

/**
 * Get list of all hosts with their compliance summaries.
 */
export const getComplianceHosts = async (): Promise<HostComplianceListResponse> => {
    const response = await axiosInstance.get('/api/compliance/hosts');
    return response.data;
};
