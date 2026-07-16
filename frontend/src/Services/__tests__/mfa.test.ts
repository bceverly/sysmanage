// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for MFA API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  getMfaStatus,
  enrollStart,
  enrollComplete,
  disableMfa,
  regenerateBackupCodes,
  getMfaSettings,
  updateMfaSettings,
  MfaStatus,
  EnrollStartResponse,
  EnrollCompleteResponse,
  MfaSettings,
} from '../mfa';
import axiosInstance from '../api';

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}));

const resolve = (data: unknown) => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  config: {} as any,
});

describe('MFA API Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getMfaStatus', () => {
    it('fetches status', async () => {
      const status: MfaStatus = {
        enrolled: true,
        remaining_backup_codes: 8,
        admin_required: false,
        grace_period_days: 7,
      };
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve(status));

      const result = await getMfaStatus();

      expect(result).toEqual(status);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/auth/mfa/status');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
      await expect(getMfaStatus()).rejects.toThrow('boom');
    });
  });

  describe('enrollStart', () => {
    it('posts to enroll start with empty body', async () => {
      const data: EnrollStartResponse = {
        secret: 'S',
        provisioning_uri: 'otpauth://x',
        issuer: 'SysManage',
        account_name: 'a@b.com',
      };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(resolve(data));

      const result = await enrollStart();

      expect(result).toEqual(data);
      expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/auth/mfa/enroll/start', {});
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('e'));
      await expect(enrollStart()).rejects.toThrow('e');
    });
  });

  describe('enrollComplete', () => {
    it('posts the verification code', async () => {
      const data: EnrollCompleteResponse = {
        backup_codes: ['a', 'b'],
        enrolled_at: '2026-01-01T00:00:00Z',
      };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(resolve(data));

      const result = await enrollComplete('123456');

      expect(result).toEqual(data);
      expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/auth/mfa/enroll/complete', {
        code: '123456',
      });
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('bad'));
      await expect(enrollComplete('000000')).rejects.toThrow('bad');
    });
  });

  describe('disableMfa', () => {
    it('posts the password', async () => {
      const data = { message: 'disabled', enrolled: false };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(resolve(data));

      const result = await disableMfa('pw');

      expect(result).toEqual(data);
      expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/auth/mfa/disable', {
        password: 'pw',
      });
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('nope'));
      await expect(disableMfa('pw')).rejects.toThrow('nope');
    });
  });

  describe('regenerateBackupCodes', () => {
    it('posts the code', async () => {
      const data: EnrollCompleteResponse = {
        backup_codes: ['x', 'y'],
        enrolled_at: '2026-02-02T00:00:00Z',
      };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(resolve(data));

      const result = await regenerateBackupCodes('654321');

      expect(result).toEqual(data);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/auth/mfa/backup-codes/regenerate',
        { code: '654321' },
      );
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('r'));
      await expect(regenerateBackupCodes('1')).rejects.toThrow('r');
    });
  });

  describe('getMfaSettings', () => {
    it('fetches settings', async () => {
      const settings: MfaSettings = {
        issuer_name: 'SysManage',
        totp_digits: 6,
        totp_period_seconds: 30,
        backup_code_count: 10,
        admin_required: false,
        grace_period_days: 7,
      };
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(resolve(settings));

      const result = await getMfaSettings();

      expect(result).toEqual(settings);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/settings/mfa');
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('g'));
      await expect(getMfaSettings()).rejects.toThrow('g');
    });
  });

  describe('updateMfaSettings', () => {
    it('puts settings patch', async () => {
      const patch: Partial<MfaSettings> = { totp_digits: 8 };
      const updated: MfaSettings = {
        issuer_name: 'SysManage',
        totp_digits: 8,
        totp_period_seconds: 30,
        backup_code_count: 10,
        admin_required: true,
        grace_period_days: 3,
      };
      vi.mocked(axiosInstance.put).mockResolvedValueOnce(resolve(updated));

      const result = await updateMfaSettings(patch);

      expect(result).toEqual(updated);
      expect(axiosInstance.put).toHaveBeenCalledWith('/api/v1/settings/mfa', patch);
    });

    it('rethrows on failure', async () => {
      vi.mocked(axiosInstance.put).mockRejectedValueOnce(new Error('u'));
      await expect(updateMfaSettings({})).rejects.toThrow('u');
    });
  });
});
