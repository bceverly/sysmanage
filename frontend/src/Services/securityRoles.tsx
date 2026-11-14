// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import type { TFunction } from 'i18next';

import axiosInstance from './api';

// Role and group names come from the database in English.  Each one has a
// translation under securityRoles.role.<slug> / securityRoles.group.<slug>;
// a name with no key yet (a new role) falls back to its English name.
const slug = (name: string): string =>
    name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

export const roleLabel = (t: TFunction, name: string): string =>
    t(`securityRoles.role.${slug(name)}`, name);

export const roleGroupLabel = (t: TFunction, name: string): string =>
    t(`securityRoles.group.${slug(name)}`, name);

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
    const response = await axiosInstance.get('/api/v1/security-roles/groups');
    return response.data;
};

export const doGetUserRoles = async (userId: string): Promise<UserRoles> => {
    const response = await axiosInstance.get(`/api/v1/security-roles/user/${userId}`);
    return response.data;
};

export const doUpdateUserRoles = async (
    userId: string,
    roleIds: string[]
): Promise<UserRoles> => {
    const response = await axiosInstance.put(`/api/v1/security-roles/user/${userId}`, {
        role_ids: roleIds,
    });
    return response.data;
};
