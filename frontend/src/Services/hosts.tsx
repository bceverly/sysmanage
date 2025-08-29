import { AxiosError } from 'axios'

import api from './api'

type SuccessResponse = {
    result: boolean;
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

export type { SuccessResponse, SysManageHost };
export { doAddHost, doDeleteHost, doGetHostByID, doGetHostByFQDN, doGetHosts, doUpdateHost, doApproveHost, doRejectHost, doRefreshHostData };