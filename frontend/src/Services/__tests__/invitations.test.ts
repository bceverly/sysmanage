// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for invitations API service
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  doListInvitations,
  doCreateInvitation,
  doRevokeInvitation,
  doResendInvitation,
  doValidateInvitation,
  doAcceptInvitation,
  Invitation,
  CreateInvitationRequest,
  AcceptInvitationRequest,
} from '../invitations';
import api from '../api';

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const resolve = (data: unknown) => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  config: {} as any,
});

const sampleInvitation: Invitation = {
  id: 'i1',
  email: 'user@example.com',
  is_admin: false,
  role_ids: ['r1'],
  first_name: 'Jane',
  last_name: 'Doe',
  invited_by: 'admin',
  created_at: '2026-01-01T00:00:00Z',
  expires_at: '2026-01-08T00:00:00Z',
  status: 'pending',
};

describe('Invitations API Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('doListInvitations', () => {
    it('lists invitations defaulting pending_only to false', async () => {
      vi.mocked(api.get).mockResolvedValueOnce(resolve([sampleInvitation]));

      const result = await doListInvitations();

      expect(result).toEqual([sampleInvitation]);
      expect(api.get).toHaveBeenCalledWith('/api/v1/invitations', {
        params: { pending_only: false },
      });
    });

    it('passes pending_only when true', async () => {
      vi.mocked(api.get).mockResolvedValueOnce(resolve([]));

      await doListInvitations(true);

      expect(api.get).toHaveBeenCalledWith('/api/v1/invitations', {
        params: { pending_only: true },
      });
    });

    it('rethrows on failure', async () => {
      vi.mocked(api.get).mockRejectedValueOnce(new Error('boom'));
      await expect(doListInvitations()).rejects.toThrow('boom');
    });
  });

  describe('doCreateInvitation', () => {
    it('posts a new invitation', async () => {
      const payload: CreateInvitationRequest = {
        email: 'user@example.com',
        role_ids: ['r1'],
        is_admin: false,
      };
      vi.mocked(api.post).mockResolvedValueOnce(resolve(sampleInvitation));

      const result = await doCreateInvitation(payload);

      expect(result).toEqual(sampleInvitation);
      expect(api.post).toHaveBeenCalledWith('/api/v1/invitations', payload);
    });

    it('rethrows on failure', async () => {
      vi.mocked(api.post).mockRejectedValueOnce(new Error('cr'));
      await expect(
        doCreateInvitation({ email: 'x@y.com' }),
      ).rejects.toThrow('cr');
    });
  });

  describe('doRevokeInvitation', () => {
    it('deletes an invitation', async () => {
      const data = { success: true, message: 'revoked' };
      vi.mocked(api.delete).mockResolvedValueOnce(resolve(data));

      const result = await doRevokeInvitation('i1');

      expect(result).toEqual(data);
      expect(api.delete).toHaveBeenCalledWith('/api/v1/invitations/i1');
    });

    it('rethrows on failure', async () => {
      vi.mocked(api.delete).mockRejectedValueOnce(new Error('rev'));
      await expect(doRevokeInvitation('i1')).rejects.toThrow('rev');
    });
  });

  describe('doResendInvitation', () => {
    it('posts to the resend endpoint', async () => {
      const data = { success: true, message: 'resent' };
      vi.mocked(api.post).mockResolvedValueOnce(resolve(data));

      const result = await doResendInvitation('i1');

      expect(result).toEqual(data);
      expect(api.post).toHaveBeenCalledWith('/api/v1/invitations/i1/resend');
    });

    it('rethrows on failure', async () => {
      vi.mocked(api.post).mockRejectedValueOnce(new Error('res'));
      await expect(doResendInvitation('i1')).rejects.toThrow('res');
    });
  });

  describe('doValidateInvitation', () => {
    it('validates a token, url-encoding it', async () => {
      vi.mocked(api.get).mockResolvedValueOnce(resolve(sampleInvitation));

      const result = await doValidateInvitation('tok en/1');

      expect(result).toEqual(sampleInvitation);
      expect(api.get).toHaveBeenCalledWith(
        '/api/v1/invitations/validate/tok%20en%2F1',
      );
    });

    it('rethrows on failure', async () => {
      vi.mocked(api.get).mockRejectedValueOnce(new Error('val'));
      await expect(doValidateInvitation('t')).rejects.toThrow('val');
    });
  });

  describe('doAcceptInvitation', () => {
    it('posts the accept payload', async () => {
      const payload: AcceptInvitationRequest = {
        token: 'tok',
        password: 'pw',
        confirm_password: 'pw',
        first_name: 'Jane',
        last_name: 'Doe',
      };
      const data = { success: true, message: 'accepted' };
      vi.mocked(api.post).mockResolvedValueOnce(resolve(data));

      const result = await doAcceptInvitation(payload);

      expect(result).toEqual(data);
      expect(api.post).toHaveBeenCalledWith('/api/v1/invitations/accept', payload);
    });

    it('rethrows on failure', async () => {
      vi.mocked(api.post).mockRejectedValueOnce(new Error('acc'));
      await expect(
        doAcceptInvitation({ token: 't', password: 'p', confirm_password: 'p' }),
      ).rejects.toThrow('acc');
    });
  });
});
