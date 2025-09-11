import { AxiosError } from 'axios'

import api from './api'

type SuccessResponse = {
    result: boolean;
}

type DiagnosticReport = {
    id: number;
    collection_id: string;
    status: string;
    requested_by: string;
    requested_at: string;
    started_at: string | null;
    completed_at: string | null;
    collection_size_bytes: number | null;
    files_collected: number | null;
    error_message: string | null;
}

type DiagnosticDetailResponse = {
    id: number;
    host_id: number;
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
    id: BigInt;
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
    // Tags
    tags?: Array<{id: number, name: string, description?: string}>;
}

type StorageDevice = {
    id: number;
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
    id: number;
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
    id: number;
    username: string;
    uid?: number;
    home_directory?: string;
    shell?: string;
    is_system_user: boolean;
    groups: string[];
    created_at?: string;
    updated_at?: string;
}

type UserGroup = {
    id: number;
    group_name: string;
    gid?: number;
    is_system_group: boolean;
    users: string[];
    created_at?: string;
    updated_at?: string;
}

type SoftwarePackage = {
    id: number;
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

const doAddHost = async (active: boolean, fqdn: string, ipv4: string, ipv6: string) => {
    let result = {} as SysManageHost;

    await api.post("/host", {
        'active': active,
        'fqdn': fqdn,
        'ipv4': ipv4,
        'ipv6': ipv6,
      })
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doDeleteHost = async (id: BigInt) => {
    let successResponse = {} as SuccessResponse;

    await api.delete<SuccessResponse>("/host/" + id)
    .then((response) => {
        // No error - process response
        successResponse = response.data;
        return Promise.resolve(successResponse);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return successResponse;
};

const doGetHostByID = async (id: BigInt) => {
    let result = {} as SysManageHost;

    await api.get<SysManageHost>("/host/" + id)
    .then((response) => {
        // No error - process response
        result = response.data;
        return result;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doGetHosts = async (): Promise<SysManageHost[]> => {
    let results = [] as SysManageHost[];

    await api.get<SysManageHost[]>("/hosts")
    .then((response) => {
        // No error - process response
        results = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return results;
};

const doGetHostByFQDN = async (fqdn: string) => {
    let result = {} as SysManageHost;

    await api.get<SysManageHost>("/host/by_fqdn/" + fqdn)
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(result);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doUpdateHost = async (id: BigInt, active: boolean, fqdn: string, ipv4: string, ipv6: string) => {
    let successResponse = {} as SuccessResponse;
    await api.put<SuccessResponse>("/host/" + id, {
        'active': active,
        'fqdn': fqdn,
        'ipv4': ipv4,
        'ipv6': ipv6,
      })
    .then((response) => {
        // No error - process response
        successResponse = response.data;
        return Promise.resolve(successResponse);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return successResponse;
};

const doApproveHost = async (id: BigInt) => {
    let result = {} as SysManageHost;

    await api.put<SysManageHost>("/host/" + id + "/approve")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doRejectHost = async (id: BigInt) => {
    let result = {} as SysManageHost;

    await api.put<SysManageHost>("/host/" + id + "/reject")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doRefreshHostData = async (id: BigInt) => {
    let result = {} as SuccessResponse;

    await api.post<SuccessResponse>("/host/" + id + "/request-os-update")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doRefreshHardwareData = async (id: BigInt) => {
    let result = {} as SuccessResponse;

    await api.post<SuccessResponse>("/host/" + id + "/request-hardware-update")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doRefreshUpdatesCheck = async (id: BigInt) => {
    let result = {} as SuccessResponse;

    await api.post<SuccessResponse>("/host/" + id + "/request-updates-check")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doRefreshAllHostData = async (id: BigInt) => {
    // Request OS, hardware updates, and updates check
    const promises = [
        doRefreshHostData(id),
        doRefreshHardwareData(id),
        doRefreshUpdatesCheck(id)
    ];
    
    await Promise.all(promises);
    return { result: true } as SuccessResponse;
};

const doGetHostStorage = async (id: BigInt): Promise<StorageDevice[]> => {
    let result: StorageDevice[] = [];

    await api.get<StorageDevice[]>("/host/" + id + "/storage")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doGetHostNetwork = async (id: BigInt): Promise<NetworkInterface[]> => {
    let result: NetworkInterface[] = [];

    await api.get<NetworkInterface[]>("/host/" + id + "/network")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doGetHostUsers = async (id: BigInt): Promise<UserAccount[]> => {
    let result: UserAccount[] = [];

    await api.get<UserAccount[]>("/host/" + id + "/users")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doGetHostGroups = async (id: BigInt): Promise<UserGroup[]> => {
    let result: UserGroup[] = [];

    await api.get<UserGroup[]>("/host/" + id + "/groups")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doRefreshUserAccessData = async (id: BigInt) => {
    let result = {} as SuccessResponse;

    await api.post<SuccessResponse>("/host/" + id + "/request-user-access-update")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(response);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doGetHostSoftware = async (id: BigInt) => {
    let result = [] as SoftwarePackage[];
    
    await api.get("/host/" + id + "/software")
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doRefreshSoftwareData = async (id: BigInt) => {
    let result = {} as SuccessResponse;

    await api.post("/host/refresh/software/" + id)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doGetHostDiagnostics = async (id: BigInt) => {
    let result = [] as DiagnosticReport[];
    
    await api.get("/host/" + id + "/diagnostics")
    .then((response) => {
        // The API returns {host_id: number, diagnostics: array}
        // Extract the diagnostics array from the response
        result = response.data.diagnostics || [];
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doRequestHostDiagnostics = async (id: BigInt) => {
    let result = {} as SuccessResponse;
    
    await api.post("/host/" + id + "/collect-diagnostics")
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doGetDiagnosticDetail = async (diagnosticId: number) => {
    let result = {} as DiagnosticDetailResponse;
    
    await api.get("/diagnostic/" + diagnosticId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doDeleteDiagnostic = async (diagnosticId: number) => {
    let result = {} as SuccessResponse;
    
    await api.delete("/diagnostic/" + diagnosticId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doRebootHost = async (hostId: number) => {
    let result = {} as SuccessResponse;
    
    await api.post("/host/reboot/" + hostId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

const doShutdownHost = async (hostId: number) => {
    let result = {} as SuccessResponse;
    
    await api.post("/host/shutdown/" + hostId)
    .then((response) => {
        result = response.data;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
    return result;
};

export type { SuccessResponse, SysManageHost, StorageDevice, NetworkInterface, UserAccount, UserGroup, SoftwarePackage, DiagnosticReport, DiagnosticDetailResponse };
export { doAddHost, doDeleteHost, doGetHostByID, doGetHostByFQDN, doGetHosts, doUpdateHost, doApproveHost, doRejectHost, doRefreshHostData, doRefreshHardwareData, doRefreshUpdatesCheck, doRefreshAllHostData, doGetHostStorage, doGetHostNetwork, doGetHostUsers, doGetHostGroups, doRefreshUserAccessData, doGetHostSoftware, doRefreshSoftwareData, doGetHostDiagnostics, doRequestHostDiagnostics, doGetDiagnosticDetail, doDeleteDiagnostic, doRebootHost, doShutdownHost };