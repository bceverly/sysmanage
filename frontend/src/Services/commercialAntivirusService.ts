// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from './api';

export interface CommercialAntivirusStatus {
  id: string;
  host_id: string;
  product_name: string | null;
  product_version: string | null;
  service_enabled: boolean | null;
  antispyware_enabled: boolean | null;
  antivirus_enabled: boolean | null;
  realtime_protection_enabled: boolean | null;
  full_scan_age: number | null;
  quick_scan_age: number | null;
  full_scan_end_time: string | null;
  quick_scan_end_time: string | null;
  signature_last_updated: string | null;
  signature_version: string | null;
  tamper_protection_enabled: boolean | null;
  created_at: string;
  last_updated: string;
}

export const getCommercialAntivirusStatus = async (hostId: string): Promise<CommercialAntivirusStatus | null> => {
  const response = await axiosInstance.get<CommercialAntivirusStatus | null>(`/api/v1/hosts/${hostId}/commercial-antivirus-status`);
  return response.data;
};
