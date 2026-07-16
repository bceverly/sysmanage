// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Multi-Factor Authentication API client (Phase 10.3).
 *
 * Wraps the ``/api/auth/mfa/*`` and ``/api/settings/mfa`` endpoints so
 * the profile page (enrollment) and login page (challenge) don't have
 * to talk to axios directly.
 */

import axiosInstance from './api';

export interface MfaStatus {
  enrolled: boolean;
  enrolled_at?: string | null;
  last_used_at?: string | null;
  last_used_method?: string | null;
  remaining_backup_codes: number;
  admin_required: boolean;
  grace_period_days: number;
}

export interface EnrollStartResponse {
  secret: string;
  provisioning_uri: string;
  issuer: string;
  account_name: string;
}

export interface EnrollCompleteResponse {
  backup_codes: string[];
  enrolled_at: string;
}

export interface MfaSettings {
  issuer_name: string;
  totp_digits: number;
  totp_period_seconds: number;
  backup_code_count: number;
  admin_required: boolean;
  grace_period_days: number;
  updated_at?: string | null;
}

export const getMfaStatus = async (): Promise<MfaStatus> => {
  const response = await axiosInstance.get<MfaStatus>('/api/v1/auth/mfa/status');
  return response.data;
};

export const enrollStart = async (): Promise<EnrollStartResponse> => {
  const response = await axiosInstance.post<EnrollStartResponse>(
    '/api/v1/auth/mfa/enroll/start',
    {},
  );
  return response.data;
};

export const enrollComplete = async (
  code: string,
): Promise<EnrollCompleteResponse> => {
  const response = await axiosInstance.post<EnrollCompleteResponse>(
    '/api/v1/auth/mfa/enroll/complete',
    { code },
  );
  return response.data;
};

export const disableMfa = async (
  password: string,
): Promise<{ message: string; enrolled: boolean }> => {
  const response = await axiosInstance.post<{
    message: string;
    enrolled: boolean;
  }>('/api/v1/auth/mfa/disable', { password });
  return response.data;
};

export const regenerateBackupCodes = async (
  code: string,
): Promise<EnrollCompleteResponse> => {
  const response = await axiosInstance.post<EnrollCompleteResponse>(
    '/api/v1/auth/mfa/backup-codes/regenerate',
    { code },
  );
  return response.data;
};

export const getMfaSettings = async (): Promise<MfaSettings> => {
  const response = await axiosInstance.get<MfaSettings>('/api/v1/settings/mfa');
  return response.data;
};

export const updateMfaSettings = async (
  patch: Partial<MfaSettings>,
): Promise<MfaSettings> => {
  const response = await axiosInstance.put<MfaSettings>('/api/v1/settings/mfa', patch);
  return response.data;
};
