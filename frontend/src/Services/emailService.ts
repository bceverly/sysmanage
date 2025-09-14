import axiosInstance from './api';

export interface EmailConfig {
  enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  from_address: string;
  from_name: string;
  subject_prefix: string;
  configured: boolean;
}

export interface EmailTestRequest {
  to_address: string;
}

export interface EmailTestResponse {
  success: boolean;
  message: string;
}

export const emailService = {
  /**
   * Get email configuration status
   */
  async getConfig(): Promise<EmailConfig> {
    const response = await axiosInstance.get('/api/email/config');
    return response.data;
  },

  /**
   * Send a test email to verify configuration
   */
  async sendTestEmail(toAddress: string): Promise<EmailTestResponse> {
    const response = await axiosInstance.post('/api/email/test', {
      to_address: toAddress
    });
    return response.data;
  }
};