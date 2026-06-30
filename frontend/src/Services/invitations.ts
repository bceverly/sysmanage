import api from './api';

export interface Invitation {
    id: string;
    email: string;
    is_admin: boolean;
    role_ids: string[];
    first_name: string | null;
    last_name: string | null;
    invited_by: string | null;
    created_at: string | null;
    expires_at: string | null;
    status: 'pending' | 'accepted' | 'revoked' | 'expired';
}

export interface CreateInvitationRequest {
    email: string;
    role_ids?: string[];
    is_admin?: boolean;
    first_name?: string | null;
    last_name?: string | null;
}

export interface AcceptInvitationRequest {
    token: string;
    password: string;
    confirm_password: string;
    first_name?: string | null;
    last_name?: string | null;
}

interface SimpleResponse {
    success: boolean;
    message: string;
}

export const doListInvitations = async (
    pendingOnly = false,
): Promise<Invitation[]> => {
    const response = await api.get<Invitation[]>('/api/v1/invitations', {
        params: { pending_only: pendingOnly },
    });
    return response.data;
};

export const doCreateInvitation = async (
    payload: CreateInvitationRequest,
): Promise<Invitation> => {
    const response = await api.post<Invitation>('/api/v1/invitations', payload);
    return response.data;
};

export const doRevokeInvitation = async (id: string): Promise<SimpleResponse> => {
    const response = await api.delete<SimpleResponse>(`/api/v1/invitations/${id}`);
    return response.data;
};

export const doResendInvitation = async (id: string): Promise<SimpleResponse> => {
    const response = await api.post<SimpleResponse>(
        `/api/v1/invitations/${id}/resend`,
    );
    return response.data;
};

export const doValidateInvitation = async (
    token: string,
): Promise<Invitation> => {
    const response = await api.get<Invitation>(
        `/api/v1/invitations/validate/${encodeURIComponent(token)}`,
    );
    return response.data;
};

export const doAcceptInvitation = async (
    payload: AcceptInvitationRequest,
): Promise<SimpleResponse> => {
    const response = await api.post<SimpleResponse>(
        '/api/v1/invitations/accept',
        payload,
    );
    return response.data;
};
