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
    // Use hasOwnProperty to prevent prototype pollution attacks
    return Object.prototype.hasOwnProperty.call(permissions.permissions, permissionName)
        && permissions.permissions[permissionName] === true; // nosemgrep: detect-object-injection
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
    // - General Host Operations (alphabetical)
    APPROVE_HOST_REGISTRATION: 'Approve Host Registration',
    DELETE_HOST: 'Delete Host',
    EDIT_TAGS: 'Edit Tags',
    VIEW_HOST_DETAILS: 'View Host Details',
    // - Host Power Operations (alphabetical)
    REBOOT_HOST: 'Reboot Host',
    SHUTDOWN_HOST: 'Shutdown Host',
    // - Host Service Operations (alphabetical)
    RESTART_HOST_SERVICE: 'Restart Host Service',
    START_HOST_SERVICE: 'Start Host Service',
    STOP_HOST_SERVICE: 'Stop Host Service',

    // Integration Management
    // - Queue Operations (alphabetical)
    DELETE_QUEUE_MESSAGE: 'Delete Queue Message',
    // - Grafana Operations (alphabetical)
    ENABLE_GRAFANA_INTEGRATION: 'Enable Grafana Integration',
    // - Graylog Operations (alphabetical)
    ENABLE_GRAYLOG_INTEGRATION: 'Enable Graylog Integration',
    // - OpenTelemetry Operations (alphabetical)
    DEPLOY_OPENTELEMETRY: 'Deploy OpenTelemetry',
    RESTART_OPENTELEMETRY_SERVICE: 'Restart OpenTelemetry Service',
    START_OPENTELEMETRY_SERVICE: 'Start OpenTelemetry Service',
    STOP_OPENTELEMETRY_SERVICE: 'Stop OpenTelemetry Service',

    // Package Management
    // - Package Operations (alphabetical)
    ADD_PACKAGE: 'Add Package',
    APPLY_HOST_OS_UPGRADE: 'Apply Host OS Upgrade',
    APPLY_SOFTWARE_UPDATE: 'Apply Software Update',
    // - Third-Party Repository Operations (alphabetical)
    ADD_THIRD_PARTY_REPOSITORY: 'Add Third-Party Repository',
    DELETE_THIRD_PARTY_REPOSITORY: 'Delete Third-Party Repository',
    DISABLE_THIRD_PARTY_REPOSITORY: 'Disable Third-Party Repository',
    ENABLE_THIRD_PARTY_REPOSITORY: 'Enable Third-Party Repository',

    // Report Management
    GENERATE_PDF_REPORT: 'Generate PDF Report',
    VIEW_REPORT: 'View Report',

    // Script Management
    // - Script CRUD Operations (alphabetical)
    ADD_SCRIPT: 'Add Script',
    DELETE_SCRIPT: 'Delete Script',
    EDIT_SCRIPT: 'Edit Script',
    // - Script Execution Operations (alphabetical)
    DELETE_SCRIPT_EXECUTION: 'Delete Script Execution',
    RUN_SCRIPT: 'Run Script',

    // Secrets Management
    // - Secret Operations (alphabetical)
    ADD_SECRET: 'Add Secret',
    DELETE_SECRET: 'Delete Secret',
    EDIT_SECRET: 'Edit Secret',
    // - Certificate Deployment (alphabetical)
    DEPLOY_CERTIFICATE: 'Deploy Certificate',
    // - SSH Key Deployment (alphabetical)
    DEPLOY_SSH_KEY: 'Deploy SSH Key',
    // - Vault Operations (alphabetical)
    START_VAULT: 'Start Vault',
    STOP_VAULT: 'Stop Vault',

    // Security Management
    // - Antivirus Operations (alphabetical)
    DEPLOY_ANTIVIRUS: 'Deploy Antivirus',
    DISABLE_ANTIVIRUS: 'Disable Antivirus',
    ENABLE_ANTIVIRUS: 'Enable Antivirus',
    MANAGE_ANTIVIRUS_DEFAULTS: 'Manage Antivirus Defaults',
    REMOVE_ANTIVIRUS: 'Remove Antivirus',
    // - Firewall Operations (alphabetical)
    DEPLOY_FIREWALL: 'Deploy Firewall',
    DISABLE_FIREWALL: 'Disable Firewall',
    EDIT_FIREWALL_PORTS: 'Edit Firewall Ports',
    ENABLE_FIREWALL: 'Enable Firewall',
    REMOVE_FIREWALL: 'Remove Firewall',
    RESTART_FIREWALL: 'Restart Firewall',
    // - User Security Role Management (alphabetical)
    EDIT_USER_SECURITY_ROLES: 'Edit User Security Roles',
    VIEW_USER_SECURITY_ROLES: 'View User Security Roles',

    // Ubuntu Pro Management
    ATTACH_UBUNTU_PRO: 'Attach Ubuntu Pro',
    CHANGE_UBUNTU_PRO_MASTER_KEY: 'Change Ubuntu Pro Master Key',
    DETACH_UBUNTU_PRO: 'Detach Ubuntu Pro',

    // User Management
    // - User CRUD Operations (alphabetical)
    ADD_USER: 'Add User',
    DELETE_USER: 'Delete User',
    EDIT_USER: 'Edit User',
    // - User Security Operations (alphabetical)
    LOCK_USER: 'Lock User',
    RESET_USER_PASSWORD: 'Reset User Password',
    UNLOCK_USER: 'Unlock User',

    // Audit Log Management
    VIEW_AUDIT_LOG: 'View Audit Log',
    EXPORT_AUDIT_LOG: 'Export Audit Log',

    // Default Repository Management
    ADD_DEFAULT_REPOSITORY: 'Add Default Repository',
    REMOVE_DEFAULT_REPOSITORY: 'Remove Default Repository',
    VIEW_DEFAULT_REPOSITORIES: 'View Default Repositories',

    // Enabled Package Manager Management
    ADD_ENABLED_PACKAGE_MANAGER: 'Add Enabled Package Manager',
    REMOVE_ENABLED_PACKAGE_MANAGER: 'Remove Enabled Package Manager',
    VIEW_ENABLED_PACKAGE_MANAGERS: 'View Enabled Package Managers',

    // Firewall Role Management
    ADD_FIREWALL_ROLE: 'Add Firewall Role',
    EDIT_FIREWALL_ROLE: 'Edit Firewall Role',
    DELETE_FIREWALL_ROLE: 'Delete Firewall Role',
    VIEW_FIREWALL_ROLES: 'View Firewall Roles',
    ASSIGN_HOST_FIREWALL_ROLES: 'Assign Host Firewall Roles',

    // Host Account Management
    // - Host Account (User) Operations (alphabetical)
    ADD_HOST_ACCOUNT: 'Add Host Account',
    DELETE_HOST_ACCOUNT: 'Delete Host Account',
    EDIT_HOST_ACCOUNT: 'Edit Host Account',
    // - Host Group Operations (alphabetical)
    ADD_HOST_GROUP: 'Add Host Group',
    DELETE_HOST_GROUP: 'Delete Host Group',
    EDIT_HOST_GROUP: 'Edit Host Group',

    // Virtualization Roles
    // - Child Host Operations (alphabetical)
    CONFIGURE_CHILD_HOST: 'Configure Child Host',
    CREATE_CHILD_HOST: 'Create Child Host',
    DELETE_CHILD_HOST: 'Delete Child Host',
    RESTART_CHILD_HOST: 'Restart Child Host',
    START_CHILD_HOST: 'Start Child Host',
    STOP_CHILD_HOST: 'Stop Child Host',
    VIEW_CHILD_HOST: 'View Child Host'
} as const;
