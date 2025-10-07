import axiosInstance from './api';

export interface UserPermissions {
    is_admin: boolean;
    permissions: {
        [key: string]: boolean;
    };
}

// Cache for user permissions
let permissionsCache: UserPermissions | null = null;

/**
 * Fetch user permissions from the API
 */
export const fetchUserPermissions = async (): Promise<UserPermissions> => {
    const response = await axiosInstance.get<UserPermissions>('/api/user/permissions');
    permissionsCache = response.data;
    return response.data;
};

/**
 * Get cached permissions or fetch if not cached
 */
export const getUserPermissions = async (): Promise<UserPermissions> => {
    if (permissionsCache) {
        return permissionsCache;
    }
    return await fetchUserPermissions();
};

/**
 * Check if user has a specific permission
 */
export const hasPermission = async (permissionName: string): Promise<boolean> => {
    const permissions = await getUserPermissions();
    return permissions.permissions[permissionName] === true;
};

/**
 * Clear the permissions cache (call on logout)
 */
export const clearPermissionsCache = (): void => {
    permissionsCache = null;
};

/**
 * Refresh permissions cache
 */
export const refreshPermissions = async (): Promise<UserPermissions> => {
    return await fetchUserPermissions();
};

// Security role names (matching backend enum)
export const SecurityRoles = {
    // Host Management
    APPROVE_HOST_REGISTRATION: 'Approve Host Registration',
    DELETE_HOST: 'Delete Host',
    VIEW_HOST_DETAILS: 'View Host Details',
    REBOOT_HOST: 'Reboot Host',
    SHUTDOWN_HOST: 'Shutdown Host',
    EDIT_TAGS: 'Edit Tags',
    STOP_HOST_SERVICE: 'Stop Host Service',
    START_HOST_SERVICE: 'Start Host Service',
    RESTART_HOST_SERVICE: 'Restart Host Service',

    // Package Management
    ADD_PACKAGE: 'Add Package',
    APPLY_SOFTWARE_UPDATE: 'Apply Software Update',
    APPLY_HOST_OS_UPGRADE: 'Apply Host OS Upgrade',
    ADD_THIRD_PARTY_REPOSITORY: 'Add Third-Party Repository',
    DELETE_THIRD_PARTY_REPOSITORY: 'Delete Third-Party Repository',
    ENABLE_THIRD_PARTY_REPOSITORY: 'Enable Third-Party Repository',
    DISABLE_THIRD_PARTY_REPOSITORY: 'Disable Third-Party Repository',

    // Secrets Management
    DEPLOY_SSH_KEY: 'Deploy SSH Key',
    DEPLOY_CERTIFICATE: 'Deploy Certificate',
    ADD_SECRET: 'Add Secret',
    DELETE_SECRET: 'Delete Secret',
    EDIT_SECRET: 'Edit Secret',
    STOP_VAULT: 'Stop Vault',
    START_VAULT: 'Start Vault',

    // User Management
    ADD_USER: 'Add User',
    EDIT_USER: 'Edit User',
    LOCK_USER: 'Lock User',
    UNLOCK_USER: 'Unlock User',
    DELETE_USER: 'Delete User',
    RESET_USER_PASSWORD: 'Reset User Password',

    // Script Management
    ADD_SCRIPT: 'Add Script',
    EDIT_SCRIPT: 'Edit Script',
    DELETE_SCRIPT: 'Delete Script',
    RUN_SCRIPT: 'Run Script',
    DELETE_SCRIPT_EXECUTION: 'Delete Script Execution',

    // Report Management
    VIEW_REPORT: 'View Report',
    GENERATE_PDF_REPORT: 'Generate PDF Report',

    // Integration Management
    DELETE_QUEUE_MESSAGE: 'Delete Queue Message',
    ENABLE_GRAFANA_INTEGRATION: 'Enable Grafana Integration',

    // Ubuntu Pro Management
    ATTACH_UBUNTU_PRO: 'Attach Ubuntu Pro',
    DETACH_UBUNTU_PRO: 'Detach Ubuntu Pro',
    CHANGE_UBUNTU_PRO_MASTER_KEY: 'Change Ubuntu Pro Master Key'
} as const;
