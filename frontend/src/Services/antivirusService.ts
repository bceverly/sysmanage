// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from './api';

export interface AntivirusStatus {
  id: string;
  host_id: string;
  software_name: string | null;
  install_path: string | null;
  version: string | null;
  enabled: boolean | null;
  last_updated: string;
}

export const getAntivirusStatus = async (hostId: string): Promise<AntivirusStatus | null> => {
  const response = await axiosInstance.get<AntivirusStatus | null>(`/api/v1/hosts/${hostId}/antivirus-status`);
  return response.data;
};
