// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Pure form logic for the Create Child Host dialog.
 *
 * Split out of useChildHosts when the Phase 12.5 Windows path pushed that file
 * past the 1000-line cap.  Being pure functions over the form data, these are
 * also directly testable without rendering the hook.
 */
import type { TFunction } from 'i18next';

import { isWindowsDistribution } from './hostDetailHelpers';
import type { ChildHostFormData } from './hostDetailTypes';

// Windows-only validation, split out of validateChildHostForm to keep that
// function under the cognitive-complexity cap now that the Windows path
// roughly doubles the number of rules.
const validateWindowsChildHost = (
    t: TFunction,
    formData: ChildHostFormData,
): string | null => {
    if (!isWindowsDistribution(formData.distribution)) {
        return null;
    }
    // The ISO is not downloadable — Microsoft publishes no stable
    // unauthenticated URL for Server media — so without a local path there is
    // nothing to install from and the VM stalls at the firmware.
    if (!formData.windowsIsoPath) {
        return t('hostDetail.windowsIsoPathRequired', 'Please enter the path to the Windows installation ISO');
    }
    // Domain join is all-or-nothing: a domain with no credentials fails the
    // specialize pass mid-install, at a prompt nobody is watching.
    if (formData.windowsJoinDomain && (!formData.windowsDomainUser || !formData.windowsDomainPassword)) {
        return t('hostDetail.windowsDomainCredentialsRequired', 'Please enter the domain join account and password');
    }
    return null;
};

// Windows-only request fields, split out of buildCreateChildRequest for the
// same reason.
const addWindowsRequestFields = (
    requestData: Record<string, string | boolean>,
    formData: ChildHostFormData,
): void => {
    // Windows has no cloud image; the distribution is a dispatch token, and
    // sending it as a URL would be misleading in the request log.
    delete requestData.cloud_image_url;
    // The built-in Administrator is the account being configured, so the one
    // password the operator typed is both the child password (hashed
    // server-side like every other guest) and the unattend value.
    requestData.username = 'Administrator';
    requestData.windows_admin_password = formData.password;
    requestData.windows_edition = formData.windowsEdition;
    requestData.windows_iso_path = formData.windowsIsoPath;
    requestData.windows_timezone = formData.windowsTimezone;
    requestData.windows_locale = formData.windowsLocale;
    if (formData.windowsProductKey) {
        requestData.windows_product_key = formData.windowsProductKey;
    }
    if (formData.windowsJoinDomain) {
        requestData.windows_join_domain = formData.windowsJoinDomain;
        requestData.windows_domain_user = formData.windowsDomainUser;
        requestData.windows_domain_password = formData.windowsDomainPassword;
        if (formData.windowsDomainOu) {
            requestData.windows_domain_ou = formData.windowsDomainOu;
        }
    }
};

export const validateChildHostForm = (
    t: TFunction,
    formData: ChildHostFormData,
    computedFqdn: string,
): string | null => {
    if (!formData.distribution) {
        // Error is shown inline on the field (no snackbar).
        return null;
    }
    if (!formData.hostname || !computedFqdn) {
        return t('hostDetail.childHostHostnameRequired', 'Please enter a hostname');
    }
    // Windows configures the built-in Administrator account, so the dialog
    // hides the username field on that path — demanding one here would dead-end
    // the operator on an error with no field to satisfy it.
    if (!formData.username && !isWindowsDistribution(formData.distribution)) {
        return t('hostDetail.childHostUsernameRequired', 'Please enter a username');
    }
    if (!formData.password) {
        return t('hostDetail.childHostPasswordRequired', 'Please enter a password');
    }
    if (formData.password !== formData.confirmPassword) {
        return t('hostDetail.childHostPasswordMismatch', 'Passwords do not match');
    }
    const needsVmName =
        formData.childType === 'vmm' ||
        formData.childType === 'kvm' ||
        formData.childType === 'bhyve';
    if (needsVmName && !formData.vmName) {
        return t('hostDetail.childHostVmNameRequired', 'Please enter a VM name');
    }
    const windowsError = validateWindowsChildHost(t, formData);
    if (windowsError) {
        return windowsError;
    }
    // For VMM specifically, require root password (KVM uses cloud-init with user password).
    if (formData.childType === 'vmm') {
        if (!formData.rootPassword) {
            return t('hostDetail.childHostRootPasswordRequired', 'Please enter a root password');
        }
        if (formData.rootPassword !== formData.confirmRootPassword) {
            return t('hostDetail.childHostRootPasswordMismatch', 'Root passwords do not match');
        }
    }
    return null;
};

// Pure builder for the create-child request payload. Mirrors the per-type
// branching that used to live inline in handleCreateChildHost.
export const buildCreateChildRequest = (
    formData: ChildHostFormData,
    computedFqdn: string,
): Record<string, string | boolean> => {
    const requestData: Record<string, string | boolean> = {
        child_type: formData.childType,
        distribution: formData.distribution,
        hostname: computedFqdn, // Always send the computed FQDN
        username: formData.username,
        password: formData.password,
        auto_approve: formData.autoApprove,
    };

    // For LXD, also send container name.
    if (formData.childType === 'lxd' && formData.containerName) {
        requestData.container_name = formData.containerName;
    }

    // For VMM, send vm_name, iso_url, and root_password.
    if (formData.childType === 'vmm') {
        requestData.vm_name = formData.vmName || formData.hostname;
        // For VMM, the install_identifier contains the ISO URL.
        if (formData.distribution) {
            requestData.iso_url = formData.distribution;
        }
        requestData.root_password = formData.rootPassword;
    }

    // For KVM and bhyve, send vm_name and cloud_image_url.
    if (formData.childType === 'kvm' || formData.childType === 'bhyve') {
        requestData.vm_name = formData.vmName || formData.hostname;
        if (formData.distribution) {
            requestData.cloud_image_url = formData.distribution;
        }
    }

    if (isWindowsDistribution(formData.distribution)) {
        addWindowsRequestFields(requestData, formData);
    }

    return requestData;
};
