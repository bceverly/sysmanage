import { useState } from "react";
import { AxiosError } from 'axios'

import api from './api'

type SuccessResponse = {
    result: boolean;
}

type SysManageUser = {
    id: BigInteger;
    active: boolean;
    userid: string;
    password: string;
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

const doAddUser = async (active: boolean, userid: string, password: string) => {
    await api.post("/user", {
        'active': active,
        'userid': userid,
        'password': password,
      })
    .then((response) => {
        // No error - process response
        console.log('Updated user: ' + response);
        return response;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doDeleteUser = async (id: BigInteger) => {
    await api.delete<SuccessResponse>("/user/" + id)
    .then((response) => {
        // No error - process response
        const successResponse: SuccessResponse = response.data;
        console.log('User ' + id + ' deleted: ' + successResponse);
        return successResponse;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doGetMe = async () => {
    await api.get<SysManageUser>("/user/me")
    .then((response) => {
        // No error - process response
        const user: SysManageUser = response.data;
        console.log('User ' + user.id + ' found: ' + user);
        return user;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doGetUserByID = async (id: BigInteger) => {
    await api.get<SysManageUser>("/user/" + id)
    .then((response) => {
        // No error - process response
        const user: SysManageUser = response.data;
        console.log('User ' + id + ' found: ' + user);
        return user;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doGetUsers = async (): Promise<SysManageUser[]> => {
    let results: SysManageUser[] = [];

    await api.get<SysManageUser[]>("/users")
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

const doGetUserByUserid = async (userid: string) => {
    await api.get<SysManageUser>("/host/by_userid/" + userid)
    .then((response) => {
        // No error - process response
        const host: SysManageUser = response.data;
        console.log('User ' + userid + ' found: ' + response);
        return host;
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doUpdateUser = async (id: BigInteger, active: boolean, userid: string, password: string) => {
    await api.put<SuccessResponse>("/user/" + id, {
        'active': active,
        'userid': userid,
        'password': password,
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

export type { SuccessResponse, SysManageUser };
export { doAddUser, doDeleteUser, doGetMe, doGetUserByID, doGetUserByUserid, doGetUsers, doUpdateUser };