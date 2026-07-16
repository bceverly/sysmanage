// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

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
    const response = await axiosInstance.get('/api/v1/email/config');
    return response.data;
  },

  /**
   * Send a test email to verify configuration
   */
  async sendTestEmail(toAddress: string): Promise<EmailTestResponse> {
    const response = await axiosInstance.post('/api/v1/email/test', {
      to_address: toAddress
    });
    return response.data;
  }
};