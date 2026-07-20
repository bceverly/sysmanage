// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Custom hook that resolves the RBAC permissions used across the Host Detail
// page.  All permission flags are checked once on mount and returned as a flat
// object so the parent component and its child tabs can gate their UI.

import { useEffect, useState } from 'react';
import { hasPermission, SecurityRoles } from '../../Services/permissions';

export interface HostPermissions {
    canEditTags: boolean;
    canEditHostname: boolean;
    canStopService: boolean;
    canStartService: boolean;
    canRestartService: boolean;
    canAddPackage: boolean;
    canDeploySshKey: boolean;
    canDeployCertificate: boolean;
    canAttachUbuntuPro: boolean;
    canDetachUbuntuPro: boolean;
    canDeployAntivirus: boolean;
    canEnableAntivirus: boolean;
    canDisableAntivirus: boolean;
    canRemoveAntivirus: boolean;
    canAddHostAccount: boolean;
    canAddHostGroup: boolean;
    canDeleteHostAccount: boolean;
    canDeleteHostGroup: boolean;
    canEnableWsl: boolean;
    canEnableLxd: boolean;
    canEnableKvm: boolean;
    canEnableVmm: boolean;
    canEnableBhyve: boolean;
}

export const useHostPermissions = (): HostPermissions => {
    const [canEditTags, setCanEditTags] = useState<boolean>(false);
    const [canEditHostname, setCanEditHostname] = useState<boolean>(false);
    const [canStopService, setCanStopService] = useState<boolean>(false);
    const [canStartService, setCanStartService] = useState<boolean>(false);
    const [canRestartService, setCanRestartService] = useState<boolean>(false);
    const [canAddPackage, setCanAddPackage] = useState<boolean>(false);
    const [canDeploySshKey, setCanDeploySshKey] = useState<boolean>(false);
    const [canDeployCertificate, setCanDeployCertificate] = useState<boolean>(false);
    const [canAttachUbuntuPro, setCanAttachUbuntuPro] = useState<boolean>(false);
    const [canDetachUbuntuPro, setCanDetachUbuntuPro] = useState<boolean>(false);
    const [canDeployAntivirus, setCanDeployAntivirus] = useState<boolean>(false);
    const [canEnableAntivirus, setCanEnableAntivirus] = useState<boolean>(false);
    const [canDisableAntivirus, setCanDisableAntivirus] = useState<boolean>(false);
    const [canRemoveAntivirus, setCanRemoveAntivirus] = useState<boolean>(false);
    const [canAddHostAccount, setCanAddHostAccount] = useState<boolean>(false);
    const [canAddHostGroup, setCanAddHostGroup] = useState<boolean>(false);
    const [canDeleteHostAccount, setCanDeleteHostAccount] = useState<boolean>(false);
    const [canDeleteHostGroup, setCanDeleteHostGroup] = useState<boolean>(false);
    const [canEnableWsl, setCanEnableWsl] = useState<boolean>(false);
    const [canEnableLxd, setCanEnableLxd] = useState<boolean>(false);
    const [canEnableKvm, setCanEnableKvm] = useState<boolean>(false);
    const [canEnableVmm, setCanEnableVmm] = useState<boolean>(false);
    const [canEnableBhyve, setCanEnableBhyve] = useState<boolean>(false);

    // Check permissions
    useEffect(() => {
        const checkPermissions = async () => {
            const [editTags, editHostname, stopService, startService, restartService, addPackage, deploySshKey, deployCertificate, attachUbuntuPro, detachUbuntuPro, deployAntivirus, enableAntivirus, disableAntivirus, removeAntivirus, addHostAccount, addHostGroup, deleteHostAccount, deleteHostGroup, enableWsl, enableLxd, enableKvm, enableVmm, enableBhyve] = await Promise.all([
                hasPermission(SecurityRoles.EDIT_TAGS),
                hasPermission(SecurityRoles.EDIT_HOST_HOSTNAME),
                hasPermission(SecurityRoles.STOP_HOST_SERVICE),
                hasPermission(SecurityRoles.START_HOST_SERVICE),
                hasPermission(SecurityRoles.RESTART_HOST_SERVICE),
                hasPermission(SecurityRoles.ADD_PACKAGE),
                hasPermission(SecurityRoles.DEPLOY_SSH_KEY),
                hasPermission(SecurityRoles.DEPLOY_CERTIFICATE),
                hasPermission(SecurityRoles.ATTACH_UBUNTU_PRO),
                hasPermission(SecurityRoles.DETACH_UBUNTU_PRO),
                hasPermission(SecurityRoles.DEPLOY_ANTIVIRUS),
                hasPermission(SecurityRoles.ENABLE_ANTIVIRUS),
                hasPermission(SecurityRoles.DISABLE_ANTIVIRUS),
                hasPermission(SecurityRoles.REMOVE_ANTIVIRUS),
                hasPermission(SecurityRoles.ADD_HOST_ACCOUNT),
                hasPermission(SecurityRoles.ADD_HOST_GROUP),
                hasPermission(SecurityRoles.DELETE_HOST_ACCOUNT),
                hasPermission(SecurityRoles.DELETE_HOST_GROUP),
                hasPermission(SecurityRoles.ENABLE_WSL),
                hasPermission(SecurityRoles.ENABLE_LXD),
                hasPermission(SecurityRoles.ENABLE_KVM),
                hasPermission(SecurityRoles.ENABLE_VMM),
                hasPermission(SecurityRoles.ENABLE_BHYVE)
            ]);
            setCanEditTags(editTags);
            setCanEditHostname(editHostname);
            setCanStopService(stopService);
            setCanStartService(startService);
            setCanRestartService(restartService);
            setCanAddPackage(addPackage);
            setCanDeploySshKey(deploySshKey);
            setCanDeployCertificate(deployCertificate);
            setCanAttachUbuntuPro(attachUbuntuPro);
            setCanDetachUbuntuPro(detachUbuntuPro);
            setCanDeployAntivirus(deployAntivirus);
            setCanEnableAntivirus(enableAntivirus);
            setCanDisableAntivirus(disableAntivirus);
            setCanRemoveAntivirus(removeAntivirus);
            setCanAddHostAccount(addHostAccount);
            setCanAddHostGroup(addHostGroup);
            setCanDeleteHostAccount(deleteHostAccount);
            setCanDeleteHostGroup(deleteHostGroup);
            setCanEnableWsl(enableWsl);
            setCanEnableLxd(enableLxd);
            setCanEnableKvm(enableKvm);
            setCanEnableVmm(enableVmm);
            setCanEnableBhyve(enableBhyve);
        };
        checkPermissions();
    }, []);

    return {
        canEditTags,
        canEditHostname,
        canStopService,
        canStartService,
        canRestartService,
        canAddPackage,
        canDeploySshKey,
        canDeployCertificate,
        canAttachUbuntuPro,
        canDetachUbuntuPro,
        canDeployAntivirus,
        canEnableAntivirus,
        canDisableAntivirus,
        canRemoveAntivirus,
        canAddHostAccount,
        canAddHostGroup,
        canDeleteHostAccount,
        canDeleteHostGroup,
        canEnableWsl,
        canEnableLxd,
        canEnableKvm,
        canEnableVmm,
        canEnableBhyve,
    };
};
