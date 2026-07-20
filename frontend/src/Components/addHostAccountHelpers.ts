// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Pure helpers extracted from AddHostAccountModal so the component's submit
// handler stays under the cognitive-complexity budget and the branch logic
// is unit-testable outside React.

import type { TFunction } from 'i18next';

export interface CreateUserPayload {
    username: string;
    full_name?: string;
    home_directory?: string;
    shell?: string;
    create_home_dir?: boolean;
    uid?: number;
    primary_group?: string;
    password?: string;
    password_never_expires?: boolean;
    user_must_change_password?: boolean;
    account_disabled?: boolean;
}

export interface AccountFormValues {
    username: string;
    fullName: string;
    homeDirectory: string;
    shell: string;
    createHomeDir: boolean;
    uid: string;
    primaryGroup: string;
    password: string;
    confirmPassword: string;
    passwordNeverExpires: boolean;
    userMustChangePassword: boolean;
    accountDisabled: boolean;
}

// Validate the form. Returns null when valid, otherwise a translated error
// message to display.
export const validateAccountForm = (
    t: TFunction,
    values: AccountFormValues,
    isWindows: boolean,
    minUid: number,
): string | null => {
    if (!values.username.trim()) {
        return t('hostAccount.usernameRequired', 'Username is required');
    }

    // Username validation - allow alphanumeric and underscore/dash
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(values.username)) {
        return t('hostAccount.invalidUsername', 'Username must start with a letter and contain only letters, numbers, underscores, and dashes');
    }

    if (isWindows) {
        const passwordError = validateWindowsPassword(t, values.password, values.confirmPassword);
        if (passwordError) {
            return passwordError;
        }
    }

    // UID validation if provided (platform-specific minimum)
    if (values.uid && (Number.isNaN(Number(values.uid)) || Number(values.uid) < minUid)) {
        return t('hostAccount.invalidUidPlatform', `UID must be a number >= ${minUid}`, { minUid });
    }

    return null;
};

const validateWindowsPassword = (
    t: TFunction,
    password: string,
    confirmPassword: string,
): string | null => {
    if (!password) {
        return t('hostAccount.passwordRequired', 'Password is required for Windows accounts');
    }
    // Client-side confirm-password match on the user's OWN input — no
    // stored secret and no attacker, so a constant-time compare isn't
    // warranted. (The rule is off in the main lint; suppress it for the
    // dedicated security scan too.)
    // eslint-disable-next-line security/detect-possible-timing-attacks
    if (password !== confirmPassword) {
        return t('hostAccount.passwordMismatch', 'Passwords do not match');
    }
    if (password.length < 8) {
        return t('hostAccount.passwordTooShort', 'Password must be at least 8 characters');
    }
    return null;
};

// Build the create-user request payload from the current form values.
export const buildCreateUserPayload = (
    values: AccountFormValues,
    isWindows: boolean,
): CreateUserPayload => {
    const payload: CreateUserPayload = {
        username: values.username.trim(),
    };

    if (values.fullName.trim()) {
        payload.full_name = values.fullName.trim();
    }

    if (isWindows) {
        payload.password = values.password;
        payload.password_never_expires = values.passwordNeverExpires;
        payload.user_must_change_password = values.userMustChangePassword;
        payload.account_disabled = values.accountDisabled;
    } else {
        if (values.homeDirectory) {
            payload.home_directory = values.homeDirectory;
        }
        if (values.shell) {
            payload.shell = values.shell;
        }
        payload.create_home_dir = values.createHomeDir;
        if (values.uid) {
            payload.uid = Number(values.uid);
        }
        if (values.primaryGroup) {
            payload.primary_group = values.primaryGroup;
        }
    }

    return payload;
};

// Extract a user-facing message from an unknown (axios or generic) error.
export const extractAccountErrorMessage = (t: TFunction, err: unknown): string => {
    if (err && typeof err === 'object' && 'response' in err) {
        const axiosError = err as { response?: { data?: { detail?: string } } };
        if (axiosError.response?.data?.detail) {
            return axiosError.response.data.detail;
        }
    } else if (err instanceof Error) {
        return err.message;
    }
    return t('hostAccount.createFailed', 'Failed to create user account');
};
