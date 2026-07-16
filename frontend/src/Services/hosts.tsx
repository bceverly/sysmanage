// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { AxiosError } from 'axios'

import api from './api'

type SuccessResponse = {
    result: boolean;
}

type DiagnosticReport = {
    id: string;
    collection_id: string;
    status: string;
    requested_by: string;
    requested_at: string;
    started_at: string | null;
    completed_at: string | null;
    collection_size_bytes: number | null;
    files_collected: number | null;
    error_message: string | null;
    system_logs?: string | object;
    configuration_files?: string | object;
    process_list?: string | object;
    system_information?: string | object;
}

type DiagnosticDetailResponse = {
    id: string;
    host_id: string;
    collection_id: string;
    status: string;
    requested_by: string;
    requested_at: string;
    started_at: string | null;
    completed_at: string | null;
    collection_size_bytes: number | null;
    files_collected: number | null;
    error_message: string | null;
    diagnostic_data: {
        system_logs: unknown;
        configuration_files: unknown;
        network_info: unknown;
        process_info: unknown;
        disk_usage: unknown;
        environment_variables: unknown;
        agent_logs: unknown;
        error_logs: unknown;
    };
}

type SysManageHost = {
    id: string;
    active: boolean;
    fqdn: string;
    ipv4: string;
    ipv6: string;
    status: string;
    approval_status: string;
    last_access: string;
    // OS Version fields
    platform?: string;
    platform_release?: string;
    platform_version?: string;
    machine_architecture?: string;
    processor?: string;
    os_details?: string;
    os_version_updated_at?: string;
    // Certificate fields
    client_certificate?: string;
    certificate_serial?: string;
    certificate_issued_at?: string;
    // Hardware inventory fields
    cpu_vendor?: string;
    cpu_model?: string;
    cpu_cores?: number;
    cpu_threads?: number;
    cpu_frequency_mhz?: number;
    memory_total_mb?: number;
    storage_details?: string;
    network_details?: string;
    hardware_details?: string;
    hardware_updated_at?: string;
    // Software inventory fields
    software_updated_at?: string;
    // User access data timestamp
    user_access_updated_at?: string;
    // Update management fields
    reboot_required?: boolean;
    reboot_required_updated_at?: string;
    // Diagnostics request tracking fields
    diagnostics_requested_at?: string;
    diagnostics_request_status?: string;
    // Agent privilege status
    is_agent_privileged?: boolean;
    // Agent version
    agent_version?: string;
    // Script execution status
    script_execution_enabled?: boolean;
    // Enabled shells for script execution
    enabled_shells?: string;
    // Tags
    tags?: Array<{id: string, name: string, description?: string}>;
    // Update status fields
    security_updates_count?: number;
    system_updates_count?: number;
    total_updates_count?: number;
    os_upgrades_count?: number;
    // Parent host ID for child hosts (WSL, VMs, containers)
    parent_host_id?: string;
    // Virtualization support (for hosts that can be parents)
    virtualization_types?: string;  // JSON string like '["wsl"]' or '["lxd"]'
    virtualization_capabilities?: string;  // JSON string with detailed capabilities
    // Timezone
    timezone?: string;
    // Phase 12.7: agent-reported public IP + GeoLite2 resolution
    public_ip?: string | null;
    public_ip_resolved_at?: string | null;
    geo_country_code?: string | null;
    geo_subdivision_code?: string | null;
    geo_city?: string | null;
    geo_latitude?: number | null;
    geo_longitude?: number | null;
}

type StorageDevice = {
    id: string;
    name?: string;
    device_path?: string;
    mount_point?: string;
    file_system?: string;
    device_type?: string;
    capacity_bytes?: number;
    used_bytes?: number;
    available_bytes?: number;
    is_physical?: boolean;
    created_at?: string;
    updated_at?: string;
}

type NetworkInterface = {
    id: string;
    name?: string;
    interface_type?: string;
    hardware_type?: string;
    mac_address?: string;
    ipv4_address?: string;
    ipv6_address?: string;
    subnet_mask?: string;
    is_active: boolean;
    speed_mbps?: number;
    created_at?: string;
    updated_at?: string;
}

type UserAccount = {
    id: string;
    username: string;
    uid?: number;
    security_id?: string;  // Windows SID string
    home_directory?: string;
    shell?: string;
    is_system_user: boolean;
    groups: string[];
    created_at?: string;
    updated_at?: string;
}

type UserGroup = {
    id: string;
    group_name: string;
    gid?: number;
    security_id?: string;  // Windows SID string
    is_system_group: boolean;
    users: string[];
    created_at?: string;
    updated_at?: string;
}

type SoftwarePackage = {
    id: string;
    package_name: string;
    version?: string;
    description?: string;
    package_manager: string;
    source?: string;
    architecture?: string;
    size_bytes?: number;
    install_date?: string;
    vendor?: string;
    category?: string;
    license_type?: string;
    bundle_id?: string;
    app_store_id?: string;
    installation_path?: string;
    is_system_package: boolean;
    is_user_installed: boolean;
    created_at?: string;
    updated_at?: string;
    software_updated_at?: string;
}

type PaginationInfo = {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
}

type PaginatedSoftwareResponse = {
    items: SoftwarePackage[];
    pagination: PaginationInfo;
}

function processError(error: AxiosError) {
    // Error situation
    if (error.response) {
        // Error response returned by server
        console.log('Error returned by server: ' + error);
    } else if (error.request) {
        // Error was in the request, no response sent by server
        console.log('Error - no response from server: ' + error);
    } else {
        // Some other error
        console.log('Unknown error: ' + error);
    }
}

const doDeleteHost = async (id: string) => {
    let successResponse = {} as SuccessResponse;

    await api.delete<SuccessResponse>("/api/v1/host/" + id)
    .then((response) => {
        // No error - process response
        successResponse = response.data;
        return successResponse;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return successResponse;
};

const doGetHostByID = async (id: string) => {
    let result = {} as SysManageHost;

    await api.get<SysManageHost>("/api/v1/host/" + id)
    .then((response) => {
        // No error - process response
        result = response.data;
        return result;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doGetHosts = async (): Promise<SysManageHost[]> => {
    let results = [] as SysManageHost[];

    await api.get<SysManageHost[]>("/api/v1/hosts")
    .then((response) => {
        // No error - process response
        results = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return results;
};

const doApproveHost = async (id: string) => {
    let result = {} as SysManageHost;

    await api.put<SysManageHost>("/api/v1/host/" + id + "/approve")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRefreshHostData = async (id: string) => {
    let result = {} as SuccessResponse;

    await api.post<SuccessResponse>("/api/v1/host/" + id + "/request-os-update")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRefreshHardwareData = async (id: string) => {
    let result = {} as SuccessResponse;

    await api.post<SuccessResponse>("/api/v1/host/" + id + "/request-hardware-update")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRefreshUpdatesCheck = async (id: string) => {
    let result = {} as SuccessResponse;

    await api.post<SuccessResponse>("/api/v1/host/" + id + "/request-updates-check")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRefreshAllHostData = async (id: string) => {
    // Request OS, hardware updates, updates check, and system info (includes antivirus status)
    const promises = [
        doRefreshHostData(id),
        doRefreshHardwareData(id),
        doRefreshUpdatesCheck(id),
        doRequestSystemInfo(id)
    ];

    await Promise.all(promises);
    return { result: true } as SuccessResponse;
};

const doGetHostStorage = async (id: string): Promise<StorageDevice[]> => {
    let result: StorageDevice[] = [];

    await api.get<StorageDevice[]>("/api/v1/host/" + id + "/storage")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doGetHostNetwork = async (id: string): Promise<NetworkInterface[]> => {
    let result: NetworkInterface[] = [];

    await api.get<NetworkInterface[]>("/api/v1/host/" + id + "/network")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doGetHostUsers = async (id: string): Promise<UserAccount[]> => {
    let result: UserAccount[] = [];

    await api.get<UserAccount[]>("/api/v1/host/" + id + "/users")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doGetHostGroups = async (id: string): Promise<UserGroup[]> => {
    let result: UserGroup[] = [];

    await api.get<UserGroup[]>("/api/v1/host/" + id + "/groups")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRefreshUserAccessData = async (id: string) => {
    let result = {} as SuccessResponse;

    await api.post<SuccessResponse>("/api/v1/host/" + id + "/request-user-access-update")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRequestSystemInfo = async (id: string) => {
    let result = {} as SuccessResponse;

    await api.post<SuccessResponse>("/api/v1/host/" + id + "/request-system-info")
    .then((response) => {
        // No error - process response
        result = response.data;
        return response;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doGetHostSoftware = async (
    id: string,
    page: number = 1,
    pageSize: number = 100,
    search?: string
): Promise<PaginatedSoftwareResponse> => {
    let result = { items: [], pagination: { page: 1, page_size: 100, total_items: 0, total_pages: 0, has_next: false, has_prev: false } } as PaginatedSoftwareResponse;

    const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString()
    });

    if (search) {
        params.append('search', search);
    }

    await api.get("/api/v1/host/" + id + "/software?" + params.toString())
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRefreshSoftwareData = async (id: string) => {
    let result = {} as SuccessResponse;

    await api.post("/api/v1/host/refresh/software/" + id)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doGetHostDiagnostics = async (id: string) => {
    let result = [] as DiagnosticReport[];
    
    await api.get("/api/v1/host/" + id + "/diagnostics")
    .then((response) => {
        // The API returns {host_id: string, diagnostics: array}
        // Extract the diagnostics array from the response
        result = response.data.diagnostics || [];
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRequestHostDiagnostics = async (id: string) => {
    let result = {} as SuccessResponse;
    
    await api.post("/api/v1/host/" + id + "/collect-diagnostics")
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doGetDiagnosticDetail = async (diagnosticId: string) => {
    let result = {} as DiagnosticDetailResponse;
    
    await api.get("/api/v1/diagnostic/" + diagnosticId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doDeleteDiagnostic = async (diagnosticId: string) => {
    let result = {} as SuccessResponse;
    
    await api.delete("/api/v1/diagnostic/" + diagnosticId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRebootHost = async (hostId: string) => {
    let result = {} as SuccessResponse;
    
    await api.post("/api/v1/host/reboot/" + hostId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doShutdownHost = async (hostId: string) => {
    let result = {} as SuccessResponse;

    await api.post("/api/v1/host/shutdown/" + hostId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doUpdateAgent = async (hostId: string) => {
    let result = {} as SuccessResponse;

    await api.post("/api/v1/host/update-agent/" + hostId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doRequestPackages = async (hostId: string) => {
    let result = {} as SuccessResponse;

    await api.post("/api/v1/host/" + hostId + "/request-packages")
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doGetHostUbuntuPro = async (hostId: string) => {
    let result = {} as UbuntuProInfo;

    await api.get("/api/v1/host/" + hostId + "/ubuntu-pro")
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doAttachUbuntuPro = async (hostId: string, token: string) => {
    let result = {} as SuccessResponse;

    await api.post("/api/v1/host/" + hostId + "/ubuntu-pro/attach", {
        token: token
    })
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doDetachUbuntuPro = async (hostId: string) => {
    let result = {} as SuccessResponse;

    await api.post("/api/v1/host/" + hostId + "/ubuntu-pro/detach")
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doEnableUbuntuProService = async (hostId: string, service: string) => {
    let result = {} as SuccessResponse;

    await api.post("/api/v1/host/" + hostId + "/ubuntu-pro/service/enable", {
        service: service
    })
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doDisableUbuntuProService = async (hostId: string, service: string) => {
    let result = {} as SuccessResponse;

    await api.post("/api/v1/host/" + hostId + "/ubuntu-pro/service/disable", {
        service: service
    })
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

type RebootPreCheckResponse = {
    has_running_children: boolean;
    running_children: Array<{
        id: string;
        child_name: string;
        child_type: string;
        status: string;
    }>;
    running_count: number;
    total_children: number;
    has_container_engine: boolean;
}

type OrchestratedRebootResponse = {
    orchestration_id: string;
    status: string;
    child_count: number;
}

type RebootOrchestrationStatus = {
    orchestration_id: string;
    parent_host_id: string;
    status: string;
    child_hosts_snapshot: Array<{
        id: string;
        child_name: string;
        child_type: string;
        pre_reboot_status: string;
    }>;
    child_hosts_restart_status: Array<{
        id: string;
        child_name: string;
        restart_status: string;
        error: string | null;
    }> | null;
    shutdown_timeout_seconds: number;
    initiated_by: string;
    initiated_at: string | null;
    shutdown_completed_at: string | null;
    reboot_issued_at: string | null;
    agent_reconnected_at: string | null;
    restart_completed_at: string | null;
    error_message: string | null;
}

const doRebootPreCheck = async (hostId: string): Promise<RebootPreCheckResponse> => {
    let result = {} as RebootPreCheckResponse;

    await api.get<RebootPreCheckResponse>("/api/v1/host/" + hostId + "/reboot/pre-check")
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doOrchestratedReboot = async (hostId: string): Promise<OrchestratedRebootResponse> => {
    let result = {} as OrchestratedRebootResponse;

    await api.post<OrchestratedRebootResponse>("/api/v1/host/" + hostId + "/reboot/orchestrated")
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const getRebootOrchestrationStatus = async (hostId: string, orchestrationId: string): Promise<RebootOrchestrationStatus> => {
    let result = {} as RebootOrchestrationStatus;

    await api.get<RebootOrchestrationStatus>("/api/v1/host/" + hostId + "/reboot/orchestration/" + orchestrationId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

const doChangeHostname = async (hostId: string, newHostname: string) => {
    let result = {} as SuccessResponse;

    await api.post("/api/v1/host/" + hostId + "/change-hostname", {
        new_hostname: newHostname
    })
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        throw error;
    });
    return result;
};

type UbuntuProService = {
    name: string;
    description: string;
    available: boolean;
    status: string;
    entitled: boolean;
}

type UbuntuProLivepatch = {
    enabled: boolean;
    client_version: string | null;
    patch_state: string | null;
    check_state: string | null;
    patch_version: string | null;
    kernel: string | null;
    last_check: string | null;
    fixes: string[];
}

type UbuntuProInfo = {
    available: boolean;
    attached: boolean;
    version: string | null;
    expires: string | null;
    account_name: string | null;
    contract_name: string | null;
    tech_support_level: string | null;
    services: UbuntuProService[];
    livepatch?: UbuntuProLivepatch | null;
}

export type { SuccessResponse, SysManageHost, StorageDevice, NetworkInterface, UserAccount, UserGroup, SoftwarePackage, PaginatedSoftwareResponse, PaginationInfo, DiagnosticReport, DiagnosticDetailResponse, UbuntuProInfo, UbuntuProService, UbuntuProLivepatch, RebootPreCheckResponse, OrchestratedRebootResponse, RebootOrchestrationStatus };
export { doDeleteHost, doGetHostByID, doGetHosts, doApproveHost, doRefreshHostData, doRefreshHardwareData, doRefreshUpdatesCheck, doRefreshAllHostData, doGetHostStorage, doGetHostNetwork, doGetHostUsers, doGetHostGroups, doRefreshUserAccessData, doRequestSystemInfo, doGetHostSoftware, doRefreshSoftwareData, doGetHostDiagnostics, doRequestHostDiagnostics, doGetDiagnosticDetail, doDeleteDiagnostic, doRebootHost, doShutdownHost, doUpdateAgent, doRequestPackages, doGetHostUbuntuPro, doAttachUbuntuPro, doDetachUbuntuPro, doEnableUbuntuProService, doDisableUbuntuProService, doChangeHostname, doRebootPreCheck, doOrchestratedReboot, getRebootOrchestrationStatus };