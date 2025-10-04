import axiosInstance from './api';

export interface SecurityRole {
    id: string;
    name: string;
    description: string | null;
    group_id: string;
    group_name: string;
}

export interface SecurityRoleGroup {
    id: string;
    name: string;
    description: string | null;
    roles: SecurityRole[];
}

export interface UserRoles {
    user_id: string;
    role_ids: string[];
}

export const doGetAllRoleGroups = async (): Promise<SecurityRoleGroup[]> => {
    const response = await axiosInstance.get('/api/security-roles/groups');
    return response.data;
};

export const doGetUserRoles = async (userId: string): Promise<UserRoles> => {
    const response = await axiosInstance.get(`/api/security-roles/user/${userId}`);
    return response.data;
};

export const doUpdateUserRoles = async (
    userId: string,
    roleIds: string[]
): Promise<UserRoles> => {
    const response = await axiosInstance.put(`/api/security-roles/user/${userId}`, {
        role_ids: roleIds,
    });
    return response.data;
};
