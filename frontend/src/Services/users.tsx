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
    first_name?: string;
    last_name?: string;
    last_access?: string;
    is_locked: boolean;
    failed_login_attempts: number;
    locked_at: string | null;
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

const doAddUser = async (active: boolean, userid: string, password: string, firstName?: string, lastName?: string) => {
    let result = {} as SysManageUser;

    // Build the request payload
    const payload: {
        active: boolean;
        userid: string;
        first_name: string | null;
        last_name: string | null;
        password?: string;
    } = {
        'active': active,
        'userid': userid,
        'first_name': firstName || null,
        'last_name': lastName || null,
    };

    // Only include password if it's provided and not empty
    if (password && password.trim() !== '') {
        payload['password'] = password;
    }

    await api.post("/api/user", payload)
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

    await api.delete<SuccessResponse>("/api/user/" + id)
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
    await api.get<SysManageUser>("/api/user/me")
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

    await api.get<SysManageUser>("/api/user/" + id)
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

    await api.get<SysManageUser[]>("/api/users")
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

    await api.get<SysManageUser>("/api/host/by_userid/" + userid)
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

const doUpdateUser = async (id: BigInt, active: boolean, userid: string, password: string, firstName?: string, lastName?: string) => {
    let successResponse = {} as SuccessResponse;

    await api.put<SuccessResponse>("/api/user/" + id, {
        'active': active,
        'userid': userid,
        'password': password,
        'first_name': firstName || null,
        'last_name': lastName || null,
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

const doUnlockUser = async (id: BigInt) => {
    let result = {} as SysManageUser;

    await api.post<SysManageUser>("/api/user/" + id + "/unlock")
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

const doUploadUserImage = async (userId: BigInt, file: globalThis.File) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await api.post(`/api/user/${userId}/image`, formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
        });
        return response.data;
    } catch (error) {
        processError(error);
        return Promise.reject(error);
    }
};

const doGetUserImage = async (userId: BigInt): Promise<globalThis.Blob> => {
    try {
        const response = await api.get(`/api/user/${userId}/image`, {
            responseType: 'blob'
        });
        return response.data;
    } catch (error) {
        processError(error);
        return Promise.reject(error);
    }
};

const doDeleteUserImage = async (userId: BigInt) => {
    try {
        const response = await api.delete(`/api/user/${userId}/image`);
        return response.data;
    } catch (error) {
        processError(error);
        return Promise.reject(error);
    }
};

export type { SuccessResponse, SysManageUser };
export { doAddUser, doDeleteUser, doGetMe, doGetUserByID, doGetUserByUserid, doGetUsers, doUpdateUser, doUnlockUser, doUploadUserImage, doGetUserImage, doDeleteUserImage };