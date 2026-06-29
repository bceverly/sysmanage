import axiosInstance from './api';

export interface OpenBAOHealth {
  [key: string]: string;
}

export interface OpenBAOStatus {
  running: boolean;
  status: string;
  message: string;
  pid: number | null;
  server_url: string | null;
  health: OpenBAOHealth | null;
  recent_logs: string[];
  sealed: boolean | null;
}

export interface OpenBAOConfig {
  enabled: boolean;
  url: string;
  mount_path: string;
  timeout: number;
  verify_ssl: boolean;
  dev_mode: boolean;
  has_token: boolean;
}

export interface OpenBAOOperationResult {
  success: boolean;
  message: string;
  status: OpenBAOStatus;
  output?: string;
  error?: string;
}

class OpenBAOService {
  async getStatus(): Promise<OpenBAOStatus> {
    const response = await axiosInstance.get('/api/v1/openbao/status');
    return response.data;
  }

  async getConfig(): Promise<OpenBAOConfig> {
    const response = await axiosInstance.get('/api/v1/openbao/config');
    return response.data;
  }

  async start(): Promise<OpenBAOOperationResult> {
    const response = await axiosInstance.post('/api/v1/openbao/start');
    return response.data;
  }

  async stop(): Promise<OpenBAOOperationResult> {
    const response = await axiosInstance.post('/api/v1/openbao/stop');
    return response.data;
  }

  async seal(): Promise<OpenBAOOperationResult> {
    const response = await axiosInstance.post('/api/v1/openbao/seal');
    return response.data;
  }

  async unseal(): Promise<OpenBAOOperationResult> {
    const response = await axiosInstance.post('/api/v1/openbao/unseal');
    return response.data;
  }
}

export const openBAOService = new OpenBAOService();