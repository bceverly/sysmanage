import axiosInstance from './api.js';

export interface SecretResponse {
  id: string;
  name: string;
  secret_type: string;
  secret_subtype?: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface SecretWithContent extends SecretResponse {
  content: string;
}

export interface SecretType {
  value: string;
  label: string;
  supports_visibility: boolean;
  visibility_label?: string;
  visibility_options?: Array<{
    value: string;
    label: string;
  }>;
}

export interface SecretTypesResponse {
  types: SecretType[];
}

export interface CreateSecretRequest {
  name: string;
  secret_type: string;
  content: string;
  secret_subtype: string;
}

export type UpdateSecretRequest = CreateSecretRequest;

export const secretsService = {
  // Get all secrets
  async getSecrets(): Promise<SecretResponse[]> {
    const response = await axiosInstance.get('/api/secrets');
    return response.data;
  },

  // Get secret types
  async getSecretTypes(): Promise<SecretTypesResponse> {
    const response = await axiosInstance.get('/api/secrets/types');
    return response.data;
  },

  // Get secret by ID (metadata only)
  async getSecret(id: string): Promise<SecretResponse> {
    const response = await axiosInstance.get(`/api/secrets/${id}`);
    return response.data;
  },

  // Get secret content
  async getSecretContent(id: string): Promise<SecretWithContent> {
    const response = await axiosInstance.get(`/api/secrets/${id}/content`);
    return response.data;
  },

  // Create new secret
  async createSecret(secretData: CreateSecretRequest): Promise<SecretResponse> {
    const response = await axiosInstance.post('/api/secrets', secretData);
    return response.data;
  },

  // Update existing secret
  async updateSecret(id: string, secretData: UpdateSecretRequest): Promise<SecretResponse> {
    const response = await axiosInstance.put(`/api/secrets/${id}`, secretData);
    return response.data;
  },

  // Delete single secret
  async deleteSecret(id: string): Promise<void> {
    await axiosInstance.delete(`/api/secrets/${id}`);
  },

  // Delete multiple secrets
  async deleteSecrets(secretIds: string[]): Promise<void> {
    await axiosInstance.delete('/api/secrets', {
      data: secretIds
    });
  }
};