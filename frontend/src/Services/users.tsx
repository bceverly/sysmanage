import { AxiosError } from 'axios'

import api from './api'

type SuccessResponse = {
    result: boolean;
}

type SysManageUser = {
    id: BigInt;
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
    let result = {} as SysManageUser;

    await api.post("/user", {
        'active': active,
        'userid': userid,
        'password': password,
      })
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

const doDeleteUser = async (id: BigInt) => {
    let successResponse = {} as SuccessResponse;

    await api.delete<SuccessResponse>("/user/" + id)
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

const doGetMe = async () => {
    let result = {} as SysManageUser;
    await api.get<SysManageUser>("/user/me")
    .then((response) => {
        // No error - process response
        result = response.data;
        return Promise.resolve(result);
    })
    .catch((error) => {
        processError(error);
        return Promise.reject(error);
    });
};

const doGetUserByID = async (id: BigInt) => {
    let result = {} as SysManageUser;

    await api.get<SysManageUser>("/user/" + id)
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
    let result = {} as SysManageUser;

    await api.get<SysManageUser>("/host/by_userid/" + userid)
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

const doUpdateUser = async (id: BigInt, active: boolean, userid: string, password: string) => {
    let successResponse = {} as SuccessResponse;

    await api.put<SuccessResponse>("/user/" + id, {
        'active': active,
        'userid': userid,
        'password': password,
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

export type { SuccessResponse, SysManageUser };
export { doAddUser, doDeleteUser, doGetMe, doGetUserByID, doGetUserByUserid, doGetUsers, doUpdateUser };