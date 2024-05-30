import { useState } from "react";
import { AxiosError } from 'axios'

import api from './api'

type SuccessResponse = {
    result: boolean;
}

type SysManageHost = {
    id: BigInteger;
    active: boolean;
    fqdn: string;
    ipv4: string;
    ipv6: string;
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
    await api.post("/host", {
        'active': active,
        'fqdn': fqdn,
        'ipv4': ipv4,
        'ipv6': ipv6,
      })
    .then((response) => {
        // No error - process response
        console.log('Updated host: ' + response);
        return response;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doDeleteHost = async (id: BigInteger) => {
    await api.delete<SuccessResponse>("/host/" + id)
    .then((response) => {
        // No error - process response
        const successResponse: SuccessResponse = response.data;
        console.log('Host ' + id + ' deleted: ' + successResponse);
        return successResponse;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doGetHostByID = async (id: BigInteger) => {
    await api.get<SysManageHost>("/host/" + id)
    .then((response) => {
        // No error - process response
        const host: SysManageHost = response.data;
        console.log('Host ' + id + ' found: ' + host);
        return host;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doGetHosts = async (): Promise<SysManageHost[]> => {
    let results: SysManageHost[] = [];

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
    await api.get<SysManageHost>("/host/by_fqdn/" + fqdn)
    .then((response) => {
        // No error - process response
        const host: SysManageHost = response.data;
        console.log('Host ' + fqdn + ' found: ' + response);
        return host;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doUpdateHost = async (id: BigInteger, active: boolean, fqdn: string, ipv4: string, ipv6: string) => {
    await api.put<SuccessResponse>("/host/" + id, {
        'active': active,
        'fqdn': fqdn,
        'ipv4': ipv4,
        'ipv6': ipv6,
      })
    .then((response) => {
        // No error - process response
        const successResponse: SuccessResponse = response.data;
        console.log('Updated host: ' + successResponse);
        return successResponse;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

export type { SuccessResponse, SysManageHost };
export { doAddHost, doDeleteHost, doGetHostByID, doGetHostByFQDN, doGetHosts, doUpdateHost };